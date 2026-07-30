"""{{NAME}} の動作確認テスト。

工房レーンでもテストは先に書く（Red を確認してから実装する）。
"""

from __future__ import annotations

import pytest

import main


def test_placeholder_fails_until_implemented():
    """テスト対象: {{NAME}} の run()
    入力: 引数なしで main([]) を呼ぶ
    期待値: NotImplementedError が送出される
    理由: 雛形の時点では未実装であることを Red として明示するため。
          本実装に着手したら、このテストを実際の仕様のテストへ置き換える
    """
    with pytest.raises(NotImplementedError):
        main.main([])
