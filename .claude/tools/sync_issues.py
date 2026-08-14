"""バックログとチケットの差分を計算し、承認のうえで反映する。

規約の正は `.claude/skills/issue-tracking/SKILL.md`。
**進捗の正は `docs/backlog.md`** で、チケットはその写し。したがって同期は
バックログ → チケットの一方向で、逆流（チケットから成熟度を書き戻す）はしない。

置き場所はプロファイルの「チケット追跡」の `- 使用:` で決まる:

    github … GitHub Issue。対応付けは **タイトルの接頭辞（`S##:` / `D##:`）だけ**
    local  … ハブ（docs/slices/S##-*.md）の「## チケット」節。
             負債（D##）は対象外 —— 負債表の行そのものがチケット

どちらのモードでも既定は **dry-run** （差分を出すだけで書き込まない）。
`--apply` を付けたときだけ書き込む。外部への書き込みは取り消しにくいので、
エージェントは差分を提示して承認を得てから `--apply` する（絶対ルール 4）。

使い方（前置コマンドはプロファイルの
「.claude/tools/ の Python ツール実行」。例: uv run python）:
    <ツール実行コマンド> .claude/tools/sync_issues.py
    <ツール実行コマンド> .claude/tools/sync_issues.py --apply
    <ツール実行コマンド> .claude/tools/sync_issues.py --include-done
    <ツール実行コマンド> .claude/tools/sync_issues.py --issues-json <path>   # 検証用

終了コード:
    0 = 差分なし（または --apply がすべて成功した）
    1 = 差分あり（未反映）、または --apply の途中で失敗した
    2 = 使用: off / 未設定、CLAUDE.md / バックログが無い、リポジトリ未設定、引数のエラー
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import issue_mode

# バックログの表の行（先頭セルが S## / D## のもの）
_ROW = re.compile(r"^\|\s*([SD][0-9]+)\s*\|(.*)\|?\s*$")
_MATURITY = re.compile(r"L([0-3])")
# Issue タイトルの接頭辞。ここだけが対応付けの鍵
_PREFIX = re.compile(r"^\s*([SD][0-9]+)\s*[:：]")

SEVEN = (
    ("要求仕様書", "docs/usdm/src/{key}-*.html"),
    ("設計書", "docs/design/{key}-*.md"),
    ("単体テスト", "テストルート"),
    ("実装", "ソースルート"),
    ("統合テスト", "統合テストルート"),
    ("テスト結果まとめ", "docs/test-reports/{key}-*.md"),
    ("マニュアル", "docs/manual.md の `## {key}` 節"),
)

NOTE = "進捗の正は `docs/backlog.md`。この Issue はその写し（窓）です。"


@dataclass
class Row:
    """バックログの 1 行（スライスまたは負債）。

    Attributes:
        key: `S03` / `D01`。Issue タイトルの接頭辞になる。
        name: 表の 2 列目（スライス名・負債の内容）。
        maturity: スライスの成熟度 0〜3。負債は -1。
        done: これ以上 Issue を開けておく必要が無い状態（L3 到達・返済済み）。
        cells: 行のセル全部（負債の本文を組み立てるのに使う）。
    """

    key: str
    name: str
    maturity: int
    done: bool
    cells: list[str] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return "slice" if self.key.startswith("S") else "debt"

    @property
    def title(self) -> str:
        return f"{self.key}: {self.name}"

    @property
    def labels(self) -> list[str]:
        if self.kind == "debt":
            return ["debt"]
        return ["slice", f"L{self.maturity}"]


@dataclass
class Change:
    """既存 Issue に対する変更（更新・クローズ・再オープン）。"""

    number: int
    key: str
    title: str
    labels: list[str]
    reason: str


@dataclass
class External:
    """接頭辞を持たない外部起票（取り込み候補）。"""

    number: int
    title: str


@dataclass
class Plan:
    """同期の計画。GitHub には触っていない状態の差分。"""

    create: list[Row] = field(default_factory=list)
    update: list[Change] = field(default_factory=list)
    close: list[Change] = field(default_factory=list)
    reopen: list[Change] = field(default_factory=list)
    pull: list[External] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """送信すべき差分が無いか（取り込み候補は人の判定待ちなので含めない）。"""
        return not (self.create or self.update or self.close or self.reopen)


def parse_backlog(text: str) -> list[Row]:
    """バックログのスライス表と負債表から行を読み取る。

    Args:
        text: `docs/backlog.md` の全文。

    Returns:
        表に現れた順の行（雛形の `S##` 行・`{…}` を含む行は除く）。
    """
    rows: list[Row] = []
    seen: set[str] = set()
    for line in text.splitlines():
        matched = _ROW.match(line.strip())
        if not matched:
            continue
        key = matched.group(1).upper()
        cells = [cell.strip() for cell in matched.group(2).split("|")]
        # 行末の `|` が空セルを生むので落とす（状態列を最後のセルで読むため）
        while cells and cells[-1] == "":
            cells.pop()
        name = cells[0].strip("`") if cells else ""
        if not name or "{" in name or key in seen:
            continue
        seen.add(key)
        if key.startswith("S"):
            level = _MATURITY.search(cells[1] if len(cells) > 1 else "")
            maturity = int(level.group(1)) if level else 0
            rows.append(Row(key, name, maturity, maturity >= 3, cells))
        else:
            state = cells[-1] if cells else ""
            rows.append(Row(key, name, -1, "済" in state, cells))
    return rows


def build_body(row: Row) -> str:
    """Issue の本文を組み立てる（雛形の正はここ 1 か所だけ）。

    Args:
        row: バックログの 1 行。

    Returns:
        Markdown の本文。7 点セットのチェックリストと、正の所在を必ず含む。
    """
    if row.kind == "debt":
        source = row.cells[1] if len(row.cells) > 1 else "—"
        pain = row.cells[2] if len(row.cells) > 2 else "—"
        when = row.cells[3] if len(row.cells) > 3 else "—"
        return (
            f"## {row.key} {row.name}\n\n"
            f"- 出所: {source}\n- 痛み: {pain}\n- 返す条件: {when}\n\n"
            f"返し方は `/refactor {row.key}`（振る舞いを変えず緑を保つ）。\n\n"
            f"> {NOTE}\n"
        )

    checklist = "\n".join(
        f"- [ ] {name} —— {where.format(key=row.key)}" for name, where in SEVEN
    )
    return (
        f"## {row.key} {row.name}\n\n"
        f"- 現在の成熟度: L{row.maturity}\n"
        f"- 次の反復で上げる先: L{min(row.maturity + 1, 3)}\n\n"
        f"### 成果物 7 点セット\n\n{checklist}\n\n"
        f"### リンク\n\n"
        f"- バックログ: `docs/backlog.md`\n"
        f"- ハブ: `docs/slices/{row.key}-*.md`\n\n"
        f"> {NOTE}\n"
    )


# ─────────────────────────────────────────────────────────────────────────
# ローカルチケット（使用: local）
#
# 置き場所はハブ（docs/slices/S##-*.md）の「## チケット」節。
# 新しいファイルを作らないのは、ハブが既に 7 点セットの索引であり、
# 別ファイルを立てると同じ内容が 2 か所に並んで必ずずれるため。
# GitHub Issue がハブに足しているのは 状態・目標・履歴 の 3 つだけなので、
# その 3 つを節として足す。
# ─────────────────────────────────────────────────────────────────────────

TICKET_HEADING = "## チケット"
HISTORY_HEADING = "### 履歴（追記だけ。書き換えない）"

_TICKET_AT = re.compile(r"^##\s+チケット\s*$")
_NEXT_H2 = re.compile(r"^##\s+")
_STATE = re.compile(r"^(\s*-\s*状態\s*[:：]\s*)(.*)$")
_GOAL = re.compile(r"^(\s*-\s*目標\s*[:：]\s*)(.*)$")

LOCAL_NOTE = "進捗の正は `docs/backlog.md`。このチケットはその写し（窓）です。"


def _today() -> str:
    """今日の日付（`YYYY-MM-DD`）。テストから差し替えられるよう関数にする。"""
    from datetime import date

    return date.today().isoformat()


TODAY = _today


def ticket_state(row: Row) -> str:
    """バックログの 1 行から、チケットの状態を決める。

    Args:
        row: バックログの 1 行。

    Returns:
        `未着手` / `進行中` / `完了` のいずれか。
    """
    if row.done:
        return "完了"
    if row.kind == "slice" and row.maturity <= 0:
        return "未着手"
    return "進行中"


def ticket_goal(row: Row) -> str:
    """チケットの目標欄（GitHub の成熟度ラベルに当たるもの）。"""
    if row.kind == "debt":
        return "負債の返済"
    if row.done:
        return "L3（到達済み）"
    return f"L{row.maturity} → L{min(row.maturity + 1, 3)}"


def hub_path(root: Path, key: str) -> Path | None:
    """`docs/slices/S##-*.md` のハブを 1 つ探す。無ければ None。"""
    found = sorted((root / "docs" / "slices").glob(f"{key}-*.md"))
    return found[0] if found else None


def read_ticket(text: str) -> dict[str, str] | None:
    """ハブの「## チケット」節から状態と目標を読み取る。

    Args:
        text: ハブ（`docs/slices/S##-*.md`）の全文。

    Returns:
        `{"状態": ..., "目標": ...}`。節が無ければ None
        （None は「未起票」を意味し、空の辞書と区別する必要がある）。
    """
    lines = text.splitlines()
    start = -1
    for index, line in enumerate(lines):
        if _TICKET_AT.match(line):
            start = index + 1
            break
    if start < 0:
        return None

    found = {"状態": "", "目標": ""}
    for line in lines[start:]:
        if _NEXT_H2.match(line):
            break
        state = _STATE.match(line)
        if state:
            found["状態"] = state.group(2).strip()
            continue
        goal = _GOAL.match(line)
        if goal:
            found["目標"] = goal.group(2).strip()
    return found


def build_ticket_section(row: Row, today: str) -> str:
    """起票時に書き込む「## チケット」節の全文を組み立てる。"""
    return (
        f"{TICKET_HEADING}\n\n"
        f"- 状態: {ticket_state(row)}\n"
        f"- 目標: {ticket_goal(row)}\n"
        f"- 参照: `refs {row.key}`（コミットメッセージの末尾に書く）\n\n"
        f"{HISTORY_HEADING}\n\n"
        f"- {today} 起票 —— {ticket_goal(row)}\n\n"
        f"> {LOCAL_NOTE}\n"
    )


