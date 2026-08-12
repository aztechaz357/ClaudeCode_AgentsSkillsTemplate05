"""diff_arch.py のテスト。

このツールの目的は「設計したつもり」と実装の食い違いを見せること。
重点は次の 2 つ:

    - **実装にだけある依存（AI が黙って増やした構造）を必ず出すこと**
    - 一致しているものを差分と言わないこと（毎回黄色だと誰も見なくなる）

実行（前置コマンドはプロファイルの「.claude/tools/ の Python ツール実行」）:
    <ツール実行コマンド> -m unittest discover -s .claude/tools -p "test_*.py" -v
"""

from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_arch
import diff_arch

DESIGN = """\
# S01 骨組み

## 構成

```mermaid
flowchart TD
  subgraph presentation
    presentation.cli["CLI"]
  end
  subgraph application
    application.filter["フィルタ"]
  end
  subgraph domain
    domain.row["行"]
  end
  presentation.cli --> application.filter
  application.filter --> domain.row
```

## 判断の記録

- **採用**: 3 層で通す
"""

SOURCES = {
    "presentation/cli.py": "from pkg.application.filter import filter_rows\n",
    "application/filter.py": "from pkg.domain.row import Row\n",
    "domain/row.py": "from dataclasses import dataclass\n",
}


def _tree(root: Path, sources: dict[str, str]) -> Path:
    for name, text in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _actual(sources: dict[str, str]) -> build_arch.Graph:
    with tempfile.TemporaryDirectory() as tmp:
        return build_arch.build_graph(_tree(Path(tmp), sources))


class ParseMermaidTest(unittest.TestCase):
    """設計書の図の読み取り。"""

    def test_reads_nodes(self) -> None:
        """`id["表示名"]` の id をノードにする（表示名は日本語でよい）。"""
        graph = diff_arch.parse_mermaid(DESIGN)
        self.assertIn("application.filter", graph.nodes)

    def test_reads_edges(self) -> None:
        """`a --> b` を辺にする。"""
        self.assertIn(("presentation.cli", "application.filter"), diff_arch.parse_mermaid(DESIGN).edges)

    def test_ignores_prose(self) -> None:
        """フェンスの外の文（判断の記録）を図として読まない。"""
        graph = diff_arch.parse_mermaid(DESIGN)
        self.assertNotIn("採用", " ".join(graph.nodes))

    def test_no_diagram_is_empty(self) -> None:
        """図の無い設計書は空のグラフ（例外にしない）。"""
        self.assertEqual(diff_arch.parse_mermaid("# 図がない\n").nodes, set())


INLINE_DESIGN = """\
# S01 骨組み

```mermaid
flowchart TD
  presentation.cli["CLI（入口）"] --> application.filter["フィルタ"]
  application.filter --> domain.row["行"]
  application.filter -.->|契約| application.ports[["読み取り（契約）"]]
  infrastructure.csv_reader["ファイル読み"] -.->|実装| application.ports
```
"""


class InlineMermaidTest(unittest.TestCase):
    """実際の設計書に多い書き方（ラベルつきノード・ラベルつき矢印）。

    テンプレートの設計書の雛形がこの形なので、ここを読めないと
    「設計にだけある」に全部倒れて、乖離の検出が空振りする。
    """

    def test_reads_edge_with_inline_labels(self) -> None:
        """`a["名前"] --> b["名前"]` を辺として読む。"""
        graph = diff_arch.parse_mermaid(INLINE_DESIGN)
        self.assertIn(("presentation.cli", "application.filter"), graph.edges)

    def test_reads_labeled_arrow(self) -> None:
        """`-.->|契約|` のようにラベルつきの矢印も辺として読む。"""
        graph = diff_arch.parse_mermaid(INLINE_DESIGN)
        self.assertIn(("application.filter", "application.ports"), graph.edges)

    def test_reads_double_bracket_node(self) -> None:
        """契約の `[[...]]` 記法でも id を読む。"""
        graph = diff_arch.parse_mermaid(INLINE_DESIGN)
        self.assertIn(("infrastructure.csv_reader", "application.ports"), graph.edges)

    def test_label_text_is_not_an_id(self) -> None:
        """表示名（日本語）をノード id と取り違えない。"""
        graph = diff_arch.parse_mermaid(INLINE_DESIGN)
        self.assertNotIn("CLI（入口）", graph.nodes)


