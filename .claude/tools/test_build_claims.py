"""build_claims.py のテスト。

主張台帳は **人が正しさを判断するための唯一の監査面** なので、
「集められること」より「 **弱まったことを見落とさないこと** 」を重く見る。
証明済み（⊢）だった主張が未証明（⊬）に戻る・消えるのは、
散文の差分では絶対に気づけない種類の後退なので、そこを固定する。

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

import build_claims

DESIGN = """\
# S03 CSV のフィルタ

## 主張（契約式）

| ID | 種別 | 主張 | assert | 状態 | 根拠 |
|---|---|---|---|---|---|
| P1 | 事前 | `pred` は全域関数 | `assert callable(pred)` | ⊢ | `test_pred_callable` |
| Q1 | 事後 | `∀r ∈ out. r ∈ in ∧ pred(r)` | `assert all(r in inp and pred(r) for r in out)` | ⊢ | `test_only_matching` |
| Q2 | 事後 | `∀r ∈ in. pred(r) → r ∈ out` | `assert all(r in out for r in inp if pred(r))` | ⊬ | 未（D02） |

**場合**: `in = ∅ ⊔ 全通過 ⊔ 一部通過 ⊔ 全落ち`

**反例**: Q2 が破れるなら —— `pred(r)` が真なのに `out` に無い `r` が 1 つ

## 判断の記録

- 採用: 契約を切らない
"""

NO_CLAIMS = """\
# S04 集計

## 判断の記録