def _insert_ticket(text: str, section: str) -> str:
    """ハブの H1 の直後に「## チケット」節を差し込む。

    Args:
        text: ハブの全文（「## チケット」節はまだ無い）。
        section: `build_ticket_section` の結果。

    Returns:
        差し込んだ全文。H1 が無ければ先頭に置く。

    Note:
        先頭行の BOM（`﻿`）を無視して H1 を探す。Windows のエディタや
        PowerShell の `Out-File -Encoding utf8` は BOM を付けるので、
        これが無いと 1 行目だけ H1 と認識できず、節が題名より上に入る。
    """
    lines = text.splitlines(keepends=True)
    at = 0
    for index, line in enumerate(lines):
        if line.lstrip("﻿").startswith("# "):
            at = index + 1
            break
    while at < len(lines) and lines[at].strip() == "":
        at += 1
    return "".join(lines[:at]) + "\n" + section + "\n" + "".join(lines[at:])


def update_ticket(text: str, row: Row, today: str, reason: str) -> str:
    """既存の「## チケット」節の状態と目標を直し、履歴を 1 行足す。

    Args:
        text: ハブの全文（「## チケット」節がある）。
        row: バックログの 1 行（こちらが正）。
        today: `YYYY-MM-DD`。
        reason: 履歴に残す変更理由。

    Returns:
        書き換えた全文。 **履歴は消さずに追記する** （経緯が消えると
        チケットがただの現在値になり、プロセス管理の役に立たない）。
    """
    lines = text.splitlines(keepends=True)
    plain = text.splitlines()
    start = -1
    for index, line in enumerate(plain):
        if _TICKET_AT.match(line):
            start = index + 1
            break
    if start < 0:
        return _insert_ticket(text, build_ticket_section(row, today))

    end = len(plain)
    history_at = -1
    for index in range(start, len(plain)):
        if _NEXT_H2.match(plain[index]):
            end = index
            break
        if plain[index].startswith("### 履歴"):
            history_at = index

    newline = "\r\n" if text.find("\r\n") >= 0 else "\n"
    for index in range(start, end):
        state = _STATE.match(plain[index])
        if state:
            lines[index] = state.group(1) + ticket_state(row) + newline
            continue
        goal = _GOAL.match(plain[index])
        if goal:
            lines[index] = goal.group(1) + ticket_goal(row) + newline

    entry = f"- {today} {reason} —— 状態 {ticket_state(row)} / {ticket_goal(row)}{newline}"
    if history_at < 0:
        lines.insert(end, f"{newline}{HISTORY_HEADING}{newline}{newline}{entry}")
        return "".join(lines)

    # 最後の履歴項目の直後に足す。節の末尾に足すと、注記（`> …`）の下に
    # 箇条書きが 1 行だけ落ちてリストが割れる
    at = history_at + 1
    for index in range(history_at + 1, end):
        if plain[index].lstrip().startswith("- "):
            at = index + 1
    lines.insert(at, entry)
    return "".join(lines)


