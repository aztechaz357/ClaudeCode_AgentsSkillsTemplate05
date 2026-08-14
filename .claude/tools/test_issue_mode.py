"""issue_mode.py のテスト。

チケット追跡のモードは **全エージェントの振る舞いを変える設定** なので、
「読めること」だけでなく「読めないときに github と誤判定しないこと」を検証する
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

### チケット追跡

- 使用: off
- リポジトリ: なし
- ラベル: slice / debt / L1 / L2 / L3

### ログ / Git

- 既定ブランチ: main
"""

PROFILE_GITHUB = PROFILE_OFF.replace("使用: off", "使用: github").replace(
    "リポジトリ: なし", "リポジトリ: owner/repo"
)

PROFILE_LOCAL = PROFILE_OFF.replace("使用: off", "使用: local")

PROFILE_GITLAB = PROFILE_OFF.replace("使用: off", "使用: gitlab").replace(
    "リポジトリ: なし", "リポジトリ: group/project\n- ホスト: なし"
)
PROFILE_GITLAB_SELF = PROFILE_GITLAB.replace(
    "ホスト: なし", "ホスト: gitlab.example.com"
)

# `リポジトリ:` の行がまだ無いプロファイル（節を手で書き始めた直後の形）
PROFILE_NO_REPO = PROFILE_OFF.replace("- リポジトリ: なし\n", "")

