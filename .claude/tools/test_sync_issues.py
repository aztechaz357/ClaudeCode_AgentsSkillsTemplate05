"""sync_issues.py のテスト。

このツールは **外部（GitHub / GitLab）へ書き込む差分を計算する** ので、
「差分を出せること」だけでなく次の 3 つを重点的に検証する:

    - 同期済みのときに余計な作成を出さない（重複起票は取り消しにくい）
    - `使用: off` のときに何も計算せず拒否する（誤送信の構造的な防止）
    - モードで呼ぶ CLI が変わる（`gitlab` のときに `gh` を呼ばない）

GitLab 側は **実物の glab を持たない環境で検証している** 。したがって
ここで固定できるのは「JSON の形の違いを吸収すること」「gh を呼ばないこと」
「引数の組み立て方」までで、 **フラグ名が glab に受理されるかは未検証** 。
誤っていれば glab が非 0 で落ち、ツールは NG を返す（黙って別の内容を
書き込むことはない）。

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
    """gh issue list --json の形（番号は number、ラベルは辞書）。"""
    return {
        "number": number,
        "title": title,
        "state": state,
        "labels": [{"name": name} for name in (labels or [])],
    }


def _gl_issue(
    iid: int, title: str, state: str = "opened", labels: list[str] | None = None
) -> dict:
    """glab issue list の形（番号は iid、状態は小文字、ラベルは文字列）。

    `id` は **インスタンス全体の通し番号** で iid とは別物なので、
    取り違えないことを固定するためにわざと違う値を入れる。
    """
    return {
        "id": iid + 1000,
        "iid": iid,
        "title": title,
        "state": state,
        "labels": list(labels or []),
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


class NormalizeTest(unittest.TestCase):
    """CLI ごとに違う JSON を 1 つの形に畳む（差分計算を共通に保つ土台）。"""

    def test_gitlab_iid_becomes_number(self) -> None:
        """番号は iid を採る（id はインスタンス通番で、別の Issue を指す）。"""
        found = sync_issues.normalize_issues([_gl_issue(7, "S02: x")])
        self.assertEqual(found[0]["number"], 7)

    def test_opened_counts_as_open(self) -> None:
        """GitLab の `opened` を OPEN に畳む（畳まないと全件が閉扱いになる）。"""
        found = sync_issues.normalize_issues([_gl_issue(7, "S02: x", state="opened")])
        self.assertEqual(found[0]["state"], "OPEN")

    def test_closed_stays_closed(self) -> None:
        """`closed` は CLOSED のまま。"""
        found = sync_issues.normalize_issues([_gl_issue(7, "x", state="closed")])
        self.assertEqual(found[0]["state"], "CLOSED")

    def test_github_shape_is_unchanged(self) -> None:
        """gh の形（number / OPEN / 辞書ラベル）も同じ結果になる。"""
        found = sync_issues.normalize_issues([_issue(7, "S02: x", labels=["slice"])])
        self.assertEqual(found[0]["number"], 7)
        self.assertEqual(found[0]["state"], "OPEN")
        self.assertEqual(found[0]["labels"], ["slice"])

    def test_wrapped_list_is_unwrapped(self) -> None:
        """配列を包んで返す形（`{"issues": [...]}`）も読む。"""
        found = sync_issues.normalize_issues({"issues": [_gl_issue(3, "x")]})
        self.assertEqual([item["number"] for item in found], [3])

    def test_items_without_a_number_are_dropped(self) -> None:
        """番号の無い要素は捨てる（推測で 0 番を作らない）。"""
        self.assertEqual(sync_issues.normalize_issues([{"title": "x"}]), [])


class GitlabPlanTest(unittest.TestCase):
    """差分の計算は GitHub と GitLab で同じ結果になる。"""

    def test_same_plan_for_both_shapes(self) -> None:
        """同じ内容なら、gh の形でも glab の形でも差分は出ない。"""
        gh_issues = [
            _issue(1, "S02: CSV のフィルタ", labels=["slice", "L1"]),
            _issue(2, "S03: 集計の出力", labels=["slice", "L0"]),
            _issue(3, "D01: 出力先をハードコード", labels=["debt"]),
        ]
        gl_issues = [
            _gl_issue(1, "S02: CSV のフィルタ", labels=["slice", "L1"]),
            _gl_issue(2, "S03: 集計の出力", labels=["slice", "L0"]),
            _gl_issue(3, "D01: 出力先をハードコード", labels=["debt"]),
        ]
        self.assertTrue(sync_issues.plan(BACKLOG, gh_issues).is_empty)
        self.assertTrue(sync_issues.plan(BACKLOG, gl_issues).is_empty)

    def test_closed_gitlab_issue_is_reopened(self) -> None:
        """`closed` の GitLab Issue を、まだ L1 なら再オープン対象にする。"""
        issues = [_gl_issue(1, "S02: CSV のフィルタ", "closed", ["slice", "L1"])]
        self.assertEqual([c.number for c in sync_issues.plan(BACKLOG, issues).reopen], [1])


class ManagedLabelTest(unittest.TestCase):
    """張り替えてよいラベルの範囲（外の情報を消さない・冪等にする）。"""

    def test_stale_maturity_label_is_removed(self) -> None:
        """L1 を足すだけでなく L0 を外す（外さないと毎回差分が出続ける）。"""
        issues = [_issue(1, "S02: CSV のフィルタ", labels=["slice", "L0"])]
        change = sync_issues.plan(BACKLOG, issues).update[0]
        self.assertEqual(change.remove, ["L0"])
        self.assertIn("L1", change.labels)

    def test_foreign_label_is_not_removed(self) -> None:
        """人が付けた `bug` は外さない（同期で外の情報を消さない）。"""
        issues = [_issue(1, "S02: CSV のフィルタ", labels=["slice", "L1", "bug"])]
        plan = sync_issues.plan(BACKLOG, issues)
        self.assertEqual(plan.update, [])

    def test_missing_label_is_added_without_removals(self) -> None:
        """足りないだけのときは外すものが空になる。"""
        issues = [_issue(1, "S02: CSV のフィルタ", labels=["slice"])]
        change = sync_issues.plan(BACKLOG, issues).update[0]
        self.assertEqual(change.remove, [])


class ForgeTest(unittest.TestCase):
    """CLI の呼び方の違い（ここ 1 か所だけがサービスを知る）。"""

    def _row(self, key: str = "S02") -> sync_issues.Row:
        return {row.key: row for row in sync_issues.parse_backlog(BACKLOG)}[key]

    def test_github_create_uses_gh_and_body(self) -> None:
        """GitHub は gh・--body・ラベルは反復。"""
        argv = sync_issues.GITHUB.create_command("owner/repo", self._row())
        self.assertEqual(argv[:2], ["gh", "issue"])
        self.assertIn("--body", argv)
        self.assertEqual(argv.count("--label"), 2)

    def test_gitlab_create_uses_glab_and_description(self) -> None:
        """GitLab は glab・--description・ラベルはカンマ区切り 1 引数。"""
        argv = sync_issues.GITLAB.create_command("group/project", self._row())
        self.assertEqual(argv[:2], ["glab", "issue"])
        self.assertIn("--description", argv)
        self.assertNotIn("--body", argv)
        self.assertIn("slice,L1", argv)

    def test_github_create_and_edit_use_different_label_flags(self) -> None:
        """gh は作成が --label、更新が --add-label（取り違えると引数エラー）。"""
        change = sync_issues.Change(1, "S02", "S02: x", ["slice", "L1"], "ラベル")
        self.assertNotIn(
            "--add-label", sync_issues.GITHUB.create_command("o/r", self._row())
        )
        self.assertNotIn("--label", sync_issues.GITHUB.edit_command("o/r", change))

    def test_gitlab_edit_verb_is_update(self) -> None:
        """既存 Issue を直す副コマンドは gh が edit、glab が update。"""
        change = sync_issues.Change(1, "S02", "S02: x", ["slice", "L1"], "ラベル", ["L0"])
        self.assertEqual(sync_issues.GITHUB.edit_command("o/r", change)[2], "edit")
        self.assertEqual(sync_issues.GITLAB.edit_command("g/p", change)[2], "update")

    def test_drop_label_flags_differ(self) -> None:
        """外すフラグは gh が --remove-label、glab が --unlabel。"""
        change = sync_issues.Change(1, "S02", "S02: x", ["slice", "L1"], "ラベル", ["L0"])
        self.assertIn("--remove-label", sync_issues.GITHUB.edit_command("o/r", change))
        self.assertIn("--unlabel", sync_issues.GITLAB.edit_command("g/p", change))

    def test_no_labels_means_no_flag(self) -> None:
        """外すものが無いときにカンマ区切りの空文字を渡さない。"""
        change = sync_issues.Change(1, "S02", "S02: x", ["slice"], "タイトル", [])
        self.assertNotIn("--unlabel", sync_issues.GITLAB.edit_command("g/p", change))

    def test_self_hosted_host_goes_into_the_environment(self) -> None:
        """自前ホストは GITLAB_HOST で渡す（コマンド行には出さない）。"""
        env = sync_issues.GITLAB.env("gitlab.example.com")
        self.assertEqual(env["GITLAB_HOST"], "gitlab.example.com")

    def test_default_host_means_no_custom_env(self) -> None:
        """ホスト未設定なら環境をいじらない（glab の設定をそのまま使う）。"""
        self.assertIsNone(sync_issues.GITLAB.env(None))

    def test_github_ignores_host(self) -> None:
        """GitHub にはホストの概念を持ち込まない。"""
        self.assertIsNone(sync_issues.GITHUB.env("gitlab.example.com"))


class BodyTest(unittest.TestCase):
    """Issue 本文（雛形の正はこのツールにだけ置く）。"""

    def test_slice_body_has_eight_deliverables(self) -> None:
        """スライスの本文に 8 点セットのチェックリストが入る。"""
        row = {row.key: row for row in sync_issues.parse_backlog(BACKLOG)}["S02"]
        body = sync_issues.build_body(row)
        for item in ("要求仕様書", "設計書", "テスト仕様書", "単体テスト", "実装",
                     "統合テスト", "テスト結果", "マニュアル"):
            self.assertIn(item, body)

    def test_slice_body_orders_test_spec_before_unit_test(self) -> None:
        """テスト仕様書は単体テストより前に並ぶ（書く順序がそのまま出る）。"""
        row = {row.key: row for row in sync_issues.parse_backlog(BACKLOG)}["S02"]
        body = sync_issues.build_body(row)
        self.assertLess(body.index("テスト仕様書"), body.index("単体テスト"))

    def test_body_states_backlog_is_the_source(self) -> None:
        """本文に「正はバックログ」と明記する（二重管理の防止）。"""
        row = {row.key: row for row in sync_issues.parse_backlog(BACKLOG)}["S02"]
        self.assertIn("docs/backlog.md", sync_issues.build_body(row))


class MainTest(unittest.TestCase):
    """終了コード（0 = 差分なし / 1 = 差分あり / 2 = エラー・off）。"""

    def _prepare(
        self, tmp: str, mode: str, issues: list[dict], host: str = ""
    ) -> list[str]:
        root = Path(tmp)
        (root / "docs").mkdir()
        (root / "docs" / "backlog.md").write_text(BACKLOG, encoding="utf-8")
        host_line = f"- ホスト: {host}\n" if host else ""
        (root / "CLAUDE.md").write_text(
            "# CLAUDE.md\n\n### Issue 追跡（GitHub Issues）\n\n"
            f"- 使用: {mode}\n- リポジトリ: owner/repo\n{host_line}",
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
        self.assertEqual(calls[0][0][:4], ["gh", "issue", "create", "--repo"])

    def test_apply_failure_exits_one(self) -> None:
        """gh が失敗したら 1 を返す（成功と誤認しない）。"""
        self._record(exit_code=1, output="could not create issue")
        with tempfile.TemporaryDirectory() as tmp:
            argv = self._prepare(tmp, "on", [])
            code, out = self._run(argv + ["--apply"])
        self.assertEqual(code, 1)
        self.assertIn("NG", out)

    def test_gitlab_apply_calls_glab_not_gh(self) -> None:
        """`使用: gitlab` で gh を 1 回も呼ばない（別のサービスへの誤送信）。"""
        calls = self._record()
        with tempfile.TemporaryDirectory() as tmp:
            argv = self._prepare(tmp, "gitlab", [])
            code, _ = self._run(argv + ["--apply"])
        self.assertEqual(code, 0)
        self.assertEqual({call[0][0] for call in calls}, {"glab"})

    def test_gitlab_dry_run_reports_the_service(self) -> None:
        """未送信の報告に、どのサービス宛てかを書く（取り違えに気づけるように）。"""
        with tempfile.TemporaryDirectory() as tmp:
            argv = self._prepare(tmp, "gitlab", [])
            code, out = self._run(argv)
        self.assertEqual(code, 1)
        self.assertIn("GitLab", out)

    def test_self_hosted_host_reaches_the_runner(self) -> None:
        """プロファイルの `ホスト:` が実行時の環境に入る。"""
        calls = self._record()
        with tempfile.TemporaryDirectory() as tmp:
            argv = self._prepare(tmp, "gitlab", [], host="gitlab.example.com")
            self._run(argv + ["--apply"])
        self.assertEqual(calls[0][1]["GITLAB_HOST"], "gitlab.example.com")

    def test_print_commands_does_not_run_anything(self) -> None:
        """--print-commands は見せるだけ（実行しない）。"""
        calls = self._record()
        with tempfile.TemporaryDirectory() as tmp:
            argv = self._prepare(tmp, "gitlab", [])
            code, out = self._run(argv + ["--print-commands"])
        self.assertEqual(code, 1)
        self.assertEqual(calls, [])
        self.assertIn("$ glab issue create", out)

    def _record(
        self, exit_code: int = 0, output: str = ""
    ) -> list[tuple[list[str], dict | None]]:
        """CLI の実行関数を記録用に差し替え、テスト終了時に戻す。"""
        calls: list[tuple[list[str], dict | None]] = []

        def _fake(argv: list[str], env: dict | None = None) -> tuple[int, str]:
            calls.append((argv, env))
            return exit_code, output or "https://github.com/owner/repo/issues/1"

        original = sync_issues.RUNNER
        sync_issues.RUNNER = _fake
        self.addCleanup(lambda: setattr(sync_issues, "RUNNER", original))
        return calls


if __name__ == "__main__":
    unittest.main()
