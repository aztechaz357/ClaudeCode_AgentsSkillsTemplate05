"""check_deliverables.py のテスト。

7 点セットの正は `.claude/skills/agile-process/deliverables.md`。
このテストは「そろっている一式を通すこと」と「欠けを検出できること」の
両方を検証する。後者を落とすと、永遠に緑のまま何も検査しないツールになる
（tool-authoring スキルの「ツールを作ったら必ず確認すること」）。

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

import check_deliverables

BACKLOG = """\
# 例のプロジェクト — バックログ

## 現在地

- **いま着手中**: なし

## スライス

| S## | スライス | 成熟度 | 価値 | 次の一手 | 文書 |
|---|---|---|---|---|---|
| S01 | 骨組み | `L1 動く` | 高 | 失敗経路 | [S01](slices/S01-count.md) |
| S02 | フィルタ | `L0 未着手` | 中 | 着手 | — |
"""

DESIGN = """\
# S01. 骨組み

## 構成

```mermaid
flowchart TD
  P["CLI"] --> A["ユースケース"]
```

- 触るファイル: `src/tool/presentation/cli.py`

## 判断の記録

- **採用**: 1 経路だけ通す。**そう考えた理由**: 先に土台が要るため
- **他の選択肢**: 全機能を先に設計する
- **メリット / デメリット**: 採用案 = 早く動く / 網羅性は無い
"""

TEST_REPORT = """\
# S01 テスト結果

```
$ uv run pytest -q
3 passed
```

| 仕様 | テスト | 結果 |
|---|---|---|
| 1-1 | test_count | 緑 |
"""

MANUAL = """\
# マニュアル

## 1. 環境構築

```
uv sync
```

## 2. 実行方法

```
uv run tool count data.csv
```

## 3. テストの実行方法

```
uv run pytest -q
```

## S01 行数を数える

使い方の説明。
"""


def _make_repo(root: Path, **override: str | None) -> None:
    """7 点セットがそろった最小のリポジトリを作る。

    Args:
        root: 作成先。
        override: 相対パス → 中身。None を渡すとそのファイルを作らない。
    """
    files: dict[str, str | None] = {
        "docs/backlog.md": BACKLOG,
        "docs/usdm/src/S01-count.html": "<html><body>要求</body></html>",
        "docs/design/S01-count.md": DESIGN,
        "docs/test-reports/S01-count.md": TEST_REPORT,
        "docs/slices/S01-count.md": "# S01\n\n実績あり。\n",
        "docs/manual.md": MANUAL,
    }
    files.update(override)
    for name, body in files.items():
        if body is None:
            continue
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")


def _run(root: Path, *args: str) -> tuple[int, str]:
    """ツールを走らせ、終了コードと標準出力を返す。"""
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = check_deliverables.main([str(root), *args])
    return code, buf.getvalue()


class OkTest(unittest.TestCase):
    """一式がそろっていれば通ること。"""

    def test_complete_set_exits_0(self) -> None:
        """7点そろっていれば終了コード0。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            code, out = _run(root)
            self.assertEqual(code, 0, out)
            self.assertIn("S01", out)

    def test_skips_l0_slices(self) -> None:
        """L0のスライスは検査対象にしない。"""
        # S02 は L0 未着手。成果物が 1 つも無いが、それが正常。
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root)
            code, out = _run(root)
            self.assertEqual(code, 0, out)
            self.assertNotIn("S02", out)
            self.assertIn("all 1 slices OK", out)


class MissingTest(unittest.TestCase):
    """欠けを検出できること（ここが落ちると検査しないツールになる）。"""

    def test_fails_without_design(self) -> None:
        """設計書が無ければ落ちる。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root, **{"docs/design/S01-count.md": None})
            code, out = _run(root)
            self.assertEqual(code, 1)
            self.assertIn("設計書", out)

    def test_fails_without_test_report(self) -> None:
        """テスト結果まとめが無ければ落ちる。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root, **{"docs/test-reports/S01-count.md": None})
            code, out = _run(root)
            self.assertEqual(code, 1)
            self.assertIn("テスト結果", out)

    def test_fails_without_manual_section(self) -> None:
        """マニュアルに当該スライスの節が無ければ落ちる。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root, **{"docs/manual.md": MANUAL.replace("## S01 行数を数える", "")})
            code, out = _run(root)
            self.assertEqual(code, 1)
            self.assertIn("マニュアル", out)

    def test_fails_without_manual_common_sections(self) -> None:
        """マニュアルの共通3節が欠けたら落ちる。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root, **{"docs/manual.md": MANUAL.replace("## 1. 環境構築", "## はじめに")})
            code, out = _run(root)
            self.assertEqual(code, 1)
            self.assertIn("環境構築", out)

    def test_fails_when_design_has_no_diagram(self) -> None:
        """設計書に図が無ければ落ちる。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = DESIGN.replace("```mermaid", "```text")
            _make_repo(root, **{"docs/design/S01-count.md": body})
            code, out = _run(root)
            self.assertEqual(code, 1)
            self.assertIn("図", out)

    def test_fails_when_design_has_no_decision_record(self) -> None:
        """設計書に判断の記録が無ければ落ちる。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = DESIGN.split("## 判断の記録")[0]
            _make_repo(root, **{"docs/design/S01-count.md": body})
            code, out = _run(root)
            self.assertEqual(code, 1)
            self.assertIn("判断の記録", out)

    def test_fails_when_report_has_no_measured_output(self) -> None:
        """テスト結果まとめに実測の出力が無ければ落ちる。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = "# S01 テスト結果\n\n全部緑でした。\n"
            _make_repo(root, **{"docs/test-reports/S01-count.md": body})
            code, out = _run(root)
            self.assertEqual(code, 1)
            self.assertIn("実測", out)

    def test_fails_on_leftover_placeholder(self) -> None:
        """雛形のプレースホルダが残っていれば落ちる。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = DESIGN.replace("先に土台が要るため", "{そう考えた理由}")
            _make_repo(root, **{"docs/design/S01-count.md": body})
            code, out = _run(root)
            self.assertEqual(code, 1)
            self.assertIn("雛形", out)


class ArgumentTest(unittest.TestCase):
    """引数と前提の扱い。"""

    def test_missing_backlog_exits_2(self) -> None:
        """バックログが無ければ終了コード2。"""
        with tempfile.TemporaryDirectory() as tmp:
            code, out = _run(Path(tmp))
            self.assertEqual(code, 2)
            self.assertIn("backlog", out)

    def test_slice_option_checks_one_slice(self) -> None:
        """スライスを指定すると1本だけ見る。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_repo(root, **{"docs/design/S01-count.md": None})
            code, out = _run(root, "--slice", "S02")
            self.assertEqual(code, 0, out)
            self.assertNotIn("設計書", out)


if __name__ == "__main__":
    unittest.main()
