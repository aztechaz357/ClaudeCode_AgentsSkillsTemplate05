"""席を外している間に「決まったこと」を、後戻りコストの高い順にまとめる。

規約の正は `.claude/skills/catchup/SKILL.md`。

エージェントに任せると生成の速度が読解の速度を超える。全部を読むのは
早々に不可能になるので、 **後から変えにくいものだけ** を拾って先頭に置く。
判定を人の感覚に任せると毎回ぶれるため、影響度はこのツールが決定論的に
決める（設計思想 8「決定論的な操作を増やす」）。

影響度（`.claude/skills/catchup/SKILL.md` の表と同じ）:

    高  ADR・設計書・要求（USDM）・CLAUDE.md・.claude/ の規約・依存
        —— 後続の全スライスが従うもの
    中  実装・バックログ
    低  テスト・マニュアル・テスト結果まとめ・整理

既読地点は `.steering/last-reviewed`（コミットハッシュ 1 行）。
`.steering/` は gitignore 対象なので、既読は人ごと・環境ごとに独立する。

使い方（前置コマンドはプロファイルの
「.claude/tools/ の Python ツール実行」。例: uv run python）:
    <ツール実行コマンド> .claude/tools/build_digest.py
    <ツール実行コマンド> .claude/tools/build_digest.py --since a20ebed
    <ツール実行コマンド> .claude/tools/build_digest.py --mark

終了コード:
    0 = 追いついている（未読なし）、または --mark に成功した
    1 = 未読がある
    2 = git の実行に失敗した・引数のエラー
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# git log のレコード区切り。件名に現れない制御文字を使う
RECORD = "\x01"
# 影響度「高」を何件まで並べるか（増やすと読む量が増え、絞る意味が消える）
HIGH_LIMIT = 5
# マーカーが無いときに遡る件数
DEFAULT_DEPTH = 20

MARKER = Path(".steering") / "last-reviewed"

# 影響度「高」の判定。上から順に見て最初に当たったものを採る
_HIGH_RULES: tuple[tuple[str, str], ...] = (
    (r"^docs/decisions/ADR-", "ADR"),
    (r"^docs/design/", "設計"),
    (r"^docs/usdm/", "要求"),
    (r"^docs/requirements/", "要求"),
    (r"^CLAUDE\.md$", "規約"),
    (r"^\.claude/", "規約"),
    (
        r"^(pyproject\.toml|package\.json|requirements[^/]*\.txt|uv\.lock|"
        r"Cargo\.toml|go\.mod|pom\.xml|build\.gradle)$",
        "依存",
    ),
)
# 「高」を並べる順（catchup スキルの「読む順」と同じ）。
# _LOW_RULES の後半 3 つがテストの判定に使われる（下の classify 参照）
READ_ORDER = ("ADR", "設計", "要求", "規約", "依存")
# 影響度「低」。判断ではなく結果の記録
_LOW_RULES = (
    r"^docs/manual\.md$",
    r"^docs/test-reports/",
    r"(^|/)tests?/",
    r"(^|/)test_[^/]+$",
    r"_test\.[a-z]+$",
)

_BACKLOG_ROW = re.compile(r"^([+-])\|\s*([SD][0-9]+)\s*\|(.*)$")
_MATURITY = re.compile(r"L([0-3])")


@dataclass
class Commit:
    """git log の 1 レコード。"""

    sha: str
    date: str
    subject: str
    files: list[str] = field(default_factory=list)


@dataclass
class Impact:
    """1 コミットの影響度。

    Attributes:
        level: `高` / `中` / `低`。
        kind: なぜその影響度なのか（`ADR` `設計` `要求` `規約` `依存` `実装` `記録`）。
        path: 代表となるファイル（読む対象として名指しするもの）。
    """

    level: str
    kind: str
    path: str


@dataclass
class BacklogChange:
    """バックログの差分から読んだ動き。

    Attributes:
        maturity: `(S##, 前のレベル, 後のレベル)` の一覧。
        added_debts: 新しく積んだ負債の番号。
        paid_debts: 返した負債（未 → 済）の番号。
    """

    maturity: list[tuple[str, int, int]] = field(default_factory=list)
    added_debts: list[str] = field(default_factory=list)
    paid_debts: list[str] = field(default_factory=list)


def parse_log(text: str) -> list[Commit]:
    """`git log --pretty=format:%x01%H%x09%ad%x09%s --name-only` を読む。

    Args:
        text: git log の出力。

    Returns:
        新しい順のコミット（出力の順のまま）。
    """
    commits: list[Commit] = []
    for chunk in text.split(RECORD):
        lines = [line for line in chunk.splitlines() if line.strip()]
        if not lines:
            continue
        head = lines[0].split("\t")
        if len(head) < 3:
            continue
        commits.append(Commit(head[0], head[1], head[2], lines[1:]))
    return commits


def classify(commit: Commit) -> Impact:
    """コミットの影響度を決める（同じ入力なら必ず同じ結果）。

    Args:
        commit: 判定するコミット。

    Returns:
        影響度と、その根拠になった種別・代表ファイル。
    """
    for pattern, kind in _HIGH_RULES:
        for path in commit.files:
            if re.search(pattern, path):
                return Impact("高", kind, path)

    interesting = [
        path
        for path in commit.files
        if not any(re.search(pattern, path) for pattern in _LOW_RULES)
        and not path.startswith("docs/")
    ]
    if interesting:
        return Impact("中", "実装", interesting[0])
    if any(path.startswith("docs/backlog.md") for path in commit.files):
        return Impact("中", "進捗", "docs/backlog.md")
    if any(re.search(pattern, path) for pattern in _LOW_RULES[2:] for path in commit.files):
        return Impact("低", "テスト", commit.files[0])
    return Impact("低", "記録", commit.files[0] if commit.files else "")


def parse_backlog_diff(text: str) -> BacklogChange:
    """`git diff -- docs/backlog.md` から成熟度と負債の動きを読む。

    Args:
        text: unified diff の全文。

    Returns:
        成熟度の変化・増えた負債・返した負債。
    """
    before: dict[str, str] = {}
    after: dict[str, str] = {}
    for line in text.splitlines():
        matched = _BACKLOG_ROW.match(line.strip())
        if not matched:
            continue
        sign, key, rest = matched.group(1), matched.group(2).upper(), matched.group(3)
        (before if sign == "-" else after)[key] = rest

    change = BacklogChange()
    for key, rest in after.items():
        if key.startswith("S"):
            new = _MATURITY.search(rest)
            old = _MATURITY.search(before.get(key, ""))
            if new and old and new.group(1) != old.group(1):
                change.maturity.append((key, int(old.group(1)), int(new.group(1))))
        elif key not in before:
            change.added_debts.append(key)
        elif "済" in rest and "済" not in before[key]:
            change.paid_debts.append(key)
    return change


def build(commits: list[Commit], change: BacklogChange) -> str:
    """ダイジェスト本文を組み立てる。

    Args:
        commits: 未読のコミット（新しい順）。
        change: バックログの差分から読んだ動き。

    Returns:
        報告にそのまま貼れる本文。低い影響度は件数だけにする。
    """
    graded = [(commit, classify(commit)) for commit in commits]
    # 「高」の中の順は読む順（catchup スキル）に従う。ADR がずれていると
    # 設計も要求も全部ずれるので、日付より種別を優先して並べる
    high = sorted(
        (pair for pair in graded if pair[1].level == "高"),
        key=lambda pair: READ_ORDER.index(pair[1].kind),
    )
    middle = [pair for pair in graded if pair[1].level == "中"]
    tests = [pair for pair in graded if pair[1].kind == "テスト"]
    low = [pair for pair in graded if pair[1].level == "低" and pair[1].kind != "テスト"]

    newest, oldest = commits[0], commits[-1]
    lines = [
        f"未読: {len(commits)} コミット"
        f"（{oldest.sha[:7]} → {newest.sha[:7]}・{oldest.date} 〜 {newest.date}）",
        "",
        f"後戻りが高い判断 {len(high)} 件",
    ]
    if not high:
        lines.append("  （なし。実装と記録だけが動いている）")
    for commit, impact in high[:HIGH_LIMIT]:
        lines.append(f"  [{impact.kind}] {commit.subject}  —— {impact.path}")
    if len(high) > HIGH_LIMIT:
        lines.append(f"  … 他 {len(high) - HIGH_LIMIT} 件（多すぎる。分けて読む）")

    lines.append("")
    lines.append(
        f"その他: 実装 {len(middle)} 件 / テスト {len(tests)} 件 / 文書 {len(low)} 件"
    )
    if change.maturity:
        moved = " / ".join(f"{key} L{old} → L{new}" for key, old, new in change.maturity)
        lines.append(f"成熟度: {moved}")
    if change.added_debts or change.paid_debts:
        lines.append(
            f"負債: 増 {len(change.added_debts)} 件"
            f"（{', '.join(change.added_debts) or 'なし'}）/ "
            f"返 {len(change.paid_debts)} 件"
            f"（{', '.join(change.paid_debts) or 'なし'}）"
        )

    lines.append("")
    if high:
        first = high[0][1]
        lines.append(f"次に読むなら: {first.path}（{first.kind}。ここがずれると後続が全部ずれる）")
    else:
        lines.append("次に読むなら: なし（判断は増えていない。/status で現在地だけ確認する）")
    return "\n".join(lines)


def _run_git(args: list[str]) -> tuple[int, str]:
    """git を実行して (終了コード, 標準出力) を返す。"""
    done = subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return done.returncode, done.stdout.strip()


# テストから差し替えられるように、実行関数を 1 か所に集める
RUNNER = _run_git


def _resolve_since(root: Path, given: str) -> str:
    """起点の ref を決める（引数 → マーカー → 直近 N 件）。"""
    if given:
        return given
    marker = root / MARKER
    if marker.is_file():
        text = marker.read_text(encoding="utf-8").strip()
        if text:
            return text
    return f"HEAD~{DEFAULT_DEPTH}"


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。未読の有無を終了コードで返す。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(
        description="決まったことを後戻りコストの高い順にまとめる"
    )
    parser.add_argument("root", nargs="?", default=".", help="リポジトリルート")
    parser.add_argument("--since", default="", help="起点の ref（省略時はマーカー）")
    parser.add_argument("--mark", action="store_true", help="既読地点を HEAD に進める")
    args = parser.parse_args(argv)

    root = Path(args.root)
    since = _resolve_since(root, args.since)
    span = f"{since}..HEAD"

    code, log = RUNNER(
        [
            "-C", str(root), "log", "--no-merges", "--date=short",
            f"--pretty=format:{RECORD}%H%x09%ad%x09%s", "--name-only", span,
        ]
    )
    if code != 0:
        # 浅いリポジトリでは HEAD~N が存在しない。全履歴に落として読み直す
        code, log = RUNNER(
            [
                "-C", str(root), "log", "--no-merges", "--date=short",
                f"--pretty=format:{RECORD}%H%x09%ad%x09%s", "--name-only",
                f"-{DEFAULT_DEPTH}",
            ]
        )
        if code != 0:
            print(f"NG: git log に失敗した（{span}）")
            return 2

    commits = parse_log(log)
    if not commits:
        head_code, head = RUNNER(["-C", str(root), "rev-parse", "--short", "HEAD"])
        print(f"追いついています（HEAD: {head if head_code == 0 else '不明'}）")
        return 0

    _, diff = RUNNER(["-C", str(root), "diff", span, "--", "docs/backlog.md"])
    print(build(commits, parse_backlog_diff(diff)))

    if args.mark:
        code, head = RUNNER(["-C", str(root), "rev-parse", "--short", "HEAD"])
        if code != 0:
            print("NG: HEAD を解決できなかった（既読地点は進めていない）")
            return 2
        marker = root / MARKER
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(head + "\n", encoding="utf-8")
        print(f"\n既読地点を {head} に進めた（{marker}）")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
