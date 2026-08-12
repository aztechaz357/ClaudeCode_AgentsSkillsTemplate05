"""check_mermaid_ids.ps1 のテスト。

実際に起きた事故: 設計書の雛形の mermaid で、ノード id に雛形の穴を書いた
（`presentation.{入口}["…"]`）。mermaid は `{` を別の図形の開始と解釈するため
構文エラーになるが、 **図の検証（check_diagrams.ps1）はフックに配線されて
おらず**、誰も走らせないまま気づかれなかった。

そこで「ツールチェーン非依存で速い」検査を作り、Markdown を編集するたびに
フックから走らせる。full の構文検証（mmdc）は 1 ファイル約 5 秒かかり、
毎編集には重いため、この検査は **壊れ方の型** だけを見る。

このテストは「検出できること」と「正しい図を誤検出しないこと」の両方を持つ。
後者を落とすと、誰も通せない検査になる。

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
TOOL = TOOLS / "check_mermaid_ids.ps1"


def run_tool(path: Path | str) -> tuple[int, str]:
    """ツールを実プロセスとして起動し、(終了コード, 標準出力) を返す。"""
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-File", str(TOOL), "-Path", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(REPO),
    )
    return proc.returncode, proc.stdout.decode("utf-8", errors="replace")


def write_md(directory: Path, body: str, name: str = "a.md") -> Path:
    target = directory / name
    target.write_text(body, encoding="utf-8")
    return target


def fenced(*lines: str) -> str:
    return "# 図\n\n```mermaid\nflowchart TD\n" + "\n".join(lines) + "\n```\n"


class DetectTest(unittest.TestCase):
    """検出できること。"""

    def test_placeholder_in_node_id(self) -> None:
        """実際に起きた事故そのもの（id に雛形の穴）。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = write_md(
                Path(tmp), fenced('  presentation.{入口}["{入口の名前}（CLI）"] --> a.b["x"]')
            )
            code, out = run_tool(path)
        self.assertEqual(code, 1)
        self.assertIn("brace", out.lower())

    def test_non_ascii_node_id(self) -> None:
        """id に日本語を使うと実装の図と機械比較できない。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = write_md(Path(tmp), fenced('  入口["CLI"] --> application.count["数える"]'))
            code, out = run_tool(path)
        self.assertEqual(code, 1)
        self.assertIn("ascii", out.lower())

    def test_unbalanced_bracket(self) -> None:
        """閉じ忘れも構文エラーになる。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = write_md(Path(tmp), fenced('  a.b["ラベル" --> c.d["x"]'))
            code, out = run_tool(path)
        self.assertEqual(code, 1)
        self.assertIn("unbalanced", out.lower())


class AcceptTest(unittest.TestCase):
    """誤検出しないこと。"""

    def test_placeholder_inside_label_is_fine(self) -> None:
        """`"…"` の中の雛形の穴は正しい書き方（雛形はこれを使う）。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = write_md(
                Path(tmp), fenced('  presentation.cli["{入口の名前}（CLI）"] --> application.count["{名前}"]')
            )
            code, out = run_tool(path)
        self.assertEqual(code, 0, out)

    def test_rhombus_shape_is_fine(self) -> None:
        """`A{判定}` は mermaid の正しい図形（id の直後の `{`）。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = write_md(Path(tmp), fenced("  A{判定} --> B[処理]"))
            code, out = run_tool(path)
        self.assertEqual(code, 0, out)

    def test_style_lines_are_skipped(self) -> None:
        """classDef / class / linkStyle は id の宣言ではない。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = write_md(
                Path(tmp),
                fenced(
                    '  a.b["x"] --> c.d["y"]',
                    "  classDef application fill:#e8f5e9,stroke:#2e7d32",
                    "  class a.b application",
                    "  linkStyle 0 stroke:#d33,stroke-width:3px",
                ),
            )
            code, out = run_tool(path)
        self.assertEqual(code, 0, out)

    def test_other_diagram_types_are_skipped(self) -> None:
        """flowchart 以外（sequenceDiagram 等）は文法が違うので見ない。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = write_md(
                Path(tmp),
                "```mermaid\nsequenceDiagram\n  利用者->>システム: 入力\n```\n",
            )
            code, out = run_tool(path)
        self.assertEqual(code, 0, out)

    def test_markdown_without_diagram_is_ok(self) -> None:
        """図の無い Markdown は素通し（毎編集で走るため）。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = write_md(Path(tmp), "# ただの文書\n\n本文。\n")
            code, _ = run_tool(path)
        self.assertEqual(code, 0)

    def test_repository_documents_pass(self) -> None:
        """このリポジトリの実物（雛形・規約）を誤検出しない。"""
        for target in (
            ".claude/skills/functional-design/template-thin.md",
            ".claude/skills/writing-conventions/guides/diagrams.md",
        ):
            code, out = run_tool(REPO / target)
            self.assertEqual(code, 0, f"{target}: {out}")


class ArgumentTest(unittest.TestCase):
    """引数まわり。"""

    def test_directory_is_scanned(self) -> None:
        """ディレクトリを渡したら配下の .md をすべて見る。"""
        with tempfile.TemporaryDirectory() as tmp:
            write_md(Path(tmp), fenced('  a.b["x"] --> c.d["y"]'), "good.md")
            write_md(Path(tmp), fenced('  a.{穴}["x"] --> c.d["y"]'), "bad.md")
            code, out = run_tool(tmp)
        self.assertEqual(code, 1)
        self.assertIn("bad.md", out)

    def test_directory_scan_ignores_non_markdown(self) -> None:
        """Markdown 以外を走査しない。

        実測: `-Include` が効かず `__pycache__` の `.pyc`（テスト文字列を
        含むバイト列）を Markdown として読み、NG を出していた。
        """
        with tempfile.TemporaryDirectory() as tmp:
            write_md(Path(tmp), fenced('  a.b["x"] --> c.d["y"]'), "good.md")
            cache = Path(tmp) / "__pycache__"
            cache.mkdir()
            (cache / "x.pyc").write_bytes(
                'flowchart TD presentation.{入口}["CLI"]'.encode("utf-8")
            )
            (Path(tmp) / "notes.txt").write_text(
                fenced('  a.{穴}["x"] --> c.d["y"]'), encoding="utf-8"
            )
            code, out = run_tool(tmp)
        self.assertEqual(code, 0, out)

    def test_missing_path_exits_two(self) -> None:
        """対象が無ければ 2（0 件を成功にしない）。"""
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = run_tool(Path(tmp) / "ない.md")
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
