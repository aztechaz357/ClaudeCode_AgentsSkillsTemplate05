"""sync_issues.py のテスト。

このツールは **外部（GitHub）へ書き込む差分を計算する** ので、
「差分を出せること」だけでなく次の 2 つを重点的に検証する:

    - 同期済みのときに余計な作成を出さない（重複起票は取り消しにくい）
    - `使用: off` のときに何も計算せず拒否する（誤送信の構造的な防止）

実行（前置コマンドはプロファイルの「.claude/tools/ の Python ツール実行」）:
    <ツール実行コマンド> -m unittest discover -s .claude/tools -p "test_*.py" -v
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sync_issues

BACKLOG = """\
# 例のプロジェクト — バックログ

## 現在地

- **いま着手中**: S02 段4 実装中（coder）

## スライス

| S## | スライス | 成熟度 | 価値 | 次の一手 | ハブ |
|---|---|---|---|---|---|
| S01 | 骨組み | `L3 整った` | 高 | なし | [S01](slices/S01-skeleton.md) |
| S02 | CSV のフィルタ | `L1 動く` | 高 | 失敗経路（L2） | [S02](slices/S02-filter.md) |
| S03 | 集計の出力 | `L0 未着手` | 中 | 着手 | — |
| S## | {次に増やす価値} | `L0 未着手` | 高 | 着手 | — |

## 負債