- 採用: なにか
"""


def _repo(root: Path, files: dict[str, str]) -> None:
    (root / "docs" / "design").mkdir(parents=True)
    for name, text in files.items():
        (root / "docs" / "design" / name).write_text(text, encoding="utf-8")


class ParseTest(unittest.TestCase):
    """設計書 1 枚から主張を読み取る。"""

    def test_reads_every_row(self) -> None:
        claims = build_claims.parse_claims(DESIGN, "S03")
        self.assertEqual([c.cid for c in claims], ["P1", "Q1", "Q2"])

    def test_reads_proof_state(self) -> None:
        """⊢ と ⊬ を取り違えない（ここを誤ると台帳が嘘になる）。"""
        claims = {c.cid: c for c in build_claims.parse_claims(DESIGN, "S03")}
        self.assertTrue(claims["Q1"].proved)
        self.assertFalse(claims["Q2"].proved)

    def test_keeps_assert_form(self) -> None:
        """記号が読めない人のための assert 併記を落とさない。"""
        claims = {c.cid: c for c in build_claims.parse_claims(DESIGN, "S03")}
        self.assertIn("all(r in inp and pred(r) for r in out)", claims["Q1"].assertion)

    def test_reads_cases_and_counterexample(self) -> None:
        """場合分けと反例は台帳の要（攻撃の入口）なので拾う。"""
        self.assertIn("⊔", build_claims.parse_cases(DESIGN))
        self.assertIn("pred(r)", build_claims.parse_counterexample(DESIGN))

    def test_document_without_claims_is_empty_not_error(self) -> None:
        """主張節が無い設計書は、落ちずに 0 件として扱う。"""
        self.assertEqual(build_claims.parse_claims(NO_CLAIMS, "S04"), [])

    def test_stops_at_next_heading(self) -> None:
        """次の節の表を主張として吸い込まない。"""
        claims = build_claims.parse_claims(DESIGN, "S03")
        self.assertTrue(all(c.cid.startswith(("P", "Q", "I")) for c in claims))


class CollectTest(unittest.TestCase):
    """リポジトリ全体から集める。"""

    def test_collects_from_all_designs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root, {"S03-filter.md": DESIGN, "S04-sum.md": NO_CLAIMS})
            claims = build_claims.collect(root)
        self.assertEqual({c.slice_key for c in claims}, {"S03"})

    def test_slice_key_comes_from_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root, {"S03-filter.md": DESIGN})
            claims = build_claims.collect(root)
        self.assertTrue(all(c.slice_key == "S03" for c in claims))


class DiffTest(unittest.TestCase):
    """席を外した間に何が変わったか。"""

    def _claims(self, **states: bool) -> list[build_claims.Claim]:
        return [
            build_claims.Claim("S03", cid, "事後", f"式{cid}", f"assert {cid}", ok, "t")
            for cid, ok in states.items()
        ]

    def test_added_guarantee(self) -> None:
        before = self._claims(Q1=True)
        after = self._claims(Q1=True, Q2=True)
        found = build_claims.diff(before, after)
        self.assertEqual([c.cid for c in found["追加"]], ["Q2"])

    def test_weakened_guarantee_is_detected(self) -> None:
        """⊢ から ⊬ への後退。散文の差分では気づけない最重要ケース。"""
        before = self._claims(Q1=True)
        after = self._claims(Q1=False)
        found = build_claims.diff(before, after)
        self.assertEqual([c.cid for c in found["弱まった"]], ["Q1"])
        self.assertEqual(found["追加"], [])

    def test_removed_guarantee_is_detected(self) -> None:
        """主張ごと消えるのも後退（黙って消せないようにする）。"""
        found = build_claims.diff(self._claims(Q1=True), [])
        self.assertEqual([c.cid for c in found["消えた"]], ["Q1"])

    def test_still_unproved_is_listed(self) -> None:
        """ずっと ⊬ のまま放置されているものを毎回見せる。"""
        found = build_claims.diff(self._claims(Q1=False), self._claims(Q1=False))
        self.assertEqual([c.cid for c in found["未証明のまま"]], ["Q1"])
        self.assertEqual(found["追加"], [])

    def test_strengthened_is_an_addition(self) -> None:
        """⊬ から ⊢ に上がったものは「追加された保証」として出す。"""
        found = build_claims.diff(self._claims(Q1=False), self._claims(Q1=True))
        self.assertEqual([c.cid for c in found["追加"]], ["Q1"])


class MainTest(unittest.TestCase):
    """終了コードと出力。"""

    def _run(self, argv: list[str]) -> tuple[int, str]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = build_claims.main(argv)
        return code, buffer.getvalue()

    def test_ledger_lists_unproved_and_exits_one(self) -> None:
        """未証明が残っていれば 1（緑と混ぜない）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root, {"S03-filter.md": DESIGN})
            code, out = self._run([str(root)])
        self.assertEqual(code, 1)
        self.assertIn("Q2", out)
        self.assertIn("⊬", out)

    def test_all_proved_exits_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root, {"S03-filter.md": DESIGN.replace("| ⊬ | 未（D02） |", "| ⊢ | `t` |")})
            code, _ = self._run([str(root)])
        self.assertEqual(code, 0)

    def test_diff_without_snapshot_is_not_an_error(self) -> None:
        """初回（既読地点が無い）は落ちずに全件を「追加」として出す。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root, {"S03-filter.md": DESIGN})
            code, out = self._run([str(root), "--diff"])
        self.assertIn(code, (0, 1))
        self.assertIn("Q1", out)

    def test_mark_then_diff_is_clean(self) -> None:
        """--mark で既読にすると、次の --diff は差分なしになる。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root, {"S03-filter.md": DESIGN})
            self._run([str(root), "--mark"])
            code, out = self._run([str(root), "--diff"])
        self.assertEqual(code, 0)
        self.assertIn("差分なし", out)

    def test_mark_then_weaken_is_reported(self) -> None:
        """既読にした後で ⊢ が ⊬ に戻ったら、差分で必ず出る。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _repo(root, {"S03-filter.md": DESIGN})
            self._run([str(root), "--mark"])
            (root / "docs" / "design" / "S03-filter.md").write_text(
                DESIGN.replace("| ⊢ | `test_only_matching` |", "| ⊬ | 未 |"),
                encoding="utf-8",
            )
            code, out = self._run([str(root), "--diff"])
        self.assertEqual(code, 1)
        self.assertIn("弱まった", out)
        self.assertIn("Q1", out)

    def test_missing_design_dir_is_not_a_crash(self) -> None:
        """設計書がまだ 1 枚も無い段階でも落ちない。"""
        with tempfile.TemporaryDirectory() as tmp:
            code, _ = self._run([tmp])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