@dataclass
class LocalChange:
    """ローカルチケット 1 件に対する変更。

    Attributes:
        key: `S03`。
        path: 書き込む先のハブ。ハブが無ければ None（起票できない）。
        action: `起票` / `更新` / `完了` / `再開`。
        detail: 人に見せる 1 行。
        row: 反映元のバックログの行。
    """

    key: str
    path: Path | None
    action: str
    detail: str
    row: Row


def plan_local(backlog_text: str, root: Path, include_done: bool = False) -> list[LocalChange]:
    """バックログとハブのチケット節を突き合わせ、書き込むべき差分を出す。

    負債（`D##`）はハブを持たないので対象にしない —— 負債表の行そのものが
    チケットであり、写しを作ると二重管理になる。

    Args:
        backlog_text: `docs/backlog.md` の全文。
        root: リポジトリルート。
        include_done: L3 到達済みのスライスも起票するか。

    Returns:
        書き込むべき変更の一覧（空なら同期済み）。
    """
    changes: list[LocalChange] = []
    for row in parse_backlog(backlog_text):
        if row.kind != "slice":
            continue
        path = hub_path(root, row.key)
        if path is None:
            if not row.done or include_done:
                changes.append(
                    LocalChange(row.key, None, "起票", "ハブが無い（先に作る）", row)
                )
            continue

        current = read_ticket(path.read_text(encoding="utf-8"))
        if current is None:
            if not row.done or include_done:
                changes.append(
                    LocalChange(row.key, path, "起票", ticket_goal(row), row)
                )
            continue

        state = ticket_state(row)
        if current.get("状態") == state and current.get("目標") == ticket_goal(row):
            continue
        if state == "完了":
            action = "完了"
        elif current.get("状態") == "完了":
            action = "再開"
        else:
            action = "更新"
        changes.append(
            LocalChange(
                row.key,
                path,
                action,
                f"{current.get('状態') or '—'} → {state} / {ticket_goal(row)}",
                row,
            )
        )
    return changes


