"""build_status.py のテスト。

このツールは「エージェントに任せると大枠が見えなくなる」問題への答え。
1 画面で ゴール / 進捗 / 7 点セットの充足 / 負債 / 直近の作業 が読めること、
そして環境が欠けていても落ちないこと（git が無い等）を検証する。

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

import build_status

BACKLOG = """\
# 例のプロジェクト — バックログ

## 現在地

- **ゴール**: CSV を素早く検分できる道具
- **完走の定義**: `tool count data.csv` で件数が出る
- **骨組み**: 通った（S01・2026-08-01）
- **いま着手中**: S02 段4 実装中（coder）
- **次の一手**: 段5 統合テスト

## スライス

| S## | スライス | 成熟度 | 価値 | 次の一手 | 文書 |
|---|---|---|---|---|---|
| S01 | 行数を数える | `L2 固い` | 高 | 完了 | [S01](slices/S01-count.md) |
| S02 | 列で絞り込む | `L1 動く` | 高 | L2 へ | [S02](slices/S02-filter.md) |
| S03 | 集計する | `L0 未着手` | 中 | 着手 | — |

## 負債

| D## | 内容 | 出所 | 痛み | 返す条件 | 状態 |
|---|---|---|---|---|---|
| D01 | 出力先をハードコード | S01 | 低 | ファイル出力が要るとき | 未 |
| D02 | 逆流が 1 か所 | S02 | 高 | 2 か所目が出たとき | 未 |
| D03 | 命名の不統一 | S01 | 中 | L3 に上げるとき | 済（abc1234） |
"""


def _make_repo(root: Path, backlog: str = BACKLOG) -> None:
    """バックログだけがある最小のリポジトリを作る。"""
    path = root / "docs" / "backlog.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(backlog, encoding="utf-8")


def _run(root: Path, *args: str) -> tuple[int, str]:
    """ツールを走らせ、終了コードと標準出力を返す。"""
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = build_status.main([str(root), *args])
    return code, buf.getvalue()


def _page(root: Path) -> str:
    return (root / "docs" / "status.html").read_text(encoding="utf-8")


class RenderTest(unittest.TestCase):
    """1 画面に必要なものが載ること。"""

    def test_ゴールと現在地を載せる(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            code, out = _run(root)
            self.assertEqual(code, 0, out)
            page = _page(root)
            self.assertIn("CSV を素早く検分できる道具", page)
            self.assertIn("S02 段4 実装中", page)

    def test_スライスごとの成熟度と充足を載せる(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            _run(root)
            page = _page(root)
            for ident in ("S01", "S02", "S03"):
                self.assertIn(ident, page)
            self.assertIn("設計書", page)

    def test_負債の件数と痛み高を数える(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            _run(root)
            page = _page(root)
            # 未返却は D01 と D02 の 2 件、うち痛み 高 は D02 の 1 件
            self.assertIn("未返却 2 件", page)
            self.assertIn("痛み 高 1 件", page)

    def test_外部への参照を持たない(self) -> None:
        # 自己完結（file:// で開ける）。CDN・リモート画像・通信を含めない。
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            _run(root)
            page = _page(root)
            for bad in ("http://", "https://", "<script src", "<link rel=\"stylesheet\" href"):
                self.assertNotIn(bad, page)

    def test_gitが無くても落ちない(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            code, out = _run(root)
            self.assertEqual(code, 0, out)


class ArgumentTest(unittest.TestCase):
    """前提が欠けたときの振る舞い。"""

    def test_バックログが無ければ終了コード2(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, out = _run(Path(tmp))
            self.assertEqual(code, 2)
            self.assertIn("backlog", out)


if __name__ == "__main__":
    unittest.main()
