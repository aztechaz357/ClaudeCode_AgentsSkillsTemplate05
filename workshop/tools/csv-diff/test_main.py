"""csv-diff の動作確認テスト。

工房レーンでもテストは先に書く（Red を確認してから実装する）。
"""

from __future__ import annotations

from pathlib import Path

import main


def write_csv(path: Path, text: str) -> str:
    """テスト用の CSV を書き出す。

    Args:
        path: 書き出し先。
        text: 中身（末尾の改行は呼び出し側で付ける）。

    Returns:
        書き出したパスの文字列。
    """
    path.write_text(text, encoding="utf-8")
    return str(path)


HEADER = "id,name,age\n"


def test_identical_files_report_no_difference(tmp_path, capsys):
    """テスト対象: csv-diff の main()
    入力: 中身が完全に同じ2つの CSV
    期待値: 終了コード 0、出力に "no differences" を含む
    理由: 差分なしを「成功（0）」で返すのがこのツールの終了コード契約であり、
          スクリプトから `if csv-diff ...` の形で使えるようにするため
    """
    a = write_csv(tmp_path / "a.csv", HEADER + "1,alice,30\n2,bob,20\n")
    b = write_csv(tmp_path / "b.csv", HEADER + "1,alice,30\n2,bob,20\n")

    assert main.main([a, b]) == 0
    assert "no differences" in capsys.readouterr().out


def test_changed_row_is_reported_as_removed_and_added(tmp_path, capsys):
    """テスト対象: csv-diff の main()
    入力: 1行だけ値が違う2つの CSV
    期待値: 終了コード 1、出力に "- 2,bob,20" と "+ 2,bob,21" を含む
    理由: 行単位の差分という要求そのもの。変更を削除＋追加として出す
    """
    a = write_csv(tmp_path / "a.csv", HEADER + "1,alice,30\n2,bob,20\n")
    b = write_csv(tmp_path / "b.csv", HEADER + "1,alice,30\n2,bob,21\n")

    assert main.main([a, b]) == 1
    out = capsys.readouterr().out
    assert "- 2,bob,20" in out
    assert "+ 2,bob,21" in out


def test_missing_file_is_an_argument_error(tmp_path, capsys):
    """テスト対象: csv-diff の main()
    入力: 存在しないファイルを片方に指定する
    期待値: 終了コード 2、出力に "ERROR" を含む
    理由: 差分あり（1）と環境・引数の誤り（2）を呼び出し側が区別できる必要がある
    """
    a = write_csv(tmp_path / "a.csv", HEADER)
    missing = str(tmp_path / "nope.csv")

    assert main.main([a, missing]) == 2
    assert "ERROR" in capsys.readouterr().out


def test_header_mismatch_is_refused(tmp_path, capsys):
    """テスト対象: csv-diff の main()
    入力: 列構成が違う2つの CSV
    期待値: 終了コード 2、出力に "ERROR" と "header" を含む
    理由: 列が違う表の行を比べても意味が無い。構造的な誤りは実行前に弾く
          （フェイルクローズ）
    """
    a = write_csv(tmp_path / "a.csv", "id,name,age\n1,alice,30\n")
    b = write_csv(tmp_path / "b.csv", "id,name\n1,alice\n")

    assert main.main([a, b]) == 2
    out = capsys.readouterr().out
    assert "ERROR" in out
    assert "header" in out
