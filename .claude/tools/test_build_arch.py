"""build_arch.py のテスト。

このツールは「実装が本当はどうなっているか」を出すものなので、
次の 2 つを重点的に検証する:

    - **逆流（内向きでない依存）を必ず検出すること** —— 見逃すと図が嘘になる
    - 正しい依存を違反と言わないこと（誤検出が続くと誰も見なくなる）

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

SOURCES = {
    "presentation/cli.py": "from pkg.application.filter import filter_rows\nimport sys\n",
    "application/filter.py": "from pkg.domain.row import Row\nfrom pkg.application.ports import Reader\n",
    "application/ports.py": "from abc import ABC\n",
    "domain/row.py": "from dataclasses import dataclass\n",
    "infrastructure/csv_reader.py": (
        "from pkg.application.ports import Reader\nfrom pkg.domain.row import Row\nimport csv\n"
    ),
}


def _tree(root: Path, sources: dict[str, str]) -> Path:
    """ソースルートを作る。"""
    for name, text in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


class ImportsTest(unittest.TestCase):
    """import の読み取り。"""

    def test_reads_from_import(self) -> None:
        """`from a.b import c` の a.b を読む。"""
        found = build_arch.parse_imports("from pkg.domain.row import Row\n")
        self.assertEqual(found, ["pkg.domain.row"])

    def test_reads_plain_import(self) -> None:
        """`import a.b` も読む。"""
        self.assertEqual(build_arch.parse_imports("import pkg.application.filter\n"), ["pkg.application.filter"])

    def test_ignores_syntax_error(self) -> None:
        """壊れたファイルは飛ばす（全体を落とさない）。"""
        self.assertEqual(build_arch.parse_imports("def (:\n"), [])


class GraphTest(unittest.TestCase):
    """依存グラフの組み立て。"""

    def _graph(self) -> build_arch.Graph:
        with tempfile.TemporaryDirectory() as tmp:
            return build_arch.build_graph(_tree(Path(tmp), SOURCES))

    def test_nodes_are_layer_qualified(self) -> None:
        """ノード id は層を含むモジュールパスになる。"""
        self.assertIn("application.filter", self._graph().nodes)

    def test_edges_are_internal_only(self) -> None:
        """標準ライブラリ（sys・csv）への import は辺にしない。"""
        edges = self._graph().edges
        self.assertIn(("presentation.cli", "application.filter"), edges)
        self.assertNotIn(("presentation.cli", "sys"), edges)

    def test_layer_of_node(self) -> None:
        """ノードの層は先頭のディレクトリ。"""
        self.assertEqual(build_arch.layer_of("application.filter"), "application")


class ViolationTest(unittest.TestCase):
    """逆流の検出（内向きの依存だけが正しい）。"""

    def _violations(self, sources: dict[str, str]) -> list[tuple[str, str]]:
        with tempfile.TemporaryDirectory() as tmp:
            graph = build_arch.build_graph(_tree(Path(tmp), sources))
        return [(edge.source, edge.target) for edge in build_arch.violations(graph)]

    def test_clean_tree_has_none(self) -> None:
        """正しい依存だけなら違反 0 件（誤検出しない）。"""
        self.assertEqual(self._violations(SOURCES), [])

    def test_domain_importing_application_is_violation(self) -> None:
        """domain が上の層を import したら違反。"""
        broken = dict(SOURCES)
        broken["domain/row.py"] = "from pkg.application.filter import filter_rows\n"
        self.assertIn(("domain.row", "application.filter"), self._violations(broken))

    def test_application_importing_infrastructure_is_violation(self) -> None:
        """application が infrastructure を直接 import したら違反（契約を介す）。"""
        broken = dict(SOURCES)
        broken["application/filter.py"] = "from pkg.infrastructure.csv_reader import CsvReader\n"
        self.assertIn(("application.filter", "infrastructure.csv_reader"), self._violations(broken))

    def test_infrastructure_to_application_is_allowed(self) -> None:
        """infrastructure → application（契約の実装）は正しい向き。"""
        self.assertNotIn(("infrastructure.csv_reader", "application.ports"), self._violations(SOURCES))


class MermaidTest(unittest.TestCase):
    """出力（設計書と比較できる形であること）。"""

    def _text(self) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            graph = build_arch.build_graph(_tree(Path(tmp), SOURCES))
        return build_arch.to_mermaid(graph, build_arch.violations(graph))

    def test_has_mermaid_fence(self) -> None:
        """check_diagrams.ps1 が検証できるフェンスで出す。"""
        text = self._text()
        self.assertIn("```mermaid", text)
        self.assertIn("flowchart TD", text)

    def test_groups_by_layer(self) -> None:
        """層ごとに subgraph でまとめる。"""
        self.assertIn("subgraph domain", self._text())

    def test_node_id_matches_module_path(self) -> None:
        """ノード id は設計書と突き合わせられるモジュールパス。"""
        self.assertIn('application.filter["', self._text())

    def test_marks_violations_red(self) -> None:
        """違反があれば色分けの定義を出す。"""
        broken = dict(SOURCES)
        broken["domain/row.py"] = "from pkg.application.filter import filter_rows\n"
        with tempfile.TemporaryDirectory() as tmp:
            graph = build_arch.build_graph(_tree(Path(tmp), broken))
        text = build_arch.to_mermaid(graph, build_arch.violations(graph))
        self.assertIn("逆流", text)


class MainTest(unittest.TestCase):
    """終了コード（0 = 逆流なし / 1 = 逆流あり / 2 = エラー）。"""

    def _run(self, argv: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = build_arch.main(argv)
        return code, buffer.getvalue()

    def test_writes_output_and_exits_zero(self) -> None:
        """正しい木では 0 を返し、図を書き出す。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = _tree(Path(tmp), SOURCES)
            out = root / "arch.md"
            code, _ = self._run([str(root), "--out", str(out)])
            self.assertEqual(code, 0)
            self.assertIn("flowchart TD", out.read_text(encoding="utf-8"))

    def test_violation_exits_one(self) -> None:
        """逆流があれば 1（緑のまま素通りさせない）。"""
        broken = dict(SOURCES)
        broken["domain/row.py"] = "from pkg.application.filter import filter_rows\n"
        with tempfile.TemporaryDirectory() as tmp:
            root = _tree(Path(tmp), broken)
            code, out = self._run([str(root), "--out", str(root / "arch.md")])
        self.assertEqual(code, 1)
        self.assertIn("domain.row", out)

    def test_missing_root_exits_two(self) -> None:
        """ソースルートが無ければ 2。"""
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = self._run([str(Path(tmp) / "ない"), "--out", str(Path(tmp) / "a.md")])
        self.assertEqual(code, 2)

    def test_empty_tree_exits_two(self) -> None:
        """.py が 1 つも無いのを成功にしない（空振りの検査を作らない）。"""
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = self._run([tmp, "--out", str(Path(tmp) / "a.md")])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
