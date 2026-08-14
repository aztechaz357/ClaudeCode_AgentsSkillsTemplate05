"""設計書に書かれた契約式（主張）を集め、台帳と差分を出す。

規約の正は `.claude/skills/verifiable-claims/SKILL.md`。

**このツールがあるのは、人が「正しいか」を 30 秒で判断できるようにするため。**
散文は 1 文ごとに「信じるか自分で再導出するか」しか選択肢が無く、量が増えると
読まれなくなる。契約式は攻撃点（反例）が明示されるので、読者は
「反証しようとして失敗する」ことで理解できる。

集めるのは `docs/design/S##-*.md` の「## 主張（契約式）」節にある表だけ。
**書く場所は分散・読む場所は 1 枚** にするための道具であり、
主張の正はあくまで各設計書（ここに書き写さない）。

使い方（前置コマンドはプロファイルの
「.claude/tools/ の Python ツール実行」。例: uv run python）:
    <ツール実行コマンド> .claude/tools/build_claims.py            # 台帳（/status 用）
    <ツール実行コマンド> .claude/tools/build_claims.py --diff     # 既読地点からの差分（/catchup 用）
    <ツール実行コマンド> .claude/tools/build_claims.py --mark     # いまの状態を既読にする

終了コード:
    台帳:  0 = 未証明（⊬）が 0 件、1 = 未証明あり、2 = エラー
    --diff: 0 = 変化なし、1 = 変化あり（弱まった・消えた・追加）、2 = エラー
            **未証明のまま は「変化」に数えない** —— 据え置きを差分と呼ぶと
            毎回赤が出て、差分そのものが読まれなくなる（ただし一覧には出す）

`--mark` の既読地点は `.steering/claims.json`（`.steering/` は gitignore 対象）。
**人ごと・環境ごとに独立する** —— 誰かが読んだことは、他の人の既読にならない。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

# 主張の節。見出しの言葉だけで探す（括弧の揺れを許す）
SECTION_WORD = "主張"
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_ROW = re.compile(r"^\|(.+)\|\s*$")
# 表の区切り行（`|---|---|`）
_SEPARATOR = re.compile(r"^[\s|:-]+$")
# 主張の ID。事前 P / 事後 Q / 不変 I の 3 種だけ（増やさない）
_CID = re.compile(r"^[PQI][0-9]+$")

PROVED = "⊢"
UNPROVED = "⊬"

_CASES = re.compile(r"^\*\*場合\*\*\s*[:：]\s*(.*)$")
_COUNTER = re.compile(r"^\*\*反例\*\*\s*[:：]\s*(.*)$")

SNAPSHOT = Path(".steering") / "claims.json"


@dataclass
class Claim:
    """契約式 1 本。

    Attributes:
        slice_key: `S03`。設計書のファイル名から取る。
        cid: `P1` / `Q1` / `I1`（事前 / 事後 / 不変）。
        kind: `事前` / `事後` / `不変`。
        statement: 論理式（小さな固定語彙・1 行）。
        assertion: 同じ内容の assert 風の 1 行（記号が読めなくても分かる形）。
        proved: `⊢` なら True、`⊬` なら False。
        evidence: 根拠（テスト名。未証明なら理由や負債 ID）。
    """

    slice_key: str
    cid: str
    kind: str
    statement: str
    assertion: str
    proved: bool
    evidence: str

    @property
    def mark(self) -> str:
        return PROVED if self.proved else UNPROVED

    @property
    def key(self) -> str:
        """主張の同一性（スライス跨ぎで衝突しない）。"""
        return f"{self.slice_key}.{self.cid}"


def _section_lines(text: str) -> list[str]:
    """「## 主張…」節の行を返す。節が無ければ空。"""
    lines = text.splitlines()
    start = -1
    level = 0
    for index, line in enumerate(lines):
        matched = _HEADING.match(line)
        if not matched:
            continue
        if start < 0:
            if SECTION_WORD in matched.group(2):
                start = index + 1
                level = len(matched.group(1))
            continue
        if len(matched.group(1)) <= level:
            return lines[start:index]
    return lines[start:] if start >= 0 else []


def _cells(line: str) -> list[str]:
    """表の 1 行をセルに割る。"""
    matched = _ROW.match(line.strip())
    if not matched or _SEPARATOR.match(line.strip()):
        return []
    return [cell.strip().strip("`") for cell in matched.group(1).split("|")]


def parse_claims(text: str, slice_key: str) -> list[Claim]:
    """設計書 1 枚から主張の表を読み取る。

    Args:
        text: 設計書の全文。
        slice_key: `S03`。

    Returns:
        表に現れた順の主張。節が無ければ空（エラーにしない —— 主張を
        まだ書いていない設計書は正常な途中状態）。
    """
    claims: list[Claim] = []
    for line in _section_lines(text):
        cells = _cells(line)
        if len(cells) < 6 or not _CID.match(cells[0]):
            continue
        claims.append(
            Claim(
                slice_key=slice_key,
                cid=cells[0],
                kind=cells[1],
                statement=cells[2],
                assertion=cells[3],
                proved=PROVED in cells[4],
                evidence=cells[5],
            )
        )
    return claims


def _first_match(text: str, pattern: re.Pattern[str]) -> str:
    for line in text.splitlines():
        found = pattern.match(line.strip())
        if found:
            return found.group(1).strip()
    return ""


def parse_cases(text: str) -> str:
    """場合分けの 1 行（`in = ∅ ⊔ … ⊔ …`）。無ければ空。"""
    return _first_match(text, _CASES)