def apply_local(changes: list[LocalChange]) -> bool:
    """差分をハブへ書き込む。1 件でも失敗したら False。"""
    ok = True
    today = TODAY()
    for change in changes:
        if change.path is None:
            print(f"NG: {change.key} のハブが無い（`docs/slices/{change.key}-*.md`）")
            ok = False
            continue
        text = change.path.read_text(encoding="utf-8")
        if change.action == "起票":
            written = _insert_ticket(text, build_ticket_section(change.row, today))
        else:
            written = update_ticket(text, change.row, today, change.action)
        change.path.write_text(written, encoding="utf-8")
        print(f"OK: {change.action} {change.key} {change.path}")
    return ok


def _print_local(changes: list[LocalChange]) -> None:
    """ローカルチケットの差分を人が読める形で出す。"""
    counts = {"起票": 0, "更新": 0, "完了": 0, "再開": 0}
    for change in changes:
        counts[change.action] = counts.get(change.action, 0) + 1
    print(
        f"差分: 起票 {counts['起票']} / 更新 {counts['更新']} / "
        f"完了 {counts['完了']} / 再開 {counts['再開']}"
    )
    for change in changes:
        where = change.path.as_posix() if change.path else "ハブ未作成"
        print(f"  {change.action}  {change.key}  {change.detail}  [{where}]")


