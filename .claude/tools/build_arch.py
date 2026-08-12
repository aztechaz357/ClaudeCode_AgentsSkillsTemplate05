"""実装の import から、実際の依存図（Mermaid）を生成する。

規約の正は `.claude/skills/architecture-drift/SKILL.md`、
層と依存の正は `.claude/skills/layered-architecture/SKILL.md`。

**設計書の図は「こうしたい」を描いたもの** で、実装がそのとおりとは限らない。
この乖離は普通、動かなくなって初めて気づく。このツールは実装側の図を
機械的に起こし、目で見える形にする（比較は `diff_arch.py`）。

ノード id は **層を含むモジュールパス**（`application.filter`）。
設計書の図も同じ id で書く規約にしてあるので、集合として比較できる。

対応言語は Python（`.py`）のみ。他言語のプロジェクトでは
「未対応」として扱う（推測でパースしない）。

使い方（前置コマンドはプロファイルの
「.claude/tools/ の Python ツール実行」。例: uv run python）:
    <ツール実行コマンド> .claude/tools/build_arch.py <ソースルート>
    <ツール実行コマンド> .claude/tools/build_arch.py src/pkg --out docs/architecture-actual.md

終了コード:
    0 = 生成でき、逆流が無い
    1 = 生成できたが逆流がある（内向きでない依存）
    2 = ソースルートが無い・`.py` が 1 つも無い・引数のエラー
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 層の名前（ディレクトリ名）。プロファイルの層構成表と同じ言葉を使う
LAYERS = ("presentation", "application", "domain", "infrastructure")

# 各層が import してよい層（`layered-architecture` の表と同じ）。
# infrastructure が application を指してよいのは「契約の実装」だけだが、
# 契約かどうかはパスからは分からないので、ここでは許可して図の色で示す
ALLOWED: dict[str, set[str]] = {
    "presentation": {"presentation", "application", "domain"},
    "application": {"application", "domain"},
    "domain": {"domain"},
    "infrastructure": {"infrastructure", "domain", "application"},
}

EXCLUDE_DIRS = {"__pycache__", ".venv", ".git", "build", "dist", "node_modules", "test", "tests"}


@dataclass(frozen=True)
class Edge:
    """依存 1 本（`source` が `target` を import している）。"""

    source: str
    target: str


@dataclass
class Graph:
    """実装から起こした依存グラフ。

    Attributes:
        nodes: モジュール id（`application.filter`）の集合。
        edges: 内部モジュール同士の依存。
    """

    nodes: set[str] = field(default_factory=set)
    edges: set[tuple[str, str]] = field(default_factory=set)


def parse_imports(source: str) -> list[str]:
    """Python の原文から import 先のモジュール名を読む。

    Args:
        source: `.py` の全文。

    Returns:
        `from a.b import c` の `a.b` と `import a.b` の `a.b`。
        構文が壊れているファイルは空リスト（全体を落とさない）。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                found.append(node.module)
        elif isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
    return found


def module_id(path: Path, root: Path) -> str:
    """ファイルパスをモジュール id にする（`application/filter.py` → `application.filter`）。"""
    relative = path.relative_to(root).with_suffix("")
    parts = [part for part in relative.parts if part != "__init__"]
    return ".".join(parts)


def layer_of(module: str) -> str:
    """モジュール id の層（先頭の要素）。層に属さなければ空文字。"""
    head = module.split(".")[0]
    return head if head in LAYERS else ""


def _match(imported: str, nodes: set[str]) -> str:
    """import 先の文字列を、内部ノード id に対応づける。

    パッケージ名（`pkg.application.filter`）が前に付いていても、
    末尾がノード id と一致すれば同じモジュールとみなす。
    """
    if imported in nodes:
        return imported
    for node in nodes:
        if imported.endswith("." + node):
            return node
    return ""