| D## | 内容 | 出所 | 痛み | 返す条件 | 状態 |
|---|---|---|---|---|---|
| D01 | 出力先をハードコード | S02 | 低 | ファイル出力が要るとき | 未 |
| D02 | 逆流している | S02 | 中 | 2 か所目が出たとき | 済（abc1234） |
"""


def _issue(number: int, title: str, state: str = "OPEN", labels: list[str] | None = None) -> dict:
    return {
        "number": number,
        "title": title,
        "state": state,
        "labels": [{"name": name} for name in (labels or [])],
    }


class ParseBacklogTest(unittest.TestCase):
    """バックログの行の読み取り。"""

    def test_reads_slices_and_debts(self) -> None:
        """スライス 3 本と負債 2 件を読む（雛形の `S##` 行は数えない）。"""
        rows = sync_issues.parse_backlog(BACKLOG)
        self.assertEqual([row.key for row in rows], ["S01", "S02", "S03", "D01", "D02"])

    def test_reads_name_and_maturity(self) -> None:
        """スライス名と成熟度を読む。"""
        rows = {row.key: row for row in sync_issues.parse_backlog(BACKLOG)}
        self.assertEqual(rows["S02"].name, "CSV のフィルタ")
        self.assertEqual(rows["S02"].maturity, 1)
        self.assertEqual(rows["S01"].maturity, 3)

    def test_reads_debt_state(self) -> None:
        """返した負債（済）と未返却を区別する。"""
        rows = {row.key: row for row in sync_issues.parse_backlog(BACKLOG)}
        self.assertFalse(rows["D01"].done)
        self.assertTrue(rows["D02"].done)

    def test_labels_by_kind(self) -> None:
        """スライスは slice + 成熟度、負債は debt のラベルになる。"""
        rows = {row.key: row for row in sync_issues.parse_backlog(BACKLOG)}
        self.assertEqual(rows["S02"].labels, ["slice", "L1"])
        self.assertEqual(rows["D01"].labels, ["debt"])


class PlanTest(unittest.TestCase):
    """差分の計算（GitHub には触らない）。"""

    def test_creates_missing_issues(self) -> None:
        """Issue が 1 本も無ければ、L3 以外と未返却の負債を作る。"""
        plan = sync_issues.plan(BACKLOG, [])
        self.assertEqual([item.key for item in plan.create], ["S02", "S03", "D01"])

    def test_skips_done_rows_by_default(self) -> None:
        """L3 のスライスと返済済みの負債は既定で作らない。"""
        keys = [item.key for item in sync_issues.plan(BACKLOG, []).create]
        self.assertNotIn("S01", keys)
        self.assertNotIn("D02", keys)

    def test_include_done_creates_them(self) -> None:
        """--include-done なら L3 も作る（履歴として残したいとき）。"""
        plan = sync_issues.plan(BACKLOG, [], include_done=True)
        self.assertIn("S01", [item.key for item in plan.create])

    def test_no_diff_when_synced(self) -> None:
        """同期済みなら作成も更新も 0 件（重複起票を出さない）。"""
        issues = [
            _issue(1, "S02: CSV のフィルタ", labels=["slice", "L1"]),
            _issue(2, "S03: 集計の出力", labels=["slice", "L0"]),
            _issue(3, "D01: 出力先をハードコード", labels=["debt"]),
        ]
        plan = sync_issues.plan(BACKLOG, issues)
        self.assertEqual(plan.create, [])
        self.assertEqual(plan.update, [])
        self.assertEqual(plan.close, [])
        self.assertTrue(plan.is_empty)

    def test_updates_stale_label(self) -> None:
        """成熟度が上がったらラベルの張り替えを出す。"""
        issues = [
            _issue(1, "S02: CSV のフィルタ", labels=["slice", "L0"]),
            _issue(2, "S03: 集計の出力", labels=["slice", "L0"]),
            _issue(3, "D01: 出力先をハードコード", labels=["debt"]),
        ]
        plan = sync_issues.plan(BACKLOG, issues)
        self.assertEqual([item.number for item in plan.update], [1])
        self.assertIn("L1", plan.update[0].labels)

    def test_updates_renamed_title(self) -> None:
        """バックログでスライス名が変わったらタイトルを直す。"""
        issues = [_issue(1, "S02: 古い名前", labels=["slice", "L1"])]
        plan = sync_issues.plan(BACKLOG, issues)
        self.assertEqual(plan.update[0].title, "S02: CSV のフィルタ")

    def test_closes_finished_rows(self) -> None:
        """L3 に到達したスライスと返済済みの負債は閉じる。"""
        issues = [
            _issue(1, "S01: 骨組み", labels=["slice", "L2"]),
            _issue(2, "D02: 逆流している", labels=["debt"]),
        ]
        plan = sync_issues.plan(BACKLOG, issues)
        self.assertEqual(sorted(item.number for item in plan.close), [1, 2])

    def test_does_not_close_l1(self) -> None:
        """L1・L2 のスライスは閉じない（完了ではない）。"""
        issues = [_issue(1, "S02: CSV のフィルタ", labels=["slice", "L1"])]
        self.assertEqual(sync_issues.plan(BACKLOG, issues).close, [])

    def test_reopens_wrongly_closed(self) -> None:
        """まだ L1 なのに閉じられている Issue は差分として出す。"""
        issues = [_issue(1, "S02: CSV のフィルタ", state="CLOSED", labels=["slice", "L1"])]
        plan = sync_issues.plan(BACKLOG, issues)
        self.assertEqual([item.number for item in plan.reopen], [1])

    def test_pulls_external_issues(self) -> None:
        """接頭辞の無い open Issue は取り込み候補にする。"""
        issues = [_issue(9, "CSV が空だと落ちる")]
        plan = sync_issues.plan(BACKLOG, issues)
        self.assertEqual([item.number for item in plan.pull], [9])

    def test_ignores_closed_external_issues(self) -> None:
        """閉じた外部 Issue は取り込み候補にしない。"""
        issues = [_issue(9, "CSV が空だと落ちる", state="CLOSED")]
        self.assertEqual(sync_issues.plan(BACKLOG, issues).pull, [])


class BodyTest(unittest.TestCase):
    """Issue 本文（雛形の正はこのツールにだけ置く）。"""

    def test_slice_body_has_seven_deliverables(self) -> None:
        """スライスの本文に 7 点セットのチェックリストが入る。"""
        row = {row.key: row for row in sync_issues.parse_backlog(BACKLOG)}["S02"]
        body = sync_issues.build_body(row)
        for item in ("要求仕様書", "設計書", "単体テスト", "実装", "統合テスト", "テスト結果", "マニュアル"):
            self.assertIn(item, body)

    def test_body_states_backlog_is_the_source(self) -> None:
        """本文に「正はバックログ」と明記する（二重管理の防止）。"""
        row = {row.key: row for row in sync_issues.parse_backlog(BACKLOG)}["S02"]
        self.assertIn("docs/backlog.md", sync_issues.build_body(row))


class MainTest(unittest.TestCase):
    """終了コード（0 = 差分なし / 1 = 差分あり / 2 = エラー・off）。"""

    def _prepare(self, tmp: str, mode: str, issues: list[dict]) -> list[str]:
        root = Path(tmp)
        (root / "docs").mkdir()
        (root / "docs" / "backlog.md").write_text(BACKLOG, encoding="utf-8")
        (root / "CLAUDE.md").write_text(
            "# CLAUDE.md\n\n### Issue 追跡（GitHub Issues）\n\n"
            f"- 使用: {mode}\n- リポジトリ: owner/repo\n",
            encoding="utf-8",
        )
        issues_json = root / "issues.json"
        issues_json.write_text(json.dumps(issues, ensure_ascii=False), encoding="utf-8")
        return [str(root), "--issues-json", str(issues_json)]

    def _run(self, argv: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = sync_issues.main(argv)
        return code, buffer.getvalue()

    def test_off_is_refused(self) -> None:
        """`使用: off` なら差分を計算せず 2 で拒否する。"""
        with tempfile.TemporaryDirectory() as tmp:
            argv = self._prepare(tmp, "off", [])
            code, out = self._run(argv)
        self.assertEqual(code, 2)
        self.assertIn("off", out)

    def test_diff_exits_one(self) -> None:
        """差分があれば 1（まだ送信していない）。"""
        with tempfile.TemporaryDirectory() as tmp:
            argv = self._prepare(tmp, "on", [])
            code, out = self._run(argv)
        self.assertEqual(code, 1)
        self.assertIn("作成 3", out)

    def test_synced_exits_zero(self) -> None:
        """同期済みなら 0。"""
        issues = [
            _issue(1, "S02: CSV のフィルタ", labels=["slice", "L1"]),
            _issue(2, "S03: 集計の出力", labels=["slice", "L0"]),
            _issue(3, "D01: 出力先をハードコード", labels=["debt"]),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            argv = self._prepare(tmp, "on", issues)
            code, _ = self._run(argv)
        self.assertEqual(code, 0)

    def test_missing_backlog_exits_two(self) -> None:
        """バックログが無ければ 2。"""
        with tempfile.TemporaryDirectory() as tmp:
            argv = self._prepare(tmp, "on", [])
            (Path(tmp) / "docs" / "backlog.md").unlink()
            code, _ = self._run(argv)
        self.assertEqual(code, 2)

    def test_dry_run_does_not_call_gh(self) -> None:
        """既定は dry-run。gh の実行関数を差し替えて 1 度も呼ばれないことを確かめる。"""
        calls = self._record()
        with tempfile.TemporaryDirectory() as tmp:
            argv = self._prepare(tmp, "on", [])
            code, _ = self._run(argv)
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])

    def test_apply_calls_gh(self) -> None:
        """--apply のときだけ gh issue create を呼ぶ。"""
        calls = self._record()
        with tempfile.TemporaryDirectory() as tmp:
            argv = self._prepare(tmp, "on", [])
            code, _ = self._run(argv + ["--apply"])
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0][:3], ["issue", "create", "--repo"])

    def test_apply_failure_exits_one(self) -> None:
        """gh が失敗したら 1 を返す（成功と誤認しない）。"""
        self._record(exit_code=1, output="could not create issue")
        with tempfile.TemporaryDirectory() as tmp:
            argv = self._prepare(tmp, "on", [])
            code, out = self._run(argv + ["--apply"])
        self.assertEqual(code, 1)
        self.assertIn("NG", out)

    def _record(self, exit_code: int = 0, output: str = "") -> list[list[str]]:
        """gh の実行関数を記録用に差し替え、テスト終了時に戻す。"""
        calls: list[list[str]] = []

        def _fake(args: list[str]) -> tuple[int, str]:
            calls.append(args)
            return exit_code, output or "https://github.com/owner/repo/issues/1"

        original = sync_issues.RUNNER
        sync_issues.RUNNER = _fake
        self.addCleanup(lambda: setattr(sync_issues, "RUNNER", original))
        return calls


if __name__ == "__main__":
    unittest.main()
