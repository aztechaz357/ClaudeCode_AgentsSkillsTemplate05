"""check_py_names.ps1 のテスト。

Python の識別子は非 ASCII でも構文としては通る。しかし関数名に日本語を
使うと、端末のコードページ次第で **テストの失敗表示が化けて読めなくなる**
（実測: `test_日本語と...` が `test_���{���...` になり、どのテストが
落ちたか分からなかった）。説明は docstring に日本語で書けばよいので、
識別子は ASCII に揃える。

このテストは「検出できること」と「正しいコードを誤検出しないこと」の
両方を持つ。後者を落とすと、誰も通せないツールになる。

実行（前置コマンドはプロファイルの「.claude/tools/ の Python ツール実行」）:
    <ツール実行コマンド> -m unittest discover -s .claude/tools -p "test_*.py" -v
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parent.parent
TOOL = TOOLS / "check_py_names.ps1"


def run_tool(path: Path | str) -> tuple[int, str]:
    """ツールを実プロセスとして起動し、(終了コード, 標準出力) を返す。"""
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-File", str(TOOL), "-Path", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(REPO),
    )
    return proc.returncode, proc.stdout.decode("utf-8", errors="replace")


def write_py(directory: Path, name: str, body: str) -> Path:
    target = directory / name
    target.write_text(body, encoding="utf-8")
    return target


class TestCheckPyNames(unittest.TestCase):
    def test_detects_japanese_function_name(self):
        """日本語の関数名を検出する。"""
        with tempfile.TemporaryDirectory() as d:
            target = write_py(Path(d), "a.py", "def 集計する(rows):\n    return rows\n")
            code, out = run_tool(target)
        self.assertEqual(code, 1)
        self.assertIn("NG:", out)
        self.assertIn("集計する", out)

    def test_detects_japanese_method_name(self):
        """クラスの中（インデントされた def）でも検出する。"""
        with tempfile.TemporaryDirectory() as d:
            target = write_py(
                Path(d),
                "a.py",
                "class T:\n    def test_日本語(self):\n        pass\n",
            )
            code, out = run_tool(target)
        self.assertEqual(code, 1)
        self.assertIn("test_日本語", out)

    def test_detects_async_function_name(self):
        """async def も対象にする。"""
        with tempfile.TemporaryDirectory() as d:
            target = write_py(Path(d), "a.py", "async def 取得(url):\n    return url\n")
            code, out = run_tool(target)
        self.assertEqual(code, 1)
        self.assertIn("取得", out)

    def test_reports_the_line_number(self):
        """どこを直せばよいか分かるよう行番号を出す。"""
        with tempfile.TemporaryDirectory() as d:
            target = write_py(
                Path(d), "a.py", "import os\n\n\ndef 数える(x):\n    return x\n"
            )
            code, out = run_tool(target)
        self.assertEqual(code, 1)
        self.assertIn("L4", out)

    def test_accepts_ascii_names(self):
        """ASCII の関数名は通す。"""
        with tempfile.TemporaryDirectory() as d:
            target = write_py(
                Path(d),
                "a.py",
                'def count_rows(rows):\n    """行を数える。"""\n    return len(rows)\n',
            )
            code, out = run_tool(target)
        self.assertEqual(code, 0, out)
        self.assertIn("OK", out)

    def test_ignores_japanese_outside_the_name(self):
        """引数の既定値・docstring・コメントの日本語は誤検出しない。"""
        with tempfile.TemporaryDirectory() as d:
            target = write_py(
                Path(d),
                "a.py",
                "# 日本語のコメント\n"
                'def label(text="既定値"):\n'
                '    """日本語の説明。"""\n'
                "    return text  # 日本語の行末コメント\n",
            )
            code, out = run_tool(target)
        self.assertEqual(code, 0, out)

    def test_ignores_def_inside_a_docstring(self):
        """三重引用符の中の `def` は定義ではない。"""
        with tempfile.TemporaryDirectory() as d:
            target = write_py(
                Path(d),
                "a.py",
                '"""使い方の例:\n\ndef 集計する(rows):\n    ...\n"""\n\n'
                "def summarize(rows):\n    return rows\n",
            )
            code, out = run_tool(target)
        self.assertEqual(code, 0, out)

    def test_scans_a_directory_recursively(self):
        """ディレクトリを渡すと配下の .py をすべて見る。"""
        with tempfile.TemporaryDirectory() as d:
            nested = Path(d) / "pkg" / "sub"
            nested.mkdir(parents=True)
            write_py(Path(d), "ok.py", "def ok():\n    pass\n")
            write_py(nested, "ng.py", "def 駄目():\n    pass\n")
            code, out = run_tool(d)
        self.assertEqual(code, 1)
        self.assertIn("ng.py", out)
        self.assertNotIn("ok.py", out)

    def test_reports_missing_path_as_argument_error(self):
        """存在しないパスは引数エラー（終了コード 2）。"""
        code, out = run_tool(Path(tempfile.gettempdir()) / "no-such-file-xyz.py")
        self.assertEqual(code, 2)
        self.assertIn("ERROR", out)

    def test_no_python_file_is_not_a_failure(self):
        """.py が 1 つも無いディレクトリは OK 扱い。"""
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "readme.md").write_text("# a\n", encoding="utf-8")
            code, out = run_tool(d)
        self.assertEqual(code, 0, out)


class TestRepositoryIsClean(unittest.TestCase):
    """このリポジトリ自身が規約を守っていること（毎回のテストで走る）。"""

    def test_repository_has_no_japanese_function_names(self):
        code, out = run_tool(REPO)
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
