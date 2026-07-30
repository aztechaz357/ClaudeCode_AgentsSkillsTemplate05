"""{{NAME}} — {{SUMMARY}}

工房レーンのツール。使い方は同じディレクトリの README.md を正とする。
"""

from __future__ import annotations

import argparse
import sys


def run(args: argparse.Namespace) -> int:
    """ツールの本体。

    Args:
        args: パース済みのコマンドライン引数。

    Returns:
        終了コード。成功なら 0、失敗なら非 0。
    """
    raise NotImplementedError("{{NAME}} の本体は未実装")


def build_parser() -> argparse.ArgumentParser:
    """コマンドライン引数のパーサを組み立てる。

    Returns:
        設定済みの ArgumentParser。
    """
    parser = argparse.ArgumentParser(prog="{{NAME}}", description="{{SUMMARY}}")
    return parser


def main(argv: list[str] | None = None) -> int:
    """エントリポイント。

    Args:
        argv: コマンドライン引数（None なら sys.argv[1:]）。

    Returns:
        終了コード。
    """
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