def _label_names(issue: dict) -> list[str]:
    """gh の JSON からラベル名の一覧を取り出す（文字列と辞書の両方を許す）。"""
    names = []
    for label in issue.get("labels", []) or []:
        names.append(label.get("name", "") if isinstance(label, dict) else str(label))
    return [name for name in names if name]


def plan(backlog_text: str, issues: list[dict], include_done: bool = False) -> Plan:
    """バックログと Issue 一覧から、送信すべき差分を計算する。

    Args:
        backlog_text: `docs/backlog.md` の全文。
        issues: `gh issue list --json number,title,state,labels` の結果。
        include_done: L3 到達・返済済みの行も Issue にするか。

    Returns:
        作成・更新・クローズ・再オープン・取り込み候補に分けた計画。
    """
    result = Plan()
    by_key: dict[str, dict] = {}
    for issue in issues:
        found = _PREFIX.match(issue.get("title", ""))
        if found:
            by_key.setdefault(found.group(1).upper(), issue)
        elif str(issue.get("state", "")).upper() == "OPEN":
            result.pull.append(External(int(issue["number"]), issue.get("title", "")))

    for row in parse_backlog(backlog_text):
        issue = by_key.get(row.key)
        if issue is None:
            if not row.done or include_done:
                result.create.append(row)
            continue

        number = int(issue["number"])
        is_open = str(issue.get("state", "")).upper() == "OPEN"
        if row.done:
            if is_open:
                result.close.append(
                    Change(number, row.key, row.title, row.labels, "バックログで完了")
                )
            continue
        if not is_open:
            result.reopen.append(
                Change(number, row.key, row.title, row.labels, "バックログでは未完了")
            )
            continue

        reasons = []
        if issue.get("title", "").strip() != row.title:
            reasons.append("タイトル")
        if sorted(_label_names(issue)) != sorted(row.labels):
            reasons.append("ラベル")
        if reasons:
            result.update.append(
                Change(number, row.key, row.title, row.labels, " / ".join(reasons))
            )
    return result


