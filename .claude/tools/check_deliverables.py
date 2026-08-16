"""スライスごとの成果物 8 点セットがそろっているかを終了コードで判定する。

8 点セットの正は `.claude/skills/agile-process/deliverables.md`。
このツールは「やり切る」を努力目標ではなく **機械判定** にするためにある。

見るのは `docs/backlog.md` のスライス表。 **成熟度 L1 以上のスライスだけ**
検査する（L0 は着手前なので成果物が無いのが正常）。

検査する項目（1 スライスにつき）:

    要求仕様書         docs/usdm/src/S##-*.html が実在する
    設計書             docs/design/S##-*.md が実在し、図と「判断の記録」を持つ
    テスト仕様書       docs/test-specs/S##-*.md が実在し、正常系（N##）と
                       異常系（E##）の例を 1 行以上ずつ持つ
    テスト結果まとめ   docs/test-reports/S##-*.md が実在し、実測の出力を持つ
    ハブ               docs/slices/S##-*.md が実在する
    マニュアル         docs/manual.md に共通 3 節と `S##` の節がある
    雛形の残り         `{…}` のプレースホルダが残っていない

異常系の例を必須にしているのは、ここが空のまま次へ進むと
**失敗時の振る舞いを実装者がその場で決めてしまう** ため。
空欄は要求の穴であり、埋めずに通してはならない。

実装コードと単体テストの実在は、このツールでは見ない（配置がプロファイル
依存のため）。それらは USDM のトレース表（`build_usdm.py` の
`missing-trace`）が仕様 1 条ごとに検査する —— 2 本で 8 点を覆う。

使い方（前置コマンドはプロファイルの
「.claude/tools/ の Python ツール実行」。例: uv run python）:
    <ツール実行コマンド> .claude/tools/check_deliverables.py
    <ツール実行コマンド> .claude/tools/check_deliverables.py --slice S03
    <ツール実行コマンド> .claude/tools/check_deliverables.py <リポジトリルート>

終了コード:
    0 = 検査したすべてのスライスで成果物がそろっている
    1 = 欠けている成果物がある
    2 = docs/backlog.md が無い、または引数のエラー
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# バックログのスライス表の行（先頭セルが S## のもの）
_SLICE_ROW = re.compile(r"^\|\s*(S[0-9]+)\s*\|(.*)$")
_MATURITY = re.compile(r"L([0-3])")
# 図のフェンス。作図言語の正は `writing-conventions/guides/diagrams.md`
_DIAGRAM = re.compile(r"^```(mermaid|dot|plantuml|graphviz)", re.MULTILINE)
_FENCE = re.compile(r"^```", re.MULTILINE)
# 雛形の穴。日本語を含む `{…}` と、よく使う英数の穴だけを見る
# （コード中の `{}` を誤検出しないための線引き）
_PLACEHOLDER = re.compile(
    r"\{[^{}\n]*[ぁ-んァ-ヶ一-龥][^{}\n]*\}|\{(?:YYYY-MM-DD|name|番号)\}"
)
# マニュアルの共通 3 節（見出しの番号は揺れてよい。言葉で見る）
_MANUAL_SECTIONS = ("環境構築", "実行方法", "テストの実行")
# テスト仕様書の入出力の例。表の行頭で ID を見る（N## = 正常系、E## = 異常系）。
# ID の規約の正は deliverables.md の「入出力と例（正常系・異常系）」。
_NORMAL_CASE = re.compile(r"^\|\s*N[0-9]+\s*\|", re.MULTILINE)
_ERROR_CASE = re.compile(r"^\|\s*E[0-9]+\s*\|", re.MULTILINE)


@dataclass
class Slice:
    """バックログ 1 行から読み取ったスライス。"""

    ident: str
    maturity: int
    line: int


# 充足マトリクスの列（ダッシュボードと共有する。順番が表示順）
ITEMS = ("要求仕様書", "設計書", "テスト仕様", "テスト結果", "マニュアル", "ハブ")


@dataclass
class Result:
    """スライス 1 本の検査結果。

    `missing` は人が読む欠落の説明、`items` は表に並べるための項目別の
    合否（`build_status.py` の充足マトリクスが使う）。
    """

    ident: str
    maturity: int
    missing: list[str] = field(default_factory=list)
    items: dict[str, bool] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.missing


def parse_backlog(text: str) -> list[Slice]:
    """バックログのスライス表から、S## と成熟度を読み取る。

    Args:
        text: `docs/backlog.md` の全文。

    Returns:
        表に現れた順のスライス一覧（雛形の行 `S##` は含めない）。
    """
    slices: list[Slice] = []
    seen: set[str] = set()
    for number, line in enumerate(text.splitlines(), start=1):
        matched = _SLICE_ROW.match(line.strip())
        if not matched:
            continue
        ident = matched.group(1).upper()
        if ident in seen:
            continue
        level = _MATURITY.search(matched.group(2))
        seen.add(ident)
        slices.append(Slice(ident, int(level.group(1)) if level else 0, number))
    return slices


def _find(root: Path, pattern: str) -> Path | None:
    """`docs/...` のグロブに最初に一致した実ファイルを返す。"""
    for path in sorted(root.glob(pattern)):
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None


def _placeholders(text: str) -> list[str]:
    """残っている雛形の穴を返す（重複は除く。順番は現れた順）。"""
    found: list[str] = []
    for hit in _PLACEHOLDER.findall(text):
        value = hit if isinstance(hit, str) else hit[0]
        if value and value not in found:
            found.append(value)
    return found


def check_slice(root: Path, item: Slice, manual: str) -> Result:
    """スライス 1 本の成果物を検査する。

    Args:
        root: リポジトリルート。
        item: 検査対象のスライス。
        manual: `docs/manual.md` の全文（無ければ空文字）。

    Returns:
        欠けている成果物の一覧を持つ Result。
    """
    result = Result(item.ident, item.maturity)
    result.items = {name: False for name in ITEMS}
    if item.maturity < 1:
        return result  # 着手前。成果物が無いのが正常

    ident = item.ident
    requirement = _find(root, f"docs/usdm/src/{ident}-*.html")
    design = _find(root, f"docs/design/{ident}-*.md")
    spec = _find(root, f"docs/test-specs/{ident}-*.md")
    report = _find(root, f"docs/test-reports/{ident}-*.md")
    hub = _find(root, f"docs/slices/{ident}-*.md")

    if requirement is None:
        result.missing.append(f"要求仕様書がない: docs/usdm/src/{ident}-*.html")
    if hub is None:
        result.missing.append(f"ハブ（スライス文書）がない: docs/slices/{ident}-*.md")

    if design is None:
        result.missing.append(f"設計書がない: docs/design/{ident}-*.md")
    else:
        body = design.read_text(encoding="utf-8")
        if not _DIAGRAM.search(body):
            result.missing.append(
                f"設計書に図がない（mermaid / dot / plantuml のいずれか 1 枚）: {design.name}"
            )
        if "判断の記録" not in body:
            result.missing.append(f"設計書に「判断の記録」節がない: {design.name}")

    if spec is None:
        result.missing.append(f"テスト仕様書がない: docs/test-specs/{ident}-*.md")
    else:
        body = spec.read_text(encoding="utf-8")
        if not _NORMAL_CASE.search(body):
            result.missing.append(
                f"テスト仕様書に正常系の例（`N1` の行）がない: {spec.name}"
            )
        if not _ERROR_CASE.search(body):
            result.missing.append(
                f"テスト仕様書に異常系の例（`E1` の行）がない: {spec.name}"
            )

    if report is None:
        result.missing.append(f"テスト結果まとめがない: docs/test-reports/{ident}-*.md")
    elif not _FENCE.search(report.read_text(encoding="utf-8")):
        result.missing.append(
            f"テスト結果まとめに実測の出力（コードブロック）がない: {report.name}"
        )

    if not manual:
        result.missing.append("マニュアルがない: docs/manual.md")
    else:
        for section in _MANUAL_SECTIONS:
            if section not in manual:
                result.missing.append(f"マニュアルに共通の節がない: {section}")
        if not re.search(rf"^#{{1,3}}\s.*{ident}\b", manual, re.MULTILINE):
            result.missing.append(f"マニュアルに {ident} の節がない: docs/manual.md")

    for path in (design, spec, report, hub):
        if path is None:
            continue
        holes = _placeholders(path.read_text(encoding="utf-8"))
        if holes:
            result.missing.append(
                f"雛形のプレースホルダが残っている: {path.name} の {holes[0]}"
                + (f" ほか {len(holes) - 1} 件" if len(holes) > 1 else "")
            )

    # 項目別の合否（欠落の説明にその項目名が現れたら未達とみなす）
    text = " ".join(result.missing)
    result.items = {
        "要求仕様書": "要求仕様書" not in text,
        "設計書": "設計書" not in text,
        "テスト仕様": "テスト仕様" not in text,
        "テスト結果": "テスト結果" not in text,
        "マニュアル": "マニュアル" not in text,
        "ハブ": "ハブ" not in text,
    }
    return result


def main(argv: list[str] | None = None) -> int:
    """コマンドとして実行する。詳しくはモジュールの docstring を参照。"""
    parser = argparse.ArgumentParser(
        description="スライスごとの成果物 8 点セットがそろっているかを検査する"
    )
    parser.add_argument("root", nargs="?", default=".", help="リポジトリルート")
    parser.add_argument("--slice", dest="target", default="", help="対象を 1 本に絞る")
    args = parser.parse_args(argv)

    root = Path(args.root)
    backlog = root / "docs" / "backlog.md"
    if not backlog.is_file():
        print(f"NG: docs/backlog.md がない（{backlog}）")
        return 2

    slices = parse_backlog(backlog.read_text(encoding="utf-8"))
    if args.target:
        target = args.target.upper()
        slices = [s for s in slices if s.ident == target]
        if not slices:
            print(f"NG: {target} がバックログのスライス表にない")
            return 2

    manual_path = root / "docs" / "manual.md"
    manual = manual_path.read_text(encoding="utf-8") if manual_path.is_file() else ""

    results = [check_slice(root, item, manual) for item in slices]
    checked = [r for r in results if r.maturity >= 1]
    for result in checked:
        if result.ok:
            print(f"OK: {result.ident}（L{result.maturity}）8 点セットがそろっている")
        else:
            print(f"NG: {result.ident}（L{result.maturity}）")
            for item in result.missing:
                print(f"    {item}")

    bad = [r for r in checked if not r.ok]
    if not checked:
        print("RESULT: 検査対象のスライスがない（すべて L0 未着手）")
        return 0
    if bad:
        print(f"RESULT: {len(bad)} of {len(checked)} slices NG")
        return 1
    print(f"RESULT: all {len(checked)} slices OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
