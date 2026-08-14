"""sync_issues.py のローカルチケット（使用: local）のテスト。

ローカルチケットは **ハブ（docs/slices/S##-*.md）を書き換える** ので、
「履歴を消さないこと」と「2 回流しても差分が出ないこと」を固定する。
この 2 つが崩れると、チケットがただの現在値になりプロセス管理に使えない。

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

import sync_issues

BACKLOG = """\
# バックログ

## スライス

| ID | 名前 | 成熟度 |
|---|---|---|
| S01 | 骨組み | L3 到達 |
| S02 | CSV のフィルタ | L1 |
| S03 | 集計 | L0 未着手 |

## 負債

| ID | 内容 | 出所 | 痛み | 返す条件 |
|---|---|---|---|---|
| D01 | 逆流している | S02 | 中 | L2 |
"""

HUB = """\
# S02 CSV のフィルタ

## 7 点セット

- 要求仕様書: docs/usdm/src/S02-csv.html
"""

PROFILE = """\
# CLAUDE.md

### チケット追跡

- 使用: local
- リポジトリ: なし
"""


def _repo(root: Path, keys: tuple[str, ...] = ("S01", "S02", "S03")) -> None:
    """CLAUDE.md・バックログ・ハブを置いた最小のリポジトリを作る。"""
    (root / "docs" / "slices").mkdir(parents=True)
    (root / "CLAUDE.md").write_text(PROFILE, encoding="utf-8")
    (root / "docs" / "backlog.md").write_text(BACKLOG, encoding="utf-8")
    for key in keys:
        (root / "docs" / "slices" / f"{key}-x.md").write_text(
            HUB.replace("S02 CSV のフィルタ", f"{key} x"), encoding="utf-8"
        )


class TicketFieldTest(unittest.TestCase):
    """バックログの行 → チケットの状態・目標。"""

    def test_l0_is_not_started(self) -> None:
        row = sync_issues.Row("S03", "集計", 0, False)
        self.assertEqual(sync_issues.ticket_state(row), "未着手")
        self.assertEqual(sync_issues.ticket_goal(row), "L0 → L1")

    def test_l1_is_in_progress(self) -> None:
        row = sync_issues.Row("S02", "CSV", 1, False)
        self.assertEqual(sync_issues.ticket_state(row), "進行中")
        self.assertEqual(sync_issues.ticket_goal(row), "L1 → L2")

    def test_done_is_closed(self) -> None:
        row = sync_issues.Row("S01", "骨組み", 3, True)
        self.assertEqual(sync_issues.ticket_state(row), "完了")


class ReadTicketTest(unittest.TestCase):
    """ハブからチケット節を読む。"""

    def test_missing_section_is_none(self) -> None:
        """節が無いのは「未起票」。空の辞書と区別する。"""
        self.assertIsNone(sync_issues.read_ticket(HUB))

    def test_reads_state_and_goal(self) -> None:
        row = sync_issues.Row("S02", "CSV", 1, False)
        text = sync_issues._insert_ticket(
            HUB, sync_issues.build_ticket_section(row, "2026-08-14")
        )
        found = sync_issues.read_ticket(text)
        self.assertEqual(found["状態"], "進行中")
        self.assertEqual(found["目標"], "L1 → L2")

    def test_ticket_goes_under_the_title(self) -> None:
        """チケット節は H1 の直後に入る（先頭でも末尾でもない）。"""
        row = sync_issues.Row("S02", "CSV", 1, False)
        text = sync_issues._insert_ticket(
            HUB, sync_issues.build_ticket_section(row, "2026-08-14")
        )
        self.assertLess(text.index("# S02"), text.index("## チケット"))
        self.assertLess(text.index("## チケット"), text.index("## 7 点セット"))

    def test_ticket_goes_under_the_title_with_bom(self) -> None:
        """BOM 付き UTF-8 のハブでも、節が題名より上に入らない。

        Windows のエディタと `Out-File -Encoding utf8` は BOM を付ける。
        BOM を無視しないと 1 行目が H1 と認識されず、節が先頭に入る。
        """
        row = sync_issues.Row("S02", "CSV", 1, False)
        text = sync_issues._insert_ticket(
            "﻿" + HUB, sync_issues.build_ticket_section(row, "2026-08-14")
        )
        self.assertLess(text.index("# S02"), text.index("## チケット"))


class UpdateTicketTest(unittest.TestCase):
    """状態を直しても履歴を消さない。"""

    def _seed(self) -> str:
        row = sync_issues.Row("S02", "CSV", 1, False)
        return sync_issues._insert_ticket(
            HUB, sync_issues.build_ticket_section(row, "2026-08-14")
        )

    def test_keeps_earlier_history(self) -> None:
        """更新しても起票の履歴が残る（追記であって上書きではない）。"""
        text = self._seed()
        after = sync_issues.update_ticket(
            text, sync_issues.Row("S02", "CSV", 2, False), "2026-08-15", "更新"
        )
        self.assertIn("2026-08-14 起票", after)
        self.assertIn("2026-08-15 更新", after)

    def test_updates_state_and_goal(self) -> None:
        text = self._seed()
        after = sync_issues.update_ticket(
            text, sync_issues.Row("S02", "CSV", 3, True), "2026-08-15", "完了"
        )
        found = sync_issues.read_ticket(after)
        self.assertEqual(found["状態"], "完了")
        self.assertEqual(found["目標"], "L3（到達済み）")

    def test_new_entry_joins_the_history_list(self) -> None:
        """追記は最後の履歴項目の直後に入る（注記 `> …` の下に落ちない）。

        落ちるとリストが割れ、Markdown として履歴が 2 つに分かれて読める。
        """
        text = self._seed()
        after = sync_issues.update_ticket(
            text, sync_issues.Row("S02", "CSV", 2, False), "2026-08-15", "更新"
        )
        self.assertLess(after.index("2026-08-15 更新"), after.index("> 進捗の正は"))

    def test_history_stays_in_order(self) -> None:
        """2 回追記しても時系列の順に並ぶ。"""
        text = self._seed()
        once = sync_issues.update_ticket(
            text, sync_issues.Row("S02", "CSV", 2, False), "2026-08-15", "更新"
        )
        twice = sync_issues.update_ticket(
            once, sync_issues.Row("S02", "CSV", 3, True), "2026-08-16", "完了"
        )
        self.assertLess(twice.index("2026-08-14"), twice.index("2026-08-15"))
        self.assertLess(twice.index("2026-08-15"), twice.index("2026-08-16"))

    def test_does_not_touch_other_sections(self) -> None:
        text = self._seed()
        after = sync_issues.update_ticket(
            text, sync_issues.Row("S02", "CSV", 2, False), "2026-08-15", "更新"
        )
        self.assertIn("- 要求仕様書: docs/usdm/src/S02-csv.html", after)


class PlanLocalTest(unittest.TestCase):
    """差分の計算。"""

    def test_creates_for_slices_without_ticket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root)
            changes = sync_issues.plan_local(BACKLOG, root)
        keys = [change.key for change in changes]
        # S01 は L3 到達済みなので既定では起票しない
        self.assertEqual(keys, ["S02", "S03"])
        self.assertTrue(all(change.action == "起票" for change in changes))

    def test_debt_is_not_a_local_ticket(self) -> None:
        """負債表の行そのものがチケット。写しを作らない。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root)
            changes = sync_issues.plan_local(BACKLOG, root)
        self.assertNotIn("D01", [change.key for change in changes])

    def test_include_done_creates_l3(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root)
            changes = sync_issues.plan_local(BACKLOG, root, include_done=True)
        self.assertIn("S01", [change.key for change in changes])

    def test_missing_hub_is_reported_not_crashed(self) -> None:
        """ハブが無いスライスは、落ちずに「ハブが無い」と報告する。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root, keys=("S01",))
            changes = sync_issues.plan_local(BACKLOG, root)
        missing = [change for change in changes if change.path is None]
        self.assertEqual([change.key for change in missing], ["S02", "S03"])

    def test_is_idempotent_after_apply(self) -> None:
        """反映後に同じ計算をすると差分が消える（何度流しても安全）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root)
            sync_issues.apply_local(sync_issues.plan_local(BACKLOG, root))
            again = sync_issues.plan_local(BACKLOG, root)
        self.assertEqual(again, [])

    def test_detects_maturity_change(self) -> None:
        """バックログで成熟度が上がったら更新の差分が出る。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root)
            sync_issues.apply_local(sync_issues.plan_local(BACKLOG, root))
            moved = BACKLOG.replace("| S02 | CSV のフィルタ | L1 |", "| S02 | CSV のフィルタ | L2 |")
            changes = sync_issues.plan_local(moved, root)
        self.assertEqual([(c.key, c.action) for c in changes], [("S02", "更新")])

    def test_detects_completion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root)
            sync_issues.apply_local(sync_issues.plan_local(BACKLOG, root))
            done = BACKLOG.replace(
                "| S02 | CSV のフィルタ | L1 |", "| S02 | CSV のフィルタ | L3 到達 |"
            )
            changes = sync_issues.plan_local(done, root)
        self.assertEqual([(c.key, c.action) for c in changes], [("S02", "完了")])


class MainLocalTest(unittest.TestCase):
    """CLI の終了コードと、既定が dry-run であること。"""

    def _run(self, argv: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = sync_issues.main(argv)
        return code, buffer.getvalue()

    def test_dry_run_does_not_write(self) -> None:
        """--apply なしではハブを 1 文字も変えない。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root)
            before = (root / "docs" / "slices" / "S02-x.md").read_text(encoding="utf-8")
            code, out = self._run([tmp])
            after = (root / "docs" / "slices" / "S02-x.md").read_text(encoding="utf-8")
        self.assertEqual(code, 1)
        self.assertEqual(before, after)
        self.assertIn("未反映", out)

    def test_apply_writes_and_then_is_clean(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root)
            code, _ = self._run([tmp, "--apply"])
            self.assertEqual(code, 0)
            second, out = self._run([tmp])
        self.assertEqual(second, 0)
        self.assertIn("同期済み", out)

    def test_off_refuses(self) -> None:
        """off のときは書き込まず 2 で拒否する。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root)
            (root / "CLAUDE.md").write_text(
                PROFILE.replace("使用: local", "使用: off"), encoding="utf-8"
            )
            code, out = self._run([tmp, "--apply"])
        self.assertEqual(code, 2)
        self.assertIn("REFUSED", out)


if __name__ == "__main__":
    unittest.main()