def build_graph(root: Path) -> Graph:
    """ソースルート配下の `.py` から依存グラフを組み立てる。

    Args:
        root: ソースルート（この下の第 1 階層が層になる）。

    Returns:
        内部モジュールだけを含むグラフ（標準ライブラリ・外部依存は辺にしない）。
    """
    files = [
        path
        for path in sorted(root.rglob("*.py"))
        if not EXCLUDE_DIRS & set(path.relative_to(root).parts)
    ]
    graph = Graph()
    sources: dict[str, str] = {}
    for path in files:
        node = module_id(path, root)
        if not node:
            continue
        graph.nodes.add(node)
        sources[node] = path.read_text(encoding="utf-8", errors="replace")

    for node, text in sources.items():
        for imported in parse_imports(text):
            target = _match(imported, graph.nodes)
            if target and target != node:
                graph.edges.add((node, target))
    return graph


def violations(graph: Graph) -> list[Edge]:
    """内向きでない依存（逆流）を返す。

    Args:
        graph: `build_graph` の結果。

    Returns:
        層のルールに反する辺（層に属さないモジュールは対象外）。
    """
    found: list[Edge] = []
    for source, target in sorted(graph.edges):
        source_layer, target_layer = layer_of(source), layer_of(target)
        if not source_layer or not target_layer:
            continue
        if target_layer not in ALLOWED[source_layer]:
            found.append(Edge(source, target))
    return found


def to_mermaid(graph: Graph, bad: list[Edge]) -> str:
    """依存図を Mermaid の Markdown にする。

    Args:
        graph: 依存グラフ。
        bad: 逆流している辺。

    Returns:
        ` ```mermaid ` フェンス入りの Markdown（`check_diagrams.ps1` で検証できる形）。
    """
    bad_set = {(edge.source, edge.target) for edge in bad}
    lines = [
        "# 実際のアーキテクチャ（生成物）",
        "",
        "> `build_arch.py` が実装の import から起こした図。 **手で編集しない** 。",
        "> 設計書との差は `diff_arch.py`（`/arch diff`）で見る。",
        "",
        "```mermaid",
        "flowchart TD",
    ]
    for layer in LAYERS:
        members = sorted(node for node in graph.nodes if layer_of(node) == layer)
        if not members:
            continue
        lines.append(f"  subgraph {layer}")
        for node in members:
            lines.append(f'    {node}["{node.split(".", 1)[-1]}"]')
        lines.append("  end")

    loose = sorted(node for node in graph.nodes if not layer_of(node))
    for node in loose:
        lines.append(f'  {node}["{node}"]')

    for index, (source, target) in enumerate(sorted(graph.edges)):
        arrow = "-->" if (source, target) not in bad_set else "== 逆流 ==>"
        lines.append(f"  {source} {arrow} {target}")
        if (source, target) in bad_set:
            lines.append(f"  linkStyle {index} stroke:#d33,stroke-width:3px")
    lines.append("```")

    if bad:
        lines += ["", "## 逆流（内向きでない依存）", ""]
        lines += [f"- `{edge.source}` → `{edge.target}`" for edge in bad]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。逆流の有無を終了コードで返す。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description="実装の import から依存図を生成する")
    parser.add_argument("root", help="ソースルート（プロファイルの値を使う）")
    parser.add_argument(
        "--out", default="docs/architecture-actual.md", help="出力先の Markdown"
    )
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"NG: ソースルートがない（{root}）")
        return 2

    graph = build_graph(root)
    if not graph.nodes:
        print(f"NG: `.py` が 1 つも無い（{root}）。Python 以外は未対応")
        return 2

    bad = violations(graph)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_mermaid(graph, bad), encoding="utf-8")

    print(f"OK: {len(graph.nodes)} モジュール / {len(graph.edges)} 依存 → {out}")
    if bad:
        for edge in bad:
            print(f"NG: 逆流 {edge.source} → {edge.target}")
        print(f"RESULT: 逆流 {len(bad)} 件")
        return 1
    print("RESULT: 逆流なし")
    return 0


if __name__ == "__main__":
    sys.exit(main())