class DiffTest(unittest.TestCase):
    """設計と実装の突き合わせ。"""

    def test_identical_has_no_diff(self) -> None:
        """一致していれば差分 0（毎回差分が出ると見なくなる）。"""
        result = diff_arch.diff(diff_arch.parse_mermaid(DESIGN), _actual(SOURCES))
        self.assertEqual(result.design_only, [])
        self.assertEqual(result.impl_only, [])
        self.assertTrue(result.is_clean)

    def test_finds_implementation_only_edge(self) -> None:
        """設計に無い依存（黙って増えた構造）を出す。"""
        extra = dict(SOURCES)
        extra["presentation/cli.py"] = (
            "from pkg.application.filter import filter_rows\nfrom pkg.domain.row import Row\n"
        )
        result = diff_arch.diff(diff_arch.parse_mermaid(DESIGN), _actual(extra))
        self.assertIn(("presentation.cli", "domain.row"), result.impl_only)

    def test_finds_design_only_edge(self) -> None:
        """設計にあるのに実装されていない依存を出す。"""
        fewer = dict(SOURCES)
        fewer["application/filter.py"] = "pass\n"
        result = diff_arch.diff(diff_arch.parse_mermaid(DESIGN), _actual(fewer))
        self.assertIn(("application.filter", "domain.row"), result.design_only)

    def test_finds_missing_module(self) -> None:
        """設計にあるモジュールが実装に無ければ出す。"""
        fewer = {key: value for key, value in SOURCES.items() if key != "domain/row.py"}
        result = diff_arch.diff(diff_arch.parse_mermaid(DESIGN), _actual(fewer))
        self.assertIn("domain.row", result.missing_nodes)


class RenderTest(unittest.TestCase):
    """差分の図（色で意味を出す）。"""

    def _text(self) -> str:
        extra = dict(SOURCES)
        extra["presentation/cli.py"] = (
            "from pkg.application.filter import filter_rows\nfrom pkg.domain.row import Row\n"
        )
        result = diff_arch.diff(diff_arch.parse_mermaid(DESIGN), _actual(extra))
        return diff_arch.to_mermaid(result)

    def test_has_legend(self) -> None:
        """色の意味を凡例で示す（色だけでは伝わらない）。"""
        text = self._text()
        self.assertIn("凡例", text)
        self.assertIn("実装にだけある", text)

    def test_marks_extra_edge(self) -> None:
        """実装にだけある辺を印つきで出す。"""
        self.assertIn("presentation.cli", self._text())


class MainTest(unittest.TestCase):
    """終了コード（0 = 乖離なし / 1 = 乖離あり / 2 = エラー）。"""

    def _run(self, argv: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = diff_arch.main(argv)
        return code, buffer.getvalue()

    def _prepare(self, tmp: str, sources: dict[str, str]) -> tuple[Path, Path]:
        root = Path(tmp)
        source_root = _tree(root / "src", sources)
        design = root / "docs" / "design"
        design.mkdir(parents=True)
        (design / "S01-skeleton.md").write_text(DESIGN, encoding="utf-8")
        return source_root, design

    def test_clean_exits_zero(self) -> None:
        """一致していれば 0。"""
        with tempfile.TemporaryDirectory() as tmp:
            source_root, design = self._prepare(tmp, SOURCES)
            code, _ = self._run(
                [str(source_root), "--design", str(design), "--out", str(Path(tmp) / "d.md")]
            )
        self.assertEqual(code, 0)

    def test_drift_exits_one(self) -> None:
        """乖離があれば 1。"""
        extra = dict(SOURCES)
        extra["presentation/cli.py"] = (
            "from pkg.application.filter import filter_rows\nfrom pkg.domain.row import Row\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            source_root, design = self._prepare(tmp, extra)
            out = Path(tmp) / "d.md"
            code, text = self._run([str(source_root), "--design", str(design), "--out", str(out)])
            self.assertIn("flowchart TD", out.read_text(encoding="utf-8"))
        self.assertEqual(code, 1)
        self.assertIn("実装にだけある", text)

    def test_missing_design_exits_two(self) -> None:
        """設計書が 1 枚も無いのを成功にしない（空振りの検査を作らない）。"""
        with tempfile.TemporaryDirectory() as tmp:
            source_root = _tree(Path(tmp) / "src", SOURCES)
            code, _ = self._run(
                [
                    str(source_root),
                    "--design",
                    str(Path(tmp) / "ない"),
                    "--out",
                    str(Path(tmp) / "d.md"),
                ]
            )
        self.assertEqual(code, 2)

    def test_design_without_diagram_exits_two(self) -> None:
        """図が 1 枚も無い設計書だけのときも 2（比較対象が無い）。"""
        with tempfile.TemporaryDirectory() as tmp:
            source_root, design = self._prepare(tmp, SOURCES)
            (design / "S01-skeleton.md").write_text("# 図がない\n", encoding="utf-8")
            code, _ = self._run(
                [str(source_root), "--design", str(design), "--out", str(Path(tmp) / "d.md")]
            )
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