# この節が 2 値（on / off）だった頃のプロファイル。読めなくなると既存の
# リポジトリが一斉に「判定不能」になるので、別名として読めることを固定する
PROFILE_LEGACY_ON = PROFILE_OFF.replace("使用: off", "使用: on").replace(
    "リポジトリ: なし", "リポジトリ: owner/repo"
)
PROFILE_LEGACY_HEADING = PROFILE_GITHUB.replace(
    "### チケット追跡", "### Issue 追跡（GitHub Issues）"
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

    def test_reads_github_with_repo(self) -> None:
        """`使用: github` とリポジトリ名を読み取る。"""
        setting = issue_mode.read_mode(PROFILE_GITHUB)
        self.assertEqual(setting.mode, "github")
        self.assertEqual(setting.repo, "owner/repo")

    def test_reads_local(self) -> None:
        """`使用: local` を読み取る（リポジトリは不要）。"""
        setting = issue_mode.read_mode(PROFILE_LOCAL)
        self.assertEqual(setting.mode, "local")
        self.assertIsNone(setting.repo)

    def test_reads_gitlab(self) -> None:
        """`使用: gitlab` を github と取り違えない（別のサービスへ起票する事故）。"""
        setting = issue_mode.read_mode(PROFILE_GITLAB)
        self.assertEqual(setting.mode, "gitlab")
        self.assertEqual(setting.repo, "group/project")

    def test_reads_self_hosted_gitlab_host(self) -> None:
        """自前ホストの GitLab のホスト名を読む。"""
        self.assertEqual(
            issue_mode.read_mode(PROFILE_GITLAB_SELF).host, "gitlab.example.com"
        )

    def test_default_gitlab_host_is_none(self) -> None:
        """`ホスト: なし` は未設定（gitlab.com）として読む。"""
        self.assertIsNone(issue_mode.read_mode(PROFILE_GITLAB).host)

    def test_legacy_on_reads_as_github(self) -> None:
        """旧設定の `使用: on` は github の別名として読む。"""
        self.assertEqual(issue_mode.read_mode(PROFILE_LEGACY_ON).mode, "github")

    def test_legacy_heading_is_found(self) -> None:
        """旧見出し「Issue 追跡（GitHub Issues）」の節も読める。"""
        self.assertEqual(issue_mode.read_mode(PROFILE_LEGACY_HEADING).mode, "github")

    def test_missing_section_is_unknown(self) -> None:
        """チケット追跡の節が無ければ判定不能（github と決めつけない）。"""
        setting = issue_mode.read_mode(PROFILE_NO_SECTION)
        self.assertIsNone(setting.mode)

    def test_invalid_value_is_unknown(self) -> None:
        """`使用: たぶん` を github 扱いしない（誤って外部送信するのを防ぐ）。"""
        setting = issue_mode.read_mode(PROFILE_OFF.replace("使用: off", "使用: たぶん"))
        self.assertIsNone(setting.mode)

    def test_placeholder_repo_is_unset(self) -> None:
        """雛形のままの `{例: owner/repo}` は未設定として扱う。"""
        text = PROFILE_GITHUB.replace(
            "リポジトリ: owner/repo", "リポジトリ: {例: owner/repo}"
        )
        self.assertIsNone(issue_mode.read_mode(text).repo)

    def test_ignores_lines_outside_section(self) -> None:
        """別の節に `- 使用: github` があってもチケット追跡の設定にしない。"""
        text = PROFILE_OFF.replace("### ログ / Git", "### ログ / Git\n\n- 使用: github\n")
        self.assertEqual(issue_mode.read_mode(text).mode, "off")


class SetModeTest(unittest.TestCase):
    """設定の書き換え（`使用:` の行だけを触る）。"""

    def test_turns_github_on(self) -> None:
        """off から github へ切り替え、リポジトリも書き込む。"""
        changed = issue_mode.set_mode(PROFILE_OFF, "github", repo="a/b")
        setting = issue_mode.read_mode(changed)
        self.assertEqual(setting.mode, "github")
        self.assertEqual(setting.repo, "a/b")

    def test_turns_local_on(self) -> None:
        """local に切り替えられる。"""
        changed = issue_mode.set_mode(PROFILE_OFF, "local")
        self.assertEqual(issue_mode.read_mode(changed).mode, "local")

    def test_turns_gitlab_on(self) -> None:
        """gitlab に切り替え、リポジトリを書き込む。"""
        changed = issue_mode.set_mode(PROFILE_OFF, "gitlab", repo="group/project")
        setting = issue_mode.read_mode(changed)
        self.assertEqual(setting.mode, "gitlab")
        self.assertEqual(setting.repo, "group/project")

    def test_gitlab_writes_host_line(self) -> None:
        """ホスト行が無いプロファイルでも、gitlab にすると足される。"""
        changed = issue_mode.set_mode(
            PROFILE_OFF, "gitlab", repo="g/p", host="gitlab.example.com"
        )
        self.assertIn("- ホスト: gitlab.example.com", changed)
        self.assertEqual(issue_mode.read_mode(changed).host, "gitlab.example.com")

    def test_gitlab_host_line_follows_repo(self) -> None:
        """足す行の順序は リポジトリ → ホスト（読む人が同じ並びを期待する）。"""
        changed = issue_mode.set_mode(
            PROFILE_NO_REPO, "gitlab", repo="g/p", host="gitlab.example.com"
        )
        lines = [line for line in changed.splitlines() if line.startswith("- ")]
        self.assertEqual(
            lines[:3],
            ["- 使用: gitlab", "- リポジトリ: g/p", "- ホスト: gitlab.example.com"],
        )

    def test_leaving_gitlab_clears_host(self) -> None:
        """github へ移すとホストは「なし」に戻る（使われない値を残さない）。"""
        changed = issue_mode.set_mode(PROFILE_GITLAB_SELF, "github", repo="owner/repo")
        self.assertIsNone(issue_mode.read_mode(changed).host)
        self.assertIn("- ホスト: なし", changed)

    def test_gitlab_keeps_host_when_not_given(self) -> None:
        """--host を渡さない切り替えで、既に書いてある自前ホストを消さない。"""
        changed = issue_mode.set_mode(PROFILE_GITLAB_SELF, "gitlab", repo="g/p")
        self.assertEqual(issue_mode.read_mode(changed).host, "gitlab.example.com")

    def test_gitlab_is_idempotent(self) -> None:
        """同じ値で 2 回書き換えても差分が出ない（ホスト行が増え続けない）。"""
        once = issue_mode.set_mode(
            PROFILE_OFF, "gitlab", repo="g/p", host="gitlab.example.com"
        )
        twice = issue_mode.set_mode(
            once, "gitlab", repo="g/p", host="gitlab.example.com"
        )
        self.assertEqual(once, twice)

    def test_legacy_on_normalizes_to_github(self) -> None:
        """`on` で書き換えても、ファイルには正式名 `github` が入る。"""
        changed = issue_mode.set_mode(PROFILE_OFF, "on", repo="a/b")
        self.assertIn("- 使用: github", changed)
        self.assertNotIn("- 使用: on", changed)

    def test_keeps_other_lines(self) -> None:
        """プロファイルの他の行を壊さない。"""
        changed = issue_mode.set_mode(PROFILE_OFF, "github")
        self.assertIn("| テスト | pytest |", changed)
        self.assertIn("- 既定ブランチ: main", changed)
        self.assertIn("- ラベル: slice / debt / L1 / L2 / L3", changed)

    def test_is_idempotent(self) -> None:
        """同じ値で 2 回書き換えても差分が出ない。"""
        once = issue_mode.set_mode(PROFILE_GITHUB, "github", repo="owner/repo")
        twice = issue_mode.set_mode(once, "github", repo="owner/repo")
        self.assertEqual(once, twice)

    def test_turning_off_clears_repo(self) -> None:
        """off にするとリポジトリは「なし」に戻る。"""
        changed = issue_mode.set_mode(PROFILE_GITHUB, "off")
        setting = issue_mode.read_mode(changed)
        self.assertEqual(setting.mode, "off")
        self.assertIsNone(setting.repo)

    def test_local_clears_repo(self) -> None:
        """local もリモートを使わないので、リポジトリ名を残さない。"""
        changed = issue_mode.set_mode(PROFILE_GITHUB, "local")
        self.assertIsNone(issue_mode.read_mode(changed).repo)

    def test_local_does_not_add_a_host_line(self) -> None:
        """gitlab 以外ではホスト行を作らない（意味の無い行を増やさない）。"""
        self.assertNotIn("ホスト", issue_mode.set_mode(PROFILE_OFF, "local"))

    def test_missing_section_raises(self) -> None:
        """節が無いプロファイルは書き換えず例外にする。"""
        with self.assertRaises(issue_mode.ProfileError):
            issue_mode.set_mode(PROFILE_NO_SECTION, "github")


class MainTest(unittest.TestCase):
    """終了コード（0 = github / 1 = off / 2 = 判定不能 / 3 = local / 4 = gitlab）。"""

    def _run(self, argv: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = issue_mode.main(argv)
        return code, buffer.getvalue()

    def test_github_exits_zero(self) -> None:
        """github のとき終了コード 0 とリポジトリ名を出す。"""
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), PROFILE_GITHUB)
            code, out = self._run([tmp])
        self.assertEqual(code, 0)
        self.assertIn("github", out)
        self.assertIn("owner/repo", out)

    def test_off_exits_one(self) -> None:
        """off のとき終了コード 1。"""
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), PROFILE_OFF)
            code, out = self._run([tmp])
        self.assertEqual(code, 1)
        self.assertIn("off", out)

    def test_local_exits_three(self) -> None:
        """local のとき終了コード 3（off の 1 と混ざらない）。"""
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), PROFILE_LOCAL)
            code, out = self._run([tmp])
        self.assertEqual(code, 3)
        self.assertIn("local", out)

    def test_gitlab_exits_four(self) -> None:
        """gitlab のとき終了コード 4（github の 0 と混ざらない）。"""
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), PROFILE_GITLAB)
            code, out = self._run([tmp])
        self.assertEqual(code, 4)
        self.assertIn("gitlab", out)
        self.assertIn("group/project", out)

    def test_gitlab_reports_default_host(self) -> None:
        """ホスト未設定なら gitlab.com と明示する（どこへ出すのかを隠さない）。"""
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), PROFILE_GITLAB)
            _, out = self._run([tmp])
        self.assertIn("ホスト: gitlab.com", out)

    def test_set_gitlab_writes_repo_and_host(self) -> None:
        """--set gitlab がリポジトリとホストを書き込み、4 を返す。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(Path(tmp), PROFILE_OFF)
            code, _ = self._run(
                [tmp, "--set", "gitlab", "--repo", "g/p", "--host", "gl.example.com"]
            )
            self.assertEqual(code, 4)
            setting = issue_mode.read_mode(path.read_text(encoding="utf-8"))
        self.assertEqual(setting.repo, "g/p")
        self.assertEqual(setting.host, "gl.example.com")

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
        """--set github がファイルを書き換える。"""
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(Path(tmp), PROFILE_OFF)
            code, _ = self._run([tmp, "--set", "github", "--repo", "a/b"])
            self.assertEqual(code, 0)
            text = path.read_text(encoding="utf-8")
        self.assertEqual(issue_mode.read_mode(text).mode, "github")
        self.assertEqual(issue_mode.read_mode(text).repo, "a/b")

    def test_set_local_exits_three(self) -> None:
        """書き換え後のモードを終了コードで返す（読み取りと同じ意味にする）。"""
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), PROFILE_GITHUB)
            code, _ = self._run([tmp, "--set", "local"])
        self.assertEqual(code, 3)

    def test_set_off_exits_one(self) -> None:
        """書き換え後のモードを終了コードで返す（読み取りと同じ意味にする）。"""
        with tempfile.TemporaryDirectory() as tmp:
            _write(Path(tmp), PROFILE_GITHUB)
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
