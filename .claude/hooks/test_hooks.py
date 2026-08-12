"""フック（`.claude/hooks/*.ps1`）のテスト。

フックは「動かなくても静かに何も起きない」ため、壊れていても気づけない。
実際にこのテンプレートでは PreToolUse / PostToolUse のフックが約 99% の
実行で落ちており、保護（凍結パス・破壊的コマンドの拒否）が無効なまま
1 編集あたり約 1 秒を払っていた（原因: stdin をコンソールの入力コード
ページで復号していたため、日本語と Windows パスが混ざると JSON が壊れる）。

そのため、このテストは 2 種類を必ず両方持つ:

1. **検出できること** —— 拒否すべき入力で deny / findings が出る
2. **壊れないこと** —— 日本語とバックスラッシュを含む実際の payload で
   標準エラーが空であること（フック自身の失敗を検出する）

実行（前置コマンドはプロファイルの「.claude/tools/ の Python ツール実行」）:
    <ツール実行コマンド> -m unittest discover -s .claude/hooks -p "test_*.py" -v
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent
REPO = HOOKS.parent.parent

# 日本語の直後にバックスラッシュのエスケープが続く形。cp932 として復号すると
# 直前の 3 バイト（UTF-8 の 1 文字）と `\` が 1 文字に食われ、残った `\U` が
# 不正なエスケープシーケンスになる。実際の編集 payload では
# 「日本語の本文 + Windows のパス」で日常的に起きる組み合わせ。
TRAP = "あ\\Users"


def run_hook(script: str, payload: dict, *args: str) -> tuple[int, str, str]:
    """フックを実際のプロセスとして起動し、(終了コード, stdout, stderr) を返す。

    payload は Claude Code と同じく UTF-8 のバイト列で標準入力へ渡す。
    """
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(HOOKS / script),
            *args,
        ],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(REPO),
    )
    return (
        proc.returncode,
        proc.stdout.decode("utf-8", errors="replace"),
        proc.stderr.decode("utf-8", errors="replace"),
    )


def make_repo(tmp: Path, protected: str = "", denied: str = "") -> Path:
    """protected_paths / denied_commands を持つ最小のリポジトリを作る。"""
    hooks = tmp / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "protected_paths.txt").write_text(protected, encoding="utf-8")
    (hooks / "denied_commands.txt").write_text(denied, encoding="utf-8")
    return tmp


class TestPreToolGuard(unittest.TestCase):
    """PreToolUse: 保護パスと破壊的コマンドを拒否する。"""

    def test_denies_destructive_command(self):
        """破壊的コマンドを拒否する。"""
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d), denied="git reset --hard*")
            code, out, err = run_hook(
                "pre-tool-guard.ps1",
                {
                    "cwd": str(root),
                    "tool_name": "Bash",
                    "tool_input": {"command": "git reset --hard HEAD~1"},
                },
            )
        self.assertEqual(err, "")
        self.assertEqual(code, 0)
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")

    def test_denies_protected_path_edit(self):
        """保護パスの編集を拒否する。"""
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d), protected="docs/Note/")
            code, out, err = run_hook(
                "pre-tool-guard.ps1",
                {
                    "cwd": str(root),
                    "tool_name": "Edit",
                    "tool_input": {"file_path": str(root / "docs" / "Note" / "a.md")},
                },
            )
        self.assertEqual(err, "")
        self.assertEqual(code, 0)
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")

    def test_allows_ordinary_edit(self):
        """保護対象でない編集は素通しする。"""
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d), protected="docs/Note/")
            code, out, err = run_hook(
                "pre-tool-guard.ps1",
                {
                    "cwd": str(root),
                    "tool_name": "Edit",
                    "tool_input": {"file_path": str(root / "src" / "main.py")},
                },
            )
        self.assertEqual(err, "")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_survives_japanese_and_backslashes(self):
        """日本語の本文と Windows パスが混ざった payload でも落ちないこと。"""
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d), protected="docs/Note/")
            code, out, err = run_hook(
                "pre-tool-guard.ps1",
                {
                    "cwd": str(root),
                    "tool_name": "Edit",
                    "tool_input": {
                        "old_string": TRAP,
                        "new_string": "日本語の本文\\Users\\msay5",
                        "file_path": str(root / "src" / "main.py"),
                    },
                },
            )
        self.assertEqual(err, "")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_denies_destructive_command_with_japanese(self):
        """壊れた JSON で素通しになると、保護が無いのと同じになる。"""
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d), denied="rm -rf *")
            code, out, err = run_hook(
                "pre-tool-guard.ps1",
                {
                    "cwd": str(root),
                    "tool_name": "Bash",
                    "tool_input": {"command": TRAP + ' && rm -rf "作業用"'},
                },
            )
        self.assertEqual(err, "")
        self.assertEqual(code, 0)
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")

    def test_deny_reason_keeps_japanese_path(self):
        """stdout が UTF-8 でなければ、理由が化けて Claude に読めない。"""
        with tempfile.TemporaryDirectory() as d:
            root = make_repo(Path(d), protected="docs/資料/")
            code, out, err = run_hook(
                "pre-tool-guard.ps1",
                {
                    "cwd": str(root),
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(root / "docs" / "資料" / "凍結.md")},
                },
            )
        self.assertEqual(err, "")
        self.assertEqual(code, 0)
        reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("docs/資料/凍結.md", reason)

    def test_survives_missing_pattern_files(self):
        """設定ファイルが無くても落ちない。"""
        with tempfile.TemporaryDirectory() as d:
            code, out, err = run_hook(
                "pre-tool-guard.ps1",
                {
                    "cwd": d,
                    "tool_name": "Bash",
                    "tool_input": {"command": "git status"},
                },
            )
        self.assertEqual(err, "")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")


class TestPostEditMarkdown(unittest.TestCase):
    """PostToolUse: 編集された Markdown に番号検証を掛ける。"""

    def test_reports_numbering_findings(self):
        """番号の誤りを検出する。"""
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "sample.md"
            target.write_text("# 見出し\n\n図 1 を参照する。\n", encoding="utf-8")
            code, out, err = run_hook(
                "post-edit-markdown.ps1",
                {
                    "cwd": str(REPO),
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(target)},
                },
            )
        self.assertEqual(err, "")
        self.assertEqual(code, 0)
        context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("DANGL", context)

    def test_silent_on_clean_markdown(self):
        """正しい Markdown では何も出力しない。"""
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "sample.md"
            target.write_text("# 見出し\n\n本文だけの文書。\n", encoding="utf-8")
            code, out, err = run_hook(
                "post-edit-markdown.ps1",
                {
                    "cwd": str(REPO),
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(target)},
                },
            )
        self.assertEqual(err, "")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_survives_japanese_and_backslashes(self):
        """日本語と Windows パスが混ざった payload でも壊れない。"""
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "sample.md"
            target.write_text("# 見出し\n\n本文だけの文書。\n", encoding="utf-8")
            code, out, err = run_hook(
                "post-edit-markdown.ps1",
                {
                    "cwd": str(REPO),
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(target), "content": TRAP},
                    "tool_response": {"filePath": str(target)},
                },
            )
        self.assertEqual(err, "")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_skips_non_markdown(self):
        """Markdown 以外のファイルには何もしない。"""
        code, out, err = run_hook(
            "post-edit-markdown.ps1",
            {
                "cwd": str(REPO),
                "tool_name": "Edit",
                "tool_input": {"file_path": str(REPO / "src" / "main.py"), "old_string": TRAP},
            },
        )
        self.assertEqual(err, "")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")


class TestPostEditPython(unittest.TestCase):
    """PostToolUse: 編集された Python に識別子の検査を掛ける。"""

    def test_reports_japanese_function_name(self):
        """日本語の関数名を Claude に差し戻す。"""
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "sample.py"
            target.write_text("def 集計する(rows):\n    return rows\n", encoding="utf-8")
            code, out, err = run_hook(
                "post-edit-python.ps1",
                {
                    "cwd": str(REPO),
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(target)},
                },
            )
        self.assertEqual(err, "")
        self.assertEqual(code, 0)
        context = json.loads(out)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("集計する", context)

    def test_silent_on_ascii_names(self):
        """ASCII の関数名だけなら何も出力しない。"""
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "sample.py"
            target.write_text(
                'def count(rows):\n    """行を数える。"""\n    return len(rows)\n',
                encoding="utf-8",
            )
            code, out, err = run_hook(
                "post-edit-python.ps1",
                {
                    "cwd": str(REPO),
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(target)},
                },
            )
        self.assertEqual(err, "")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_skips_non_python(self):
        """Python 以外のファイルには何もしない。"""
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "sample.md"
            target.write_text("# 見出し\n", encoding="utf-8")
            code, out, err = run_hook(
                "post-edit-python.ps1",
                {
                    "cwd": str(REPO),
                    "tool_name": "Write",
                    "tool_input": {"file_path": str(target), "content": TRAP},
                },
            )
        self.assertEqual(err, "")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")


class TestOtherHooks(unittest.TestCase):
    """stdin を読む残りのフックも同じ payload で壊れないこと。"""

    def test_notify_survives_japanese_payload(self):
        """notify.ps1 が日本語の通知でも壊れない。"""
        code, _out, err = run_hook(
            "notify.ps1",
            {"hook_event_name": "Notification", "message": "確認が必要です" + TRAP},
            "-Duration",
            "1",
        )
        self.assertEqual(err, "")
        self.assertEqual(code, 0)

    def test_post_edit_lint_skips_non_target(self):
        """post-edit-lint.ps1 が対象外の拡張子では何もしない。"""
        code, out, err = run_hook(
            "post-edit-lint.ps1",
            {
                "cwd": str(REPO),
                "tool_name": "Edit",
                "tool_input": {"file_path": str(REPO / "docs" / "a.md"), "old_string": TRAP},
            },
            "-Command",
            "echo",
        )
        self.assertEqual(err, "")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_stop_uncommitted_survives_japanese_payload(self):
        """stop-uncommitted.ps1 が日本語の payload でも壊れない。"""
        code, _out, err = run_hook(
            "stop-uncommitted.ps1",
            {"hook_event_name": "Stop", "cwd": str(REPO), "note": TRAP},
        )
        self.assertEqual(err, "")
        self.assertEqual(code, 0)

    def test_session_start_context_survives_japanese_payload(self):
        """session-start-context.ps1 が日本語の payload でも壊れない。"""
        code, _out, err = run_hook(
            "session-start-context.ps1",
            {"hook_event_name": "SessionStart", "cwd": str(REPO), "note": TRAP},
        )
        self.assertEqual(err, "")
        self.assertEqual(code, 0)


class TestSessionStartIssueMode(unittest.TestCase):
    """Issue 追跡が on のときだけ文脈へ注入すること。

    モードは全エージェントの `gh` の扱いを変えるので、on を見落とすのも
    off を on と報告するのも事故になる。両方向を検証する。
    """

    PROFILE = (
        "# CLAUDE.md\n\n### Issue "
        + "追跡"
        + "（GitHub Issues）\n\n- 使用: {mode}\n- リポジトリ: owner/repo\n"
    )

    def _run_in(self, mode: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text(
                self.PROFILE.format(mode=mode), encoding="utf-8"
            )
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-File",
                    str(HOOKS / "session-start-context.ps1"),
                ],
                input=json.dumps({"hook_event_name": "SessionStart"}).encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(root),
            )
        self.assertEqual(proc.stderr.decode("utf-8", errors="replace"), "")
        self.assertEqual(proc.returncode, 0)
        return proc.stdout.decode("utf-8", errors="replace")

    def test_reports_when_on(self):
        """`使用: on` のとき ISSUE TRACKING IS ON を注入する。"""
        self.assertIn("ISSUE TRACKING IS ON", self._run_in("on"))

    def test_silent_when_off(self):
        """`使用: off` のときは何も言わない（既定を邪魔しない）。"""
        self.assertNotIn("ISSUE TRACKING", self._run_in("off"))


class TestSessionStartUnread(unittest.TestCase):
    """既読地点からの未読コミット数を知らせること。

    生成が読解より速いので「気づいたら追いつけない」が起きる。
    マーカーがあるときだけ数え、無いときは黙る（既定を邪魔しない）。
    """

    def _run_in(self, marker: str | None) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for args in (
                ["init", "-q"],
                ["config", "user.email", "t@example.com"],
                ["config", "user.name", "t"],
            ):
                subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
            (root / "a.txt").write_text("1", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", "最初"], cwd=root, check=True, capture_output=True
            )
            first = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            (root / "a.txt").write_text("2", encoding="utf-8")
            subprocess.run(["git", "commit", "-qam", "次"], cwd=root, check=True, capture_output=True)

            if marker is not None:
                steering = root / ".steering"
                steering.mkdir()
                (steering / "last-reviewed").write_text(
                    (first if marker == "first" else marker) + "\n", encoding="utf-8"
                )

            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-File",
                    str(HOOKS / "session-start-context.ps1"),
                ],
                input=json.dumps({"hook_event_name": "SessionStart"}).encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(root),
            )
        self.assertEqual(proc.stderr.decode("utf-8", errors="replace"), "")
        self.assertEqual(proc.returncode, 0)
        return proc.stdout.decode("utf-8", errors="replace")

    def test_reports_unread_count(self):
        """1 コミット前を既読地点にすると UNREAD: 1 が出る。"""
        self.assertIn("UNREAD: 1 commits", self._run_in("first"))

    def test_silent_without_marker(self):
        """マーカーが無ければ黙る（まだ一度も /catchup していない）。"""
        self.assertNotIn("UNREAD", self._run_in(None))


if __name__ == "__main__":
    unittest.main()
