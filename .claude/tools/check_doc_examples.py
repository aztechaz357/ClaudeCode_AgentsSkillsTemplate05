"""Markdown 内の Python コード例を実際に実行し、記載された出力と照合する。

マニュアルの「動かない例」を機械的に検出するためのツール。
動かない取説は無い方がマシなので、例の実行を検証で強制する。

対象とする書き方:

    ```python
    print("hello")
    ```

    出力:

    ```
    hello
    ```

- ` ```python ` ブロックを 1 つのスクリプトとして実行する
- 直後に（見出しや短い段落を挟んでもよい）現れる言語指定なしの
  ` ``` ` ブロックがあれば、それを期待する標準出力として照合する
- 期待出力ブロックが無い場合は、例外なく終了することだけを確認する
- ` ```python ` 以外（ ```text ` や ` ```dot ` など）は実行しない

使い方（前置コマンドはプロファイルの
「.claude/tools/ の Python ツール実行」。例: uv run python）:
    <ツール実行コマンド> .claude/tools/check_doc_examples.py <file.md> [<file.md> ...]

終了コード:
    0 = 全ての例が期待どおり
    1 = 実行に失敗したか出力が一致しない例がある
    2 = 引数・環境のエラー
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# ```python ... ``` と、それに続く言語指定なしの ``` ... ``` を拾う。
# 2 つのブロックの間は、空行・短い段落（「出力:」など）だけを許す。
_EXAMPLE = re.compile(
    r"```python\n(?P<code>.*?)```"
    r"(?P<gap>(?:[^\n`]*\n){0,6})"
    r"(?:```\n(?P<expected>.*?)```)?",
    re.DOTALL,
)


def _iter_examples(text: str) -> list[tuple[int, str, str | None]]:
    """Markdown から (連番, コード, 期待出力) を取り出す。

    Args:
        text: Markdown 全文

    Returns:
        例の一覧。期待出力が無い例は None を持つ。
    """
    examples: list[tuple[int, str, str | None]] = []
    for index, match in enumerate(_EXAMPLE.finditer(text), start=1):
        expected = match.group("expected")
        examples.append((index, match.group("code"), expected))
    return examples


def _run(code: str, cwd: Path) -> tuple[bool, str]:
    """コードを別プロセスで実行し、標準出力を返す。

    Args:
        code: 実行する Python コード
        cwd: 実行時の作業ディレクトリ（リポジトリルート）

    Returns:
        (正常終了したか, 標準出力または標準エラー)
    """
    # 子プロセスの標準出力を UTF-8 に固定する。Windows では既定が
    # コンソールのコードページ（cp932 等）になり、日本語を print する例で
    # UnicodeDecodeError になるため。
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"

    with tempfile.TemporaryDirectory() as work:
        script = Path(work) / "example.py"
        script.write_text(code, encoding="utf-8")
        completed = subprocess.run(  # noqa: S603
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            env=env,
        )
    if completed.returncode != 0:
        return False, completed.stderr.strip()
    return True, completed.stdout.strip()


def _check_file(path: Path, repo_root: Path) -> tuple[list[str], int]:
    """1 ファイル分の例を検証する。

    Args:
        path: 検証する Markdown のパス
        repo_root: リポジトリルート（実行時の作業ディレクトリ）

    Returns:
        (問題の説明の一覧, 出力を照合できた例の数) の組。
        照合数を返すのは、期待出力ブロックを取り違えて「実行しただけ」に
        なっていないかを呼び出し側が確認できるようにするため。
    """
    text = path.read_text(encoding="utf-8")
    problems: list[str] = []
    compared = 0

    for index, code, expected in _iter_examples(text):
        ok, output = _run(code, repo_root)
        if not ok:
            problems.append(f"example {index}: 実行に失敗した\n{_indent(output)}")
            continue
        if expected is None:
            continue
        compared += 1
        if output != expected.strip():
            problems.append(
                f"example {index}: 出力が一致しない\n"
                f"        期待:\n{_indent(expected.strip())}\n"
                f"        実際:\n{_indent(output)}"
            )
    return problems, compared


def _indent(text: str) -> str:
    """複数行を字下げして読みやすくする。

    Args:
        text: 字下げする文字列

    Returns:
        各行を 12 スペース字下げした文字列
    """
    return "\n".join(f"            {line}" for line in text.splitlines())


def main(argv: list[str]) -> int:
    """エントリポイント。

    Args:
        argv: コマンドライン引数（ファイルパスの並び）

    Returns:
        終了コード
    """
    if not argv:
        print("ERROR: 検証する Markdown を 1 つ以上指定する")
        return 2

    repo_root = Path(__file__).resolve().parent.parent.parent
    failed = 0
    total = 0

    for raw in argv:
        path = Path(raw)
        if not path.is_file():
            print(f"ERROR: file not found: {path}")
            return 2

        examples = _iter_examples(path.read_text(encoding="utf-8"))
        total += len(examples)
        problems, compared = _check_file(path, repo_root)
        summary = f"{len(examples)} examples, {compared} compared"

        if not examples:
            print(f"NO-EXAMPLE: {path}")
        elif problems:
            print(f"NG: {path} ({summary})")
            for problem in problems:
                print(f"    {problem}")
            failed += 1
        else:
            print(f"OK: {path} ({summary})")

    if failed:
        print(f"RESULT: {failed} file(s) NG")
        return 1
    print(f"RESULT: all OK ({total} examples)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
