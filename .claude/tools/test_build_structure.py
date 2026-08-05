"""build_structure.py のテスト。

このツールは「フォルダ構成を手で書き写さない」ためにある。
手書きのスナップショットは必ず実物とずれるので、実物から生成し、
`--check` で古さを終了コードで落とす（build_usdm.py と同じ考え方）。

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

import build_structure


def _make_repo(root: Path) -> None:
    """層のあるリポジトリと、除外されるべきディレクトリを作る。"""
    files = [
        "src/tool/presentation/cli.py",
        "src/tool/application/ports.py",
        "src/tool/domain/count.py",
        "src/tool/infrastructure/csv_file.py",
        "test/domain/test_count.py",
        "test/e2e/test_cli.py",
        "docs/backlog.md",
        ".venv/lib/junk.py",
        "__pycache__/cache.pyc",
        "node_modules/pkg/index.js",
        ".git/config",
    ]
    for name in files:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")


def _run(root: Path, *args: str) -> tuple[int, str]:
    """ツールを走らせ、終了コードと標準出力を返す。"""
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = build_structure.main([str(root), *args])
    return code, buf.getvalue()


class RenderTest(unittest.TestCase):
    """実物のツリーを文書にできること。"""

    def test_ツリーを生成して書き出す(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            code, _ = _run(root)
            self.assertEqual(code, 0)
            body = (root / "docs" / "structure.md").read_text(encoding="utf-8")
            self.assertIn("presentation", body)
            self.assertIn("domain", body)
            self.assertIn("test", body)

    def test_探索除外のディレクトリは出さない(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            _run(root)
            body = (root / "docs" / "structure.md").read_text(encoding="utf-8")
            for name in (".venv", "__pycache__", "node_modules", ".git"):
                self.assertNotIn(name, body)

    def test_日時を埋め込まない(self) -> None:
        # 日時を入れると --check が常に古いと言い出す（build_usdm.py と同じ轍）。
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            _run(root)
            first = (root / "docs" / "structure.md").read_text(encoding="utf-8")
            _run(root)
            second = (root / "docs" / "structure.md").read_text(encoding="utf-8")
            self.assertEqual(first, second)

    def test_深さで打ち切る(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            _run(root, "--depth", "1")
            body = (root / "docs" / "structure.md").read_text(encoding="utf-8")
            self.assertIn("src", body)
            self.assertNotIn("cli.py", body)

    def test_説明を付けられる(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            notes = root / ".claude" / "structure-notes.txt"
            notes.parent.mkdir(parents=True, exist_ok=True)
            notes.write_text(
                "# コメント行は無視する\nsrc/tool/domain\t業務ロジック（純粋）\n",
                encoding="utf-8",
            )
            _run(root)
            body = (root / "docs" / "structure.md").read_text(encoding="utf-8")
            self.assertIn("業務ロジック（純粋）", body)


class CheckTest(unittest.TestCase):
    """--check が古さを終了コードで落とすこと。"""

    def test_最新なら0(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            _run(root)
            code, out = _run(root, "--check")
            self.assertEqual(code, 0, out)

    def test_構成が変わっていたら1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            _run(root)
            # 既定の深さ 3 に収まる位置に足す（深さ 4 は打ち切られて見えない）
            (root / "src" / "tool" / "container.py").write_text("x", encoding="utf-8")
            code, out = _run(root, "--check")
            self.assertEqual(code, 1)
            self.assertIn("STALE", out)

    def test_未生成なら1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            code, out = _run(root, "--check")
            self.assertEqual(code, 1)
            self.assertIn("STALE", out)


if __name__ == "__main__":
    unittest.main()