def parse_counterexample(text: str) -> str:
    """反例の形の 1 行。無ければ空。"""
    return _first_match(text, _COUNTER)


def collect(root: Path) -> list[Claim]:
    """`docs/design/S##-*.md` を全部読んで主張を集める。"""
    found: list[Claim] = []
    for path in sorted((root / "docs" / "design").glob("*.md")):
        key = path.stem.split("-")[0].upper()
        found += parse_claims(path.read_text(encoding="utf-8"), key)
    return found


def diff(before: list[Claim], after: list[Claim]) -> dict[str, list[Claim]]:
    """既読地点からの変化を 4 つに分ける。

    Args:
        before: 既読地点の主張。
        after: いまの主張。

    Returns:
        `追加` / `弱まった` / `消えた` / `未証明のまま` の 4 つ。

    Note:
        **弱まった（⊢ → ⊬）と消えた** を独立させているのは、この 2 つが
        散文の差分では絶対に気づけない後退だから。行が増えたことには
        気づけても、保証が減ったことには気づけない。
    """
    old = {claim.key: claim for claim in before}
    new = {claim.key: claim for claim in after}

    result: dict[str, list[Claim]] = {
        "追加": [],
        "弱まった": [],
        "消えた": [],
        "未証明のまま": [],
    }
    for key, claim in new.items():
        previous = old.get(key)
        if previous is None:
            result["追加"].append(claim)
        elif claim.proved and not previous.proved:
            result["追加"].append(claim)
        elif previous.proved and not claim.proved:
            result["弱まった"].append(claim)
        elif not claim.proved:
            result["未証明のまま"].append(claim)
    for key, claim in old.items():
        if key not in new:
            result["消えた"].append(claim)
    return result


def render_ledger(claims: list[Claim]) -> str:
    """主張の一覧（`/status` に載せる形）。"""
    if not claims:
        return "主張: 0 件（設計書に「## 主張（契約式）」節がまだ無い）"

    proved = [claim for claim in claims if claim.proved]
    lines = [
        f"主張: {len(claims)} 件（証明済み {PROVED} {len(proved)} / "
        f"未証明 {UNPROVED} {len(claims) - len(proved)}）",
        "",
    ]
    current = ""
    for claim in claims:
        if claim.slice_key != current:
            current = claim.slice_key
            lines.append(f"[{current}]")
        lines.append(
            f"  {claim.mark} {claim.cid} {claim.kind}  {claim.statement}"
            + (f"   … {claim.evidence}" if not claim.proved else "")
        )
    return "\n".join(lines)


# 「変化」に数えるもの。`未証明のまま` は据え置きなので入れない
# （変化していないものを差分と呼ぶと、毎回赤が出て差分が読まれなくなる）
CHANGED = ("弱まった", "消えた", "追加")


def changed_count(found: dict[str, list[Claim]]) -> int:
    """既読地点から実際に変化した主張の数。"""
    return sum(len(found[name]) for name in CHANGED)


def render_diff(found: dict[str, list[Claim]]) -> str:
    """既読地点からの差分（`/catchup` に載せる形）。"""
    labels = {
        "弱まった": f"弱まった保証（{PROVED} → {UNPROVED}。最優先で見る）",
        "消えた": "消えた保証（主張ごと無くなった）",
        "追加": "追加された保証",
        "未証明のまま": "未証明のまま（据え置き。変化ではないが放置の指標）",
    }

    def block(name: str) -> list[str]:
        items = found[name]
        rows = [f"{labels[name]}: {len(items)} 件"]
        for claim in items:
            rows.append(
                f"  {claim.mark} {claim.key} {claim.statement}"
                + (f"   … {claim.evidence}" if not claim.proved else "")
            )
        return rows

    lines: list[str] = []
    if changed_count(found) == 0:
        lines.append("主張の差分なし（既読地点から保証は変わっていない）")
    else:
        for name in CHANGED:
            lines += block(name)
    if found["未証明のまま"]:
        lines += block("未証明のまま")
    return "\n".join(lines)


def load_snapshot(root: Path) -> list[Claim] | None:
    """既読地点の主張。まだ無ければ None（初回はエラーにしない）。"""
    path = root / SNAPSHOT
    if not path.is_file():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [Claim(**item) for item in raw]


def save_snapshot(root: Path, claims: list[Claim]) -> Path:
    """いまの主張を既読地点として書き出す。"""
    path = root / SNAPSHOT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(claim) for claim in claims], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。既定は台帳。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(
        description="設計書の契約式（主張）を集めて台帳と差分を出す"
    )
    parser.add_argument("root", nargs="?", default=".", help="リポジトリルート")
    parser.add_argument("--diff", action="store_true", help="既読地点からの差分を出す")
    parser.add_argument("--mark", action="store_true", help="いまの状態を既読にする")
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"NG: ルートがない（{root}）")
        return 2

    claims = collect(root)

    if args.mark:
        path = save_snapshot(root, claims)
        print(f"既読にした: {path}（主張 {len(claims)} 件）")
        return 0

    if args.diff:
        before = load_snapshot(root)
        if before is None:
            print("既読地点が無い（初回）。いまの全主張を「追加」として出す。")
            before = []
        found = diff(before, claims)
        print(render_diff(found))
        return 1 if changed_count(found) else 0

    print(render_ledger(claims))
    return 1 if any(not claim.proved for claim in claims) else 0


if __name__ == "__main__":
    sys.exit(main())
