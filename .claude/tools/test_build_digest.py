"""build_digest.py のテスト。

このツールの価値は「全部を読まなくてよくすること」なので、
次の 2 つを重点的に検証する:

    - **影響度 高 を取りこぼさない**（読み落としだけが事故）
    - 低いものを高く見せない（毎回全部が「高」なら絞る意味が無い）

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

import build_digest

# git log --pretty=format:%x01%H%x09%ad%x09%s --date=short --name-only の形
LOG = "\n".join(
    [
        "\x01aaaaaaa\t2026-08-12\t設計: S03 の層と契約を決める",
        "docs/design/S03-filter.md",
        "",
        "\x01bbbbbbb\t2026-08-12\t実装: フィルタを足す",
        "src/tool/application/filter.py",
        "",
        "\x01ccccccc\t2026-08-11\tテスト: 境界値を足す",
        "test/application/test_filter.py",
        "",
        "\x01ddddddd\t2026-08-11\tdocs: 判断を ADR に残す",
        "docs/decisions/ADR-003-backlog-is-the-source.md",
        "",
        "\x01eeeeeee\t2026-08-10\tdocs: マニュアルに S03 を足す",
        "docs/manual.md",
        "",
    ]
)

BACKLOG_DIFF = """\
diff --git a/docs/backlog.md b/docs/backlog.md
--- a/docs/backlog.md
+++ b/docs/backlog.md
@@
-| S03 | 集計の出力 | `L0 未着手` | 中 | 着手 | — |
+| S03 | 集計の出力 | `L1 動く` | 中 | 失敗経路（L2） | [S03](slices/S03-sum.md) |
+| D04 | 出力先をハードコード | S03 | 低 | ファイル出力が要るとき | 未 |
-| D02 | 逆流している | S02 | 中 | 2 か所目が出たとき | 未 |
+| D02 | 逆流している | S02 | 中 | 2 か所目が出たとき | 済（abc1234） |
"""


class ParseLogTest(unittest.TestCase):
    """git log の読み取り。"""

    def test_reads_every_commit(self) -> None:
        """レコード区切りで 5 件を読む。"""
        commits = build_digest.parse_log(LOG)
        self.assertEqual(len(commits), 5)

    def test_reads_subject_and_files(self) -> None:
        """件名と触ったファイルを組で読む。"""
        first = build_digest.parse_log(LOG)[0]
        self.assertEqual(first.subject, "設計: S03 の層と契約を決める")
        self.assertEqual(first.files, ["docs/design/S03-filter.md"])
        self.assertEqual(first.date, "2026-08-12")

    def test_empty_log_is_empty(self) -> None:
        """未読が無いときは空（例外にしない）。"""
        self.assertEqual(build_digest.parse_log(""), [])


class ImpactTest(unittest.TestCase):
    """影響度の判定（後から変えにくいものが「高」）。"""

    def _impact(self, subject: str, files: list[str]) -> str:
        return build_digest.classify(build_digest.Commit("x", "2026-08-12", subject, files)).level

    def test_adr_is_high(self) -> None:
        """ADR は最も高い（2 つ以上のスライスが従う）。"""
        self.assertEqual(self._impact("docs: 判断を残す", ["docs/decisions/ADR-003-x.md"]), "高")

    def test_design_is_high(self) -> None:
        """設計書は「判断の記録」を含むので高い。"""
        self.assertEqual(self._impact("設計: 層を決める", ["docs/design/S03-filter.md"]), "高")

    def test_requirement_is_high(self) -> None:
        """要求（USDM）の変更も高い。"""
        self.assertEqual(self._impact("要求: 仕様を足す", ["docs/usdm/src/S03-filter.html"]), "高")

    def test_profile_is_high(self) -> None:
        """CLAUDE.md（プロファイル）は全エージェントが従う。"""
        self.assertEqual(self._impact("docs: コマンドを直す", ["CLAUDE.md"]), "高")

    def test_convention_is_high(self) -> None:
        """.claude/ の規約変更も高い。"""
        self.assertEqual(self._impact("プロセス: 段を足す", [".claude/commands/iterate.md"]), "高")

    def test_dependency_is_high(self) -> None:
        """依存の追加は後から外しにくい。"""
        self.assertEqual(self._impact("実装: 依存を足す", ["pyproject.toml"]), "高")

    def test_implementation_is_middle(self) -> None:
        """実装は局所的なので中。"""
        self.assertEqual(self._impact("実装: フィルタ", ["src/tool/application/filter.py"]), "中")

    def test_test_only_is_low(self) -> None:
        """テストだけの変更は低い（結果の記録であって判断ではない）。"""
        self.assertEqual(self._impact("テスト: 境界値", ["test/test_filter.py"]), "低")

    def test_manual_is_low(self) -> None:
        """マニュアル・テスト結果まとめは低い。"""
        self.assertEqual(self._impact("docs: マニュアル", ["docs/manual.md"]), "低")

    def test_reason_is_given(self) -> None:
        """なぜ高いのかを 1 語で返す（並べ替えの根拠を人が読めるように）。"""
        found = build_digest.classify(
            build_digest.Commit("x", "2026-08-12", "docs: ADR", ["docs/decisions/ADR-003-x.md"])
        )
        self.assertEqual(found.kind, "ADR")


class BacklogDiffTest(unittest.TestCase):
    """バックログの差分（成熟度と負債の動き）。"""

    def test_reads_maturity_change(self) -> None:
        """L0 → L1 の変化を読む。"""
        change = build_digest.parse_backlog_diff(BACKLOG_DIFF)
        self.assertEqual(change.maturity, [("S03", 0, 1)])

    def test_reads_new_debt(self) -> None:
        """増えた負債を読む。"""
        self.assertEqual(build_digest.parse_backlog_diff(BACKLOG_DIFF).added_debts, ["D04"])

    def test_reads_paid_debt(self) -> None:
        """返した負債（未 → 済）を読む。"""
        self.assertEqual(build_digest.parse_backlog_diff(BACKLOG_DIFF).paid_debts, ["D02"])

    def test_empty_diff_is_quiet(self) -> None:
        """差分が無ければ何も言わない。"""
        change = build_digest.parse_backlog_diff("")
        self.assertEqual(change.maturity, [])
        self.assertEqual(change.added_debts, [])


class DigestTest(unittest.TestCase):
    """ダイジェストの本文。"""

    def _text(self) -> str:
        return build_digest.build(
            build_digest.parse_log(LOG), build_digest.parse_backlog_diff(BACKLOG_DIFF)
        )

    def test_high_comes_first(self) -> None:
        """後戻りが高いものを先頭に出す。"""
        text = self._text()
        self.assertLess(text.index("ADR-003"), text.index("S03-filter.md"))

    def test_low_is_counted_not_listed(self) -> None:
        """低いものは件数だけにする（並べると絞る意味が消える）。"""
        text = self._text()
        self.assertNotIn("docs/manual.md", text)
        self.assertIn("文書 1 件", text)

    def test_shows_maturity_and_debt(self) -> None:
        """成熟度と負債の動きを 1 行で出す。"""
        text = self._text()
        self.assertIn("S03 L0 → L1", text)
        self.assertIn("増 1 件", text)
        self.assertIn("返 1 件", text)

    def test_suggests_what_to_read(self) -> None:
        """次に読むものを 1 つだけ名指しする。"""
        self.assertIn("次に読むなら", self._text())

    def test_caps_the_high_list(self) -> None:
        """高が多すぎるときは上限で切る（読む量を増やさない）。"""
        many = "\n".join(
            f"\x01{index:07d}\t2026-08-12\t設計: {index}\ndocs/design/S{index:02d}-x.md\n"
            for index in range(10)
        )
        text = build_digest.build(build_digest.parse_log(many), build_digest.parse_backlog_diff(""))
        # 並べるのは上限まで（末尾の「次に読むなら」の 1 件は案内なので数えない）
        listed = [line for line in text.splitlines() if line.startswith("  [")]
        self.assertLessEqual(len(listed), build_digest.HIGH_LIMIT)
        self.assertIn("他 5 件", text)


class MainTest(unittest.TestCase):
    """終了コード（0 = 追いついている / 1 = 未読あり / 2 = エラー）。"""

    def _record(self, log: str = LOG, head: str = "1234567") -> list[list[str]]:
        calls: list[list[str]] = []

        def _fake(args: list[str]) -> tuple[int, str]:
            # 引数は `-C <root> log …` の形。位置ではなく含まれる語で判定する
            calls.append(args)
            if "log" in args:
                return 0, log
            if "diff" in args:
                return 0, BACKLOG_DIFF
            if "rev-parse" in args:
                return 0, head
            return 0, ""

        original = build_digest.RUNNER
        build_digest.RUNNER = _fake
        self.addCleanup(lambda: setattr(build_digest, "RUNNER", original))
        return calls

    def _run(self, argv: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = build_digest.main(argv)
        return code, buffer.getvalue()

    def test_unread_exits_one(self) -> None:
        """未読があれば 1。"""
        self._record()
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self._run([tmp])
        self.assertEqual(code, 1)
        self.assertIn("未読: 5 コミット", out)

    def test_caught_up_exits_zero(self) -> None:
        """未読が無ければ 0 と 1 行だけ。"""
        self._record(log="")
        with tempfile.TemporaryDirectory() as tmp:
            code, out = self._run([tmp])
        self.assertEqual(code, 0)
        self.assertIn("追いついています", out)

    def test_mark_writes_marker(self) -> None:
        """--mark で既読地点を HEAD に進める。"""
        self._record()
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = self._run([tmp, "--mark"])
            marker = Path(tmp) / ".steering" / "last-reviewed"
            self.assertEqual(marker.read_text(encoding="utf-8").strip(), "1234567")
        self.assertEqual(code, 0)

    def test_reads_marker_as_since(self) -> None:
        """マーカーがあれば、そこからの範囲を git に渡す。"""
        calls = self._record()
        with tempfile.TemporaryDirectory() as tmp:
            steering = Path(tmp) / ".steering"
            steering.mkdir()
            (steering / "last-reviewed").write_text("abc1234\n", encoding="utf-8")
            self._run([tmp])
        ranges = [arg for call in calls for arg in call if "abc1234.." in arg]
        self.assertTrue(ranges, f"マーカーが範囲に使われていない: {calls}")


if __name__ == "__main__":
    unittest.main()
