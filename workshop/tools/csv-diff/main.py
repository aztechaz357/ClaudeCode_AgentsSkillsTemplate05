"""csv-diff — 2つの CSV の差分を行単位で出す

工房レーンのツール。使い方は同じディレクトリの README.md を正とする。
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


def read_rows(path: Path) -> tuple[list[str], list[list[str]]]:
    """CSV を見出し行と本体行に分けて読む。

    Args:
        path: 読み込む CSV のパス。

    Returns:
        (見出し行, 本体行のリスト)。空ファイルなら ([], [])。
    """
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    if not rows:
        return [], []
    return rows[0], rows[1:]


def run(args: argparse.Namespace) -> int:
    """ツールの本体。

    Args:
        args: パース済みのコマンドライン引数。

    Returns:
        終了コード。差分なし 0 / 差分あり 1 / 引数・構造の誤り 2。
    """
    left, right = Path(args.left), Path(args.right)
    for p in (left, right):
        if not p.is_file():
            print(f"ERROR: file not found: {p}")
            return 2

    left_header, left_rows = read_rows(left)
    right_header, right_rows = read_rows(right)

    # 列が違う表の行を比べても意味が無いので、実行前に弾く（フェイルクローズ）。
    if left_header != right_header:
        print(f"ERROR: header mismatch: {left_header} != {right_header}")
        return 2

    left_keys = {",".join(r) for r in left_rows}
    right_keys = {",".join(r) for r in right_rows}

    removed = [r for r in left_rows if ",".join(r) not in right_keys]
    added = [r for r in right_rows if ",".join(r) not in left_keys]

    if not removed and not added:
        print(f"RESULT: no differences ({len(left_rows)} rows)")
        return 0

    print(f"--- {left}")
    print(f"+++ {right}")
    for r in removed:
        print("- " + ",".join(r))
    for r in added:
        print("+ " + ",".join(r))
    print(f"RESULT: {len(removed)} removed, {len(added)} added")
    return 1


def build_parser() -> argparse.ArgumentParser:
    """コマンドライン引数のパーサを組み立てる。

    Returns:
        設定済みの ArgumentParser。
    """
    parser = argparse.ArgumentParser(prog="csv-diff", description="2つの CSV の差分を行単位で出す")
    parser.add_argument("left", help="比較元の CSV")
    parser.add_argument("right", help="比較先の CSV")
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
