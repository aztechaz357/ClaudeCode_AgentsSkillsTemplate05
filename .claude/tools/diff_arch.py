"""設計書の図と、実装から起こした図を突き合わせて乖離を可視化する。

規約の正は `.claude/skills/architecture-drift/SKILL.md`。

設計書の図は「こうしたい」、`build_arch.py` の図は「こうなっている」。
両者は放っておくと必ずずれる —— しかも **ずれた瞬間には誰も気づかない** 。
このツールは 2 つの図を集合として比較し、3 種類の差を 1 枚に色分けする。

    実線（黒） 一致            —— 設計どおり
    破線（灰） 設計にだけある  —— まだ実装していない
    太線（黄） 実装にだけある  —— 設計に無い構造が増えている（要注意）

比較を成立させるため、設計書の図は **ノード id をモジュールパス**
（`application.filter`）で書く規約にしている（表示名は日本語でよい。
正: `.claude/skills/functional-design/`）。id が規約どおりでない図は
「設計にだけある」に倒れるので、差分を見れば規約違反にも気づける。

使い方（前置コマンドはプロファイルの
「.claude/tools/ の Python ツール実行」。例: uv run python）:
    <ツール実行コマンド> .claude/tools/diff_arch.py <ソースルート>
    <ツール実行コマンド> .claude/tools/diff_arch.py src/pkg --design docs/design --out docs/architecture-diff.md

終了コード:
    0 = 乖離なし（設計と実装が一致している）
    1 = 乖離あり
    2 = ソースルートが無い・設計書または図が 1 枚も無い・引数のエラー
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_arch

_FENCE = re.compile(r"```mermaid(.*?)```", re.DOTALL)
# `id["表示名"]` / `id(表示名)` / `id[["契約"]]` のノード宣言
_NODE = re.compile(r"([\w.]+)\s*[\[\({]")
# 表示名・矢印ラベルは id ではないので、辺を読む前に落とす
_LABEL = re.compile(r"\[+[^\]]*\]+|\(+[^)]*\)+|\{+[^}]*\}+")
_ARROW_LABEL = re.compile(r"\|[^|]*\|")
# `-->` `-.->` `--->` `==>`（ラベルを落とした後の骨組みを分割する）
_ARROW = re.compile(r"\s*(?:-\.?-*>|={2,}>)\s*")
_ID = re.compile(r"^[\w.]+$")
_SKIP = ("subgraph", "end", "flowchart", "graph", "classDef", "class ", "linkStyle", "style ")


@dataclass
class Diff:
    """設計と実装の差。

    Attributes:
        matched: 両方にある依存。
        design_only: 設計にあるが実装に無い依存（未実装）。
        impl_only: 実装にあるが設計に無い依存（黙って増えた構造）。
        missing_nodes: 設計にあるが実装に無いモジュール。
        extra_nodes: 実装にあるが設計に無いモジュール。
        violations: 逆流している依存（`build_arch.violations`）。
    """

    matched: list[tuple[str, str]] = field(default_factory=list)
    design_only: list[tuple[str, str]] = field(default_factory=list)
    impl_only: list[tuple[str, str]] = field(default_factory=list)
    missing_nodes: list[str] = field(default_factory=list)
    extra_nodes: list[str] = field(default_factory=list)
    violations: list[build_arch.Edge] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """乖離が無いか（ノードの増減は情報として出すが合否に含めない）。"""
        return not (self.design_only or self.impl_only or self.violations)


def parse_mermaid(text: str) -> build_arch.Graph:
    """Markdown 内の Mermaid 図からノードと辺を読む。

    Args:
        text: 設計書の全文（フェンスの外は無視する）。

    Returns:
        図に書かれたノード id と辺。図が無ければ空のグラフ。

    Note:
        設計書は `a["表示名"] --> b["表示名"]` や `a -.->|契約| b` の形で
        書かれる（雛形がその形）。表示名と矢印ラベルを先に落としてから
        辺を読まないと、実物と比較したときに全部「設計にだけある」へ倒れる。
    """
    graph = build_arch.Graph()
    for block in _FENCE.findall(text):
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped or any(stripped.startswith(word) for word in _SKIP):
                continue
            for node in _NODE.findall(stripped):
                graph.nodes.add(node)

            skeleton = _ARROW_LABEL.sub(" ", _LABEL.sub(" ", stripped))
            parts = [part.strip() for part in _ARROW.split(skeleton) if part.strip()]
            if len(parts) < 2:
                continue
            for source, target in zip(parts, parts[1:]):
                if _ID.match(source) and _ID.match(target):
                    graph.nodes.add(source)
                    graph.nodes.add(target)
                    graph.edges.add((source, target))
    return graph


def diff(designed: build_arch.Graph, actual: build_arch.Graph) -> Diff:
    """設計の図と実装の図を集合として比較する。

    Args:
        designed: 設計書から読んだ図。
        actual: 実装から起こした図。

    Returns:
        一致・設計のみ・実装のみに分けた差と、逆流の一覧。
    """
    return Diff(
        matched=sorted(designed.edges & actual.edges),
        design_only=sorted(designed.edges - actual.edges),
        impl_only=sorted(actual.edges - designed.edges),
        missing_nodes=sorted(designed.nodes - actual.nodes),
        extra_nodes=sorted(actual.nodes - designed.nodes),
        violations=build_arch.violations(actual),
    )


def to_mermaid(result: Diff) -> str:
    """差分を 1 枚の Mermaid にする（色に意味を持たせる）。

    Args:
        result: `diff()` の結果。

    Returns:
        凡例つきの Markdown。 **色だけでは伝わらない** ので凡例を必ず添える。
    """
    lines = [
        "# 設計と実装の差（生成物）",
        "",
        "> `diff_arch.py` が設計書の図と実装の import を突き合わせた結果。",
        "> **手で編集しない** 。直すのは設計書か実装のどちらか。",
        "",
        "## 凡例",
        "",
        "| 線 | 意味 | どうするか |",
        "|---|---|---|",
        "| 実線 | 一致している | なし |",
        "| 破線 | 設計にだけある（未実装） | 実装するか、設計から落とす |",
        "| 太線 | **実装にだけある**（設計に無い構造） | 設計書に書くか、実装を戻す |",
        "| 二重線 | **逆流**（内向きでない依存） | 直す（L3 では 0 件が条件） |",
        "",
        "```mermaid",
        "flowchart TD",
    ]
    bad = {(edge.source, edge.target) for edge in result.violations}
    index = 0
    for source, target in result.matched:
        lines.append(f"  {source} --> {target}")
        index += 1
    for source, target in result.design_only:
        lines.append(f"  {source} -.->|未実装| {target}")
        lines.append(f"  linkStyle {index} stroke:#999,stroke-dasharray:4")
        index += 1
    for source, target in result.impl_only:
        label = "逆流" if (source, target) in bad else "設計に無い"
        color = "#d33" if (source, target) in bad else "#e6a700"
        lines.append(f"  {source} ==>|{label}| {target}")
        lines.append(f"  linkStyle {index} stroke:{color},stroke-width:3px")
        index += 1
    lines.append("```")

    lines += ["", "## 差の一覧", ""]
    lines.append(f"- 一致: {len(result.matched)} 本")
    lines.append(
        f"- 設計にだけある（未実装）: {len(result.design_only)} 本"
        + ("".join(f"\n  - `{a}` → `{b}`" for a, b in result.design_only) or "")
    )
    lines.append(
        f"- **実装にだけある（設計に無い）**: {len(result.impl_only)} 本"
        + ("".join(f"\n  - `{a}` → `{b}`" for a, b in result.impl_only) or "")
    )
    lines.append(
        f"- 逆流: {len(result.violations)} 本"
        + ("".join(f"\n  - `{e.source}` → `{e.target}`" for e in result.violations) or "")
    )
    if result.missing_nodes:
        lines.append(f"- 設計にあるが実装に無いモジュール: {', '.join(result.missing_nodes)}")
    if result.extra_nodes:
        lines.append(f"- 実装にあるが設計に無いモジュール: {', '.join(result.extra_nodes)}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。乖離の有無を終了コードで返す。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description="設計書の図と実装の依存を突き合わせる")
    parser.add_argument("root", help="ソースルート（プロファイルの値を使う）")
    parser.add_argument("--design", default="docs/design", help="設計書のファイルまたはディレクトリ")
    parser.add_argument("--out", default="docs/architecture-diff.md", help="出力先の Markdown")
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"NG: ソースルートがない（{root}）")
        return 2

    design_path = Path(args.design)
    if design_path.is_file():
        documents = [design_path]
    elif design_path.is_dir():
        documents = sorted(design_path.glob("*.md"))
    else:
        documents = []
    if not documents:
        print(f"NG: 設計書がない（{design_path}）")
        return 2

    designed = build_arch.Graph()
    for document in documents:
        graph = parse_mermaid(document.read_text(encoding="utf-8"))
        designed.nodes |= graph.nodes
        designed.edges |= graph.edges
    if not designed.edges:
        print(f"NG: 設計書に図（mermaid の依存）が 1 つも無い（{design_path}）")
        return 2

    actual = build_arch.build_graph(root)
    if not actual.nodes:
        print(f"NG: `.py` が 1 つも無い（{root}）。Python 以外は未対応")
        return 2

    result = diff(designed, actual)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_mermaid(result), encoding="utf-8")

    print(
        f"一致 {len(result.matched)} 本 / 未実装 {len(result.design_only)} 本 / "
        f"実装にだけある {len(result.impl_only)} 本 / 逆流 {len(result.violations)} 本 → {out}"
    )
    for source, target in result.impl_only:
        print(f"NG: 実装にだけある依存 {source} → {target}")
    for edge in result.violations:
        print(f"NG: 逆流 {edge.source} → {edge.target}")
    if result.is_clean:
        print("RESULT: 設計と実装は一致している")
        return 0
    print("RESULT: 乖離あり（設計書か実装のどちらかを直す）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
