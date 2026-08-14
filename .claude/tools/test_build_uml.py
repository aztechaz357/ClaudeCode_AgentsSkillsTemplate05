"""build_uml.py のテスト。

逆生成した図は **設計書の図と突き合わせる基準** になるので、
「描けること」より「実装に無いものを描かないこと」を重く見る。
実装より豪華な図が出ると、乖離の検出が逆向きに壊れる。

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

import build_uml

SOURCE = '''\
"""ドメイン。"""

from dataclasses import dataclass


class Reader:
    """契約（Port）。"""

    def read(self, path: str) -> list[str]:
        raise NotImplementedError


@dataclass
class Row:
    name: str
    size: int


class CsvReader(Reader):
    """契約の実装。"""

    def __init__(self, encoding: str) -> None:
        self.encoding = encoding
        self.rows: list[Row] = []

    def read(self, path: str) -> list[str]:
        return []

    def _private(self) -> None:
        pass
'''

CALLER = '''\
class Service:
    def __init__(self, reader):
        self.reader = reader

    def run(self, path):
        rows = self.reader.read(path)
        return summarize(rows)


def summarize(rows):
    return len(rows)
'''


def _src(root: Path, files: dict[str, str]) -> Path:
    pkg = root / "src" / "pkg"
    pkg.mkdir(parents=True)
    for name, text in files.items():
        (pkg / name).write_text(text, encoding="utf-8")
    return pkg


class ClassDiagramTest(unittest.TestCase):
    """クラス図を実装の AST から起こす。"""

    def test_lists_classes(self) -> None:
        found = build_uml.parse_classes(SOURCE, "domain.reader")
        self.assertEqual({c.name for c in found}, {"Reader", "Row", "CsvReader"})

    def test_records_inheritance(self) -> None:
        found = {c.name: c for c in build_uml.parse_classes(SOURCE, "m")}
        self.assertEqual(found["CsvReader"].bases, ["Reader"])
        self.assertEqual(found["Reader"].bases, [])

    def test_public_methods_only(self) -> None:
        """`_` 始まりは図に出さない（実装の内側は設計書の図に無い）。"""
        found = {c.name: c for c in build_uml.parse_classes(SOURCE, "m")}
        self.assertIn("read", found["CsvReader"].methods)
        self.assertNotIn("_private", found["CsvReader"].methods)
        self.assertNotIn("__init__", found["CsvReader"].methods)

    def test_reads_annotated_attributes(self) -> None:
        """型注釈のある属性だけを拾う（推測で属性を足さない）。"""
        found = {c.name: c for c in build_uml.parse_classes(SOURCE, "m")}
        self.assertEqual(found["Row"].attributes, {"name": "str", "size": "int"})

    def test_reads_self_assignment_with_annotation(self) -> None:
        found = {c.name: c for c in build_uml.parse_classes(SOURCE, "m")}
        self.assertIn("rows", found["CsvReader"].attributes)

    def test_renders_valid_mermaid(self) -> None:
        text = build_uml.to_class_diagram(build_uml.parse_classes(SOURCE, "m"))
        self.assertIn("classDiagram", text)
        self.assertIn("Reader <|-- CsvReader", text)
        self.assertIn("+read(", text)

    def test_node_ids_are_ascii(self) -> None:
        """ノード id に日本語や `{}` を入れない（構文エラーになる）。"""
        text = build_uml.to_class_diagram(build_uml.parse_classes(SOURCE, "m"))
        for bad in ("{", "}"):
            self.assertNotIn(bad + "例", text)

    def test_syntax_error_is_skipped_not_crashed(self) -> None:
        """壊れた .py があっても落ちない（他のファイルの図は出す）。"""
        self.assertEqual(build_uml.parse_classes("def (:", "m"), [])


class SequenceDiagramTest(unittest.TestCase):
    """呼び出し関係だけをシーケンス図にする。"""

    def test_records_calls_from_methods(self) -> None:
        calls = build_uml.parse_calls(CALLER, "application.service")
        pairs = {(c.caller, c.callee) for c in calls}
        self.assertIn(("Service.run", "self.reader.read"), pairs)
        self.assertIn(("Service.run", "summarize"), pairs)

    def test_renders_valid_mermaid(self) -> None:
        text = build_uml.to_sequence_diagram(
            build_uml.parse_calls(CALLER, "application.service")
        )
        self.assertIn("sequenceDiagram", text)
        self.assertIn("Service.run", text)


class CollectTest(unittest.TestCase):
    """ソースルート全体。"""

    def test_walks_the_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pkg = _src(Path(tmp), {"reader.py": SOURCE, "service.py": CALLER})
            classes = build_uml.collect_classes(pkg)
        self.assertEqual(
            {c.name for c in classes}, {"Reader", "Row", "CsvReader", "Service"}
        )

    def test_module_id_includes_layer(self) -> None:
        """設計書の図と同じ id 規約（層を含む）で出す。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pkg = root / "src" / "pkg" / "domain"
            pkg.mkdir(parents=True)
            (pkg / "reader.py").write_text(SOURCE, encoding="utf-8")
            classes = build_uml.collect_classes(root / "src" / "pkg")
        self.assertTrue(all(c.module.startswith("domain.") for c in classes))


class MainTest(unittest.TestCase):
    """CLI。"""

    def _run(self, argv: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = build_uml.main(argv)
        return code, buffer.getvalue()

    def test_class_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pkg = _src(Path(tmp), {"reader.py": SOURCE})
            code, out = self._run([str(pkg), "--kind", "class"])
        self.assertEqual(code, 0)
        self.assertIn("classDiagram", out)

    def test_sequence_kind(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pkg = _src(Path(tmp), {"service.py": CALLER})
            code, out = self._run([str(pkg), "--kind", "sequence"])
        self.assertEqual(code, 0)
        self.assertIn("sequenceDiagram", out)

    def test_state_kind_refuses_honestly(self) -> None:
        """状態遷移図は実装から復元できない。できるふりをしない。"""
        with tempfile.TemporaryDirectory() as tmp:
            pkg = _src(Path(tmp), {"reader.py": SOURCE})
            code, out = self._run([str(pkg), "--kind", "state"])
        self.assertEqual(code, 2)
        self.assertIn("復元できない", out)

    def test_missing_root_exits_two(self) -> None:
        code, _ = self._run(["no/such/dir", "--kind", "class"])
        self.assertEqual(code, 2)

    def test_no_python_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self._run([tmp, "--kind", "class"])
        self.assertEqual(code, 2)
        self.assertIn("py", out)


if __name__ == "__main__":
    unittest.main()
