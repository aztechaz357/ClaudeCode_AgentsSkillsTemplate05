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


DESIGN_S01 = """\
# S01. 行数を数える — 設計

## 主張（契約式）

| ID | 種別 | 主張 | assert | 状態 | 根拠 |
|---|---|---|---|---|---|
| Q1 | 事後 | `count(in) = \\|in\\|` | `assert n == len(rows)` | ⊢ | `test_counts_rows` |
| Q2 | 事後 | `in = ∅ → count(in) = 0` | `assert n == 0` | ⊢ | `test_empty` |
"""

DESIGN_S02 = """\
# S02. 列で絞り込む — 設計

## 主張（契約式）

| ID | 種別 | 主張 | assert | 状態 | 根拠 |
|---|---|---|---|---|---|
| Q1 | 事後 | `∀r ∈ out. r ∈ in` | `assert all(r in rows for r in out)` | ⊢ | `test_subset` |
| Q2 | 事後 | `∀r ∈ in. pred(r) → r ∈ out` | `assert all(...)` | ⊬ | 未（D02） |
"""


def _make_repo(root: Path, backlog: str = BACKLOG) -> None:
    """バックログだけがある最小のリポジトリを作る。"""
    path = root / "docs" / "backlog.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(backlog, encoding="utf-8")


def _make_designs(root: Path) -> None:
    """主張の表を持つ設計書を 2 枚置く（⊢ 3 本・⊬ 1 本）。"""
    design = root / "docs" / "design"
    design.mkdir(parents=True, exist_ok=True)
    (design / "S01-count.md").write_text(DESIGN_S01, encoding="utf-8")
    (design / "S02-filter.md").write_text(DESIGN_S02, encoding="utf-8")


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

    def test_renders_goal_and_current_position(self) -> None:
        """ゴールと現在地を載せる。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            code, out = _run(root)
            self.assertEqual(code, 0, out)
            page = _page(root)
            self.assertIn("CSV を素早く検分できる道具", page)
            self.assertIn("S02 段4 実装中", page)

    def test_renders_maturity_and_completeness_per_slice(self) -> None:
        """スライスごとの成熟度と充足を載せる。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            _run(root)
            page = _page(root)
            for ident in ("S01", "S02", "S03"):
                self.assertIn(ident, page)
            self.assertIn("設計書", page)

    def test_counts_debts_and_high_pain(self) -> None:
        """負債の件数と痛み高を数える。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            _run(root)
            page = _page(root)
            # 未返却は D01 と D02 の 2 件、うち痛み 高 は D02 の 1 件
            self.assertIn("未返却 2 件", page)
            self.assertIn("痛み 高 1 件", page)

    def test_has_no_external_references(self) -> None:
        """外部への参照を持たない。"""
        # 自己完結（file:// で開ける）。CDN・リモート画像・通信を含めない。
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            _run(root)
            page = _page(root)
            for bad in ("http://", "https://", "<script src", "<link rel=\"stylesheet\" href"):
                self.assertNotIn(bad, page)

    def test_survives_without_git(self) -> None:
        """gitが無くても落ちない。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            code, out = _run(root)
            self.assertEqual(code, 0, out)


class ClaimsTest(unittest.TestCase):
    """主張（契約式）の一覧。

    **この 1 画面が、人が正しさを判断する唯一の監査面** 。散文の要約では
    「保証が減ったこと」に気づけないので、⊢ / ⊬ をそのまま数えて出す
    （規約: `.claude/skills/verifiable-claims/SKILL.md`）。
    """

    def test_counts_proved_and_unproved(self) -> None:
        """⊢ と ⊬ の件数をカードに出す。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            _make_designs(root)
            _run(root)
            page = _page(root)
        self.assertIn("⊢ 3 / ⊬ 1", page)

    def test_lists_each_claim_with_its_slice(self) -> None:
        """主張を 1 行 1 主張で、どのスライスのものか分かる形で並べる。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            _make_designs(root)
            _run(root)
            page = _page(root)
        self.assertIn("test_subset", page)
        self.assertIn("pred(r)", page)

    def test_unproved_comes_first(self) -> None:
        """⊬（未証明 = 負債）を先頭に置く。

        証明済みが先に並ぶと、読む人は最後まで読まないと負債に届かない。
        **読まれない記録は無いのと同じ** なので、順序で優先度を示す。
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            _make_designs(root)
            _run(root)
            page = _page(root)
        section = page.split("主張（契約式）", 1)[1]
        self.assertLess(section.index("⊬"), section.index("⊢"))

    def test_says_so_when_there_are_no_claims(self) -> None:
        """主張がまだ 1 本も無いときは、空であることを明示する。

        表を黙って省くと「主張が無い」のか「節を作っていない」のか
        区別できず、L1 の条件（事後条件 1 本以上 ⊢）を判定できない。
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            code, out = _run(root)
            self.assertEqual(code, 0, out)
            page = _page(root)
        self.assertIn("主張（契約式）", page)
        self.assertIn("まだ無い", page)

    def test_reports_the_counts_on_stdout(self) -> None:
        """標準出力の 1 行にも件数を出す（HTML を開かずに分かる）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            _make_designs(root)
            _, out = _run(root)
        self.assertIn("⊢ 3 / ⊬ 1", out)


class ArgumentTest(unittest.TestCase):
    """前提が欠けたときの振る舞い。"""

    def test_missing_backlog_exits_2(self) -> None:
        """バックログが無ければ終了コード2。"""
        with tempfile.TemporaryDirectory() as tmp:
            code, out = _run(Path(tmp))
            self.assertEqual(code, 2)
            self.assertIn("backlog", out)


if __name__ == "__main__":
    unittest.main()
