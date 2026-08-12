"""バックログと GitHub Issue の差分を計算し、承認のうえで反映する。

規約の正は `.claude/skills/issue-tracking/SKILL.md`。
**進捗の正は `docs/backlog.md`** で、Issue はその写し。したがって同期は
バックログ → Issue の一方向で、逆流（Issue から成熟度を書き戻す）はしない。

対応付けは **Issue タイトルの接頭辞（`S##:` / `D##:`）だけ** で行う。
対応表のファイルを別に持たないので、実物とずれる余地が無い。

既定は **dry-run** （差分を出すだけで GitHub に触らない）。
`--apply` を付けたときだけ `gh` を呼ぶ。外部への書き込みは取り消しにくいので、
エージェントは差分を提示して承認を得てから `--apply` する（絶対ルール 4）。

使い方（前置コマンドはプロファイルの
「.claude/tools/ の Python ツール実行」。例: uv run python）:
    <ツール実行コマンド> .claude/tools/sync_issues.py
    <ツール実行コマンド> .claude/tools/sync_issues.py --apply
    <ツール実行コマンド> .claude/tools/sync_issues.py --include-done
    <ツール実行コマンド> .claude/tools/sync_issues.py --issues-json <path>   # 検証用

終了コード:
    0 = 差分なし（または --apply がすべて成功した）
    1 = 差分あり（未送信）、または --apply の途中で gh が失敗した
    2 = 使用: off、CLAUDE.md / バックログが無い、リポジトリ未設定、引数のエラー
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
    if setting.mode != "on":
        print(f"REFUSED: Issue 追跡は {setting.mode or '未設定'}。`/issue on` で有効化する")
        return 2

    repo = args.repo or setting.repo or ""
    if not repo:
        print("NG: リポジトリが未設定（プロファイルの `- リポジトリ:` か --repo）")
        return 2

    backlog = root / "docs" / "backlog.md"
    if not backlog.is_file():
        print(f"NG: docs/backlog.md がない（{backlog}）")
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
