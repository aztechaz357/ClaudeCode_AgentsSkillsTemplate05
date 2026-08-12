"""issue_mode.py のテスト。

Issue 追跡の on / off は **全エージェントの振る舞いを変える設定** なので、
「読めること」だけでなく「読めないときに on と誤判定しないこと」を検証する
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

import issue_mode

PROFILE_OFF = """\
# CLAUDE.md

## プロジェクトプロファイル

### コマンド

| 用途 | コマンド |
|---|---|
| テスト | pytest |

### Issue 追跡（GitHub Issues）

- 使用: off
- リポジトリ: なし
- ラベル: slice / debt / L1 / L2 / L3

### ログ / Git

- 既定ブランチ: main
"""

PROFILE_ON = PROFILE_OFF.replace("使用: off", "使用: on").replace(
    "リポジトリ: なし", "リポジトリ: owner/repo"
)

PROFILE_NO_SECTION = """\
# CLAUDE.md

## プロジェクトプロファイル

### コマンド

| 用途 | コマンド |
|---|---|
| テスト | pytest |
"""


def _write(root: Path, text: str) -> Path:
    path = root / "CLAUDE.md"
    path.write_text(text, encoding="utf-8")
    return path


class ReadModeTest(unittest.TestCase):
    """設定の読み取り。"""

    def test_reads_off_without_repo(self) -> None:
        """`使用: off` と `リポジトリ: なし` を読み取る。"""
        setting = issue_mode.read_mode(PROFILE_OFF)
        self.assertEqual(setting.mode, "off")
        self.assertIsNone(setting.repo)

    def test_reads_on_with_repo(self) -> None:
        """`使用: on` とリポジトリ名を読み取る。"""
        setting = issue_mode.read_mode(PROFILE_ON)
        self.assertEqual(setting.mode, "on")
        self.assertEqual(setting.repo, "owner/repo")

    def test_missing_section_is_unknown(self) -> None:
        """Issue 追跡の節が無ければ判定不能（on と決めつけない）。"""
        setting = issue_mode.read_mode(PROFILE_NO_SECTION)
        self.assertIsNone(setting.mode)

    def test_invalid_value_is_unknown(self) -> None:
        """`使用: たぶん` を on 扱いしない（誤って外部送信するのを防ぐ）。"""
        setting = issue_mode.read_mode(PROFILE_OFF.replace("使用: off", "使用: たぶん"))
        self.assertIsNone(setting.mode)

    def test_placeholder_repo_is_unset(self) -> None:
        """雛形のままの `{例: owner/repo}` は未設定として扱う。"""
        text = PROFILE_ON.replace("リポジトリ: owner/repo", "リポジトリ: {例: owner/repo}")
        self.assertIsNone(issue_mode.read_mode(text).repo)

    def test_ignores_lines_outside_section(self) -> None:
        """別の節に `- 使用: on` があっても Issue 追跡の設定にしない。"""
        text = PROFILE_OFF.replace("### ログ / Git", "### ログ / Git\n\n- 使用: on\n")
        self.assertEqual(issue_mode.read_mode(text).mode, "off")


class SetModeTest(unittest.TestCase):
    """設定の書き換え（`使用:` の行だけを触る）。"""

    def test_turns_on(self) -> None:
        """off から on へ切り替え、リポジトリも書き込む。"""
        changed = issue_mode.set_mode(PROFILE_OFF, "on", repo="a/b")
        setting = issue_mode.read_mode(changed)
        self.assertEqual(setting.mode, "on")
        self.assertEqual(setting.repo, "a/b")

    def test_keeps_other_lines(self) -> None:
        """プロファイルの他の行を壊さない。"""
        changed = issue_mode.set_mode(PROFILE_OFF, "on")
        self.assertIn("| テスト | pytest |", changed)
        self.assertIn("- 既定ブランチ: main", changed)
        self.assertIn("- ラベル: slice / debt / L1 / L2 / L3", changed)

    def test_is_idempotent(self) -> None:
        """同じ値で 2 回書き換えても差分が出ない。"""
        once = issue_mode.set_mode(PROFILE_ON, "on", repo="owner/repo")
        twice = issue_mode.set_mode(once, "on", repo="owner/repo")
        self.assertEqual(once, twice)

    def test_turning_off_clears_repo(self) -> None:
        """off にするとリポジトリは「なし」に戻る。"""
        changed = issue_mode.set_mode(PROFILE_ON, "off")
        setting = issue_mode.read_mode(changed)
        self.assertEqual(setting.mode, "off")
        self.assertIsNone(setting.repo)

    def test_missing_section_raises(self) -> None:
        """節が無いプロファイルは書き換えず例外にする。"""
        with self.assertRaises(issue_mode.ProfileError):
            issue_mode.set_mode(PROFILE_NO_SECTION, "on")


class MainTest(unittest.TestCase):
    """終了コード（0 = on / 1 = off / 2 = 判定不能）。"""

    def _run(self, argv: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = issue_mode.main(argv)
        return code, buffer.getvalue()

    def test_on_exits_zero(self) -> None:
        """on のとき終了コード 0 とリポジトリ名を出す。"""
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), PROFILE_ON)
            code, out = self._run([tmp])
        self.assertEqual(code, 0)
        self.assertIn("on", out)
        self.assertIn("owner/repo", out)

    def test_off_exits_one(self) -> None:
        """off のとき終了コード 1。"""
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), PROFILE_OFF)
            code, out = self._run([tmp])
        self.assertEqual(code, 1)
        self.assertIn("off", out)

    def test_missing_section_exits_two(self) -> None:
        """節が無ければ終了コード 2。"""
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), PROFILE_NO_SECTION)
            code, _ = self._run([tmp])
        self.assertEqual(code, 2)

    def test_missing_claude_md_exits_two(self) -> None:
        """CLAUDE.md が無ければ終了コード 2。"""
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = self._run([tmp])
        self.assertEqual(code, 2)

    def test_set_writes_file(self) -> None:
        """--set on がファイルを書き換える。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(Path(tmp), PROFILE_OFF)
            code, _ = self._run([tmp, "--set", "on", "--repo", "a/b"])
            self.assertEqual(code, 0)
            text = path.read_text(encoding="utf-8")
        self.assertEqual(issue_mode.read_mode(text).mode, "on")
        self.assertEqual(issue_mode.read_mode(text).repo, "a/b")

    def test_set_off_exits_one(self) -> None:
        """書き換え後のモードを終了コードで返す（読み取りと同じ意味にする）。"""
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), PROFILE_ON)
            code, _ = self._run([tmp, "--set", "off"])
        self.assertEqual(code, 1)

    def test_invalid_set_value_exits_two(self) -> None:
        """--set maybe のような不正値は書き換えず 2。"""
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), PROFILE_OFF)
            code, _ = self._run([tmp, "--set", "maybe"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