def _run_gh(args: list[str]) -> tuple[int, str]:
    """gh を実行して (終了コード, 出力) を返す。"""
    done = subprocess.run(
        ["gh", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return done.returncode, (done.stdout + done.stderr).strip()


# テストから差し替えられるように、実行関数を 1 か所に集める
RUNNER = _run_gh


def _label_args(labels: list[str], flag: str = "--label") -> list[str]:
    args: list[str] = []
    for label in labels:
        args += [flag, label]
    return args


def apply_plan(target: Plan, repo: str) -> bool:
    """計画を GitHub へ反映する。1 つでも失敗したら False を返す。

    Args:
        target: `plan()` の結果。
        repo: `owner/repo`。

    Returns:
        すべての gh 呼び出しが成功したか。
    """
    ok = True
    for row in target.create:
        code, out = RUNNER(
            [
                "issue", "create", "--repo", repo,
                "--title", row.title,
                "--body", build_body(row),
                *_label_args(row.labels),
            ]
        )
        print(f"{'OK' if code == 0 else 'NG'}: create {row.key} {out}")
        ok = ok and code == 0
    for change in target.update:
        code, out = RUNNER(
            [
                "issue", "edit", str(change.number), "--repo", repo,
                "--title", change.title,
                *_label_args(change.labels, "--add-label"),
            ]
        )
        print(f"{'OK' if code == 0 else 'NG'}: update #{change.number} {change.key} {out}")
        ok = ok and code == 0
    for change in target.close:
        code, out = RUNNER(["issue", "close", str(change.number), "--repo", repo])
        print(f"{'OK' if code == 0 else 'NG'}: close #{change.number} {change.key} {out}")
        ok = ok and code == 0
    for change in target.reopen:
        code, out = RUNNER(["issue", "reopen", str(change.number), "--repo", repo])
        print(f"{'OK' if code == 0 else 'NG'}: reopen #{change.number} {change.key} {out}")
        ok = ok and code == 0
    return ok


def _print_plan(target: Plan) -> None:
    """差分を人が読める形で出す（承認を取るための材料）。"""
    print(
        f"差分: 作成 {len(target.create)} / 更新 {len(target.update)} / "
        f"閉じる {len(target.close)} / 再オープン {len(target.reopen)} / "
        f"取り込み候補 {len(target.pull)}"
    )
    for row in target.create:
        print(f"  作成      {row.title}  [{', '.join(row.labels)}]")
    for change in target.update:
        print(f"  更新      #{change.number} {change.title}（{change.reason}）")
    for change in target.close:
        print(f"  閉じる    #{change.number} {change.title}")
    for change in target.reopen:
        print(f"  再オープン #{change.number} {change.title}")
    for item in target.pull:
        print(f"  取り込み? #{item.number} {item.title}")


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。既定は dry-run。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(
        description="バックログと GitHub Issue の差分を出す（既定は送信しない）"
    )
    parser.add_argument("root", nargs="?", default=".", help="リポジトリルート")
    parser.add_argument("--apply", action="store_true", help="差分を GitHub へ反映する")
    parser.add_argument("--include-done", action="store_true", help="L3・返済済みも作る")
    parser.add_argument("--repo", default="", help="owner/repo（省略時はプロファイル）")
    parser.add_argument("--issues-json", default="", help="Issue 一覧の JSON（検証用）")
    args = parser.parse_args(argv)

    root = Path(args.root)
    claude = root / "CLAUDE.md"
    if not claude.is_file():
        print(f"NG: CLAUDE.md がない（{claude}）")
        return 2

    setting = issue_mode.read_mode(claude.read_text(encoding="utf-8"))
    if setting.mode not in ("github", "local"):
        print(
            f"REFUSED: チケット追跡は {setting.mode or '未設定'}。"
            "`/issue github` または `/issue local` で有効化する"
        )
        return 2

    backlog = root / "docs" / "backlog.md"
    if not backlog.is_file():
        print(f"NG: docs/backlog.md がない（{backlog}）")
        return 2

    if setting.mode == "local":
        changes = plan_local(
            backlog.read_text(encoding="utf-8"), root, args.include_done
        )
        _print_local(changes)
        if not args.apply:
            if not changes:
                print("RESULT: 同期済み（書き込むものは無い）")
                return 0
            print("RESULT: 差分あり（未反映）。承認を得てから --apply する")
            return 1
        if not changes:
            print("RESULT: 同期済み（--apply でも書き込むものは無い）")
            return 0
        if apply_local(changes):
            print("RESULT: 反映した")
            return 0
        print("RESULT: 反映に失敗した項目がある")
        return 1

    repo = args.repo or setting.repo or ""
    if not repo:
        print("NG: リポジトリが未設定（プロファイルの `- リポジトリ:` か --repo）")
        return 2

    if args.issues_json:
        issues = json.loads(Path(args.issues_json).read_text(encoding="utf-8"))
    else:
        code, out = RUNNER(
            [
                "issue", "list", "--repo", repo, "--state", "all", "--limit", "200",
                "--json", "number,title,state,labels",
            ]
        )
        if code != 0:
            print(f"NG: gh issue list に失敗した: {out}")
            return 2
        issues = json.loads(out or "[]")

    target = plan(backlog.read_text(encoding="utf-8"), issues, args.include_done)
    _print_plan(target)

    if not args.apply:
        if target.is_empty:
            print("RESULT: 同期済み（送信するものは無い）")
            return 0
        print("RESULT: 差分あり（未送信）。承認を得てから --apply する")
        return 1

    if target.is_empty:
        print("RESULT: 同期済み（--apply でも送信するものは無い）")
        return 0
    if apply_plan(target, repo):
        print("RESULT: 反映した")
        return 0
    print("RESULT: 反映に失敗した項目がある")
    return 1


if __name__ == "__main__":
    sys.exit(main())
