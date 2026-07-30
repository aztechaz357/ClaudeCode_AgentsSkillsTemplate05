"""build_usdm.py のテスト。

USDM の記法（`.claude/skills/usdm/SKILL.md`）が正。このテストは
「記法どおりの文書をパースできること」と「記法違反を検出できること」の
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

import build_usdm  # noqa: E402

VALID = """\
# S02. CSV のフィルタ

**成熟度: `L1 動く`** ｜ 依存: S01

## 要求

### 【REQ2】列を指定して絞り込みたい

- **理由**: 実データが 5 万行あり、全件出ると目的の行を目で探すことになる
- **範囲**: 完全一致のみ。部分一致・正規表現は対象外

**仕様**:

- [ ] `<2-1>` `--col NAME=値` を渡すと、その列が完全一致する行だけを数える
- [x] `<2-2>` 一致行が 0 件なら `0 行` と出す
"""

WITH_CHILD = """\
# S02. CSV のフィルタ

**成熟度: `L2 固い`**

## 要求

### 【REQ2】列を指定して絞り込みたい

- **理由**: 全件出ると目的の行を目で探すことになる

**仕様**:

- [ ] `<2-1>` 一致する行だけを数える

### 【REQ2.1】複数列を AND で指定したい

- **理由**: 1 列では絞り切れないデータがある

**仕様**:

- [ ] `<2.1-1>` `--col` を 2 回渡すと両方に一致する行だけを数える
"""


def _write(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


class ParseTest(unittest.TestCase):
    """記法どおりの文書を構造として取り出せることの検証。"""

    def test_parses_requirement_reason_scope_and_specs(self):
        """テスト対象: parse_document
        入力: 要求 1 個・理由・範囲・仕様 2 条（1 条は [x]）の S02 文書
        期待値: 要求 1 件が取れ、理由・範囲・成熟度・仕様の検証状態が読める
        理由: これが USDM 記法の最小単位であり、他の全機能の土台のため
        """
        doc = build_usdm.parse_document(VALID, slice_id="S02")

        self.assertEqual(doc.violations, [])
        self.assertEqual(doc.maturity, "L1 動く")
        self.assertEqual(len(doc.requirements), 1)

        req = doc.requirements[0]
        self.assertEqual(req.number, "2")
        self.assertEqual(req.title, "列を指定して絞り込みたい")
        self.assertIn("5 万行", req.reason)
        self.assertIn("完全一致のみ", req.scope)
        self.assertEqual([s.number for s in req.specs], ["2-1", "2-2"])
        self.assertEqual([s.verified for s in req.specs], [False, True])

    def test_title_drops_the_leading_slice_number(self):
        """テスト対象: parse_document
        入力: 見出しが `# S02. CSV のフィルタ` の文書
        期待値: title が「CSV のフィルタ」になる（S02. を含まない）
        理由: 表示側がスライス番号を前置するため、含めると
              「S02. S02. CSV のフィルタ」と重複する（実物で発生した不具合）
        """
        doc = build_usdm.parse_document(VALID, slice_id="S02")
        self.assertEqual(doc.title, "CSV のフィルタ")

    def test_builds_parent_child_from_dotted_number(self):
        """テスト対象: parse_document + build_tree
        入力: REQ2 と REQ2.1 を持つ文書（どちらも見出しレベルは ###）
        期待値: REQ2.1 が REQ2 の子として組まれ、根は REQ2 だけになる
        理由: 階層は番号のドットだけが正であり、見出しレベルで表さない仕様のため
        """
        doc = build_usdm.parse_document(WITH_CHILD, slice_id="S02")
        self.assertEqual(doc.violations, [])

        roots = build_usdm.build_tree(doc.requirements)
        self.assertEqual([r.number for r in roots], ["2"])
        self.assertEqual([c.number for c in roots[0].children], ["2.1"])


class ViolationTest(unittest.TestCase):
    """記法違反を実際に検出できることの検証（空振り防止）。"""

    def test_missing_reason_is_violation(self):
        """テスト対象: parse_document
        入力: 理由の行が無い要求
        期待値: 種別 missing-reason の違反が 1 件出る
        理由: 理由の必須性は USDM の核心ルールであり、機械検証の第一目的のため
        """
        text = VALID.replace(
            "- **理由**: 実データが 5 万行あり、全件出ると目的の行を目で探すことになる\n",
            "",
        )
        doc = build_usdm.parse_document(text, slice_id="S02")
        kinds = [v.kind for v in doc.violations]
        self.assertIn("missing-reason", kinds)

    def test_requirement_without_spec_is_violation(self):
        """テスト対象: parse_document
        入力: 要求と理由だけで仕様が 0 条の文書
        期待値: 種別 no-spec の違反が出る
        理由: L1 でも仕様は 1 条必要。要求だけ書いて止まった状態を検出するため
        """
        text = """\
# S02. テスト

**成熟度: `L1 動く`**

## 要求

### 【REQ2】絞り込みたい

- **理由**: 目で探すことになる
"""
        doc = build_usdm.parse_document(text, slice_id="S02")
        self.assertIn("no-spec", [v.kind for v in doc.violations])

    def test_spec_number_not_matching_parent_is_violation(self):
        """テスト対象: parse_document
        入力: REQ2 の配下に `<3-1>` という仕様番号
        期待値: 種別 spec-number-mismatch の違反が出る
        理由: 仕様は親要求から導出される。番号の食い違いは導出関係の破れのため
        """
        text = VALID.replace("`<2-1>`", "`<3-1>`")
        doc = build_usdm.parse_document(text, slice_id="S02")
        self.assertIn("spec-number-mismatch", [v.kind for v in doc.violations])

    def test_duplicate_requirement_number_is_violation(self):
        """テスト対象: parse_document
        入力: 同じ REQ2 を 2 回宣言した文書
        期待値: 種別 duplicate-requirement の違反が出る
        理由: 番号が要求の同一性を決めるため、重複すると参照が壊れる
        """
        text = WITH_CHILD.replace("【REQ2.1】", "【REQ2】").replace("`<2.1-1>`", "`<2-9>`")
        doc = build_usdm.parse_document(text, slice_id="S02")
        self.assertIn("duplicate-requirement", [v.kind for v in doc.violations])

    def test_duplicate_spec_number_is_violation(self):
        """テスト対象: parse_document
        入力: 同じ仕様番号 <2-1> を 2 回書いた文書
        期待値: 種別 duplicate-spec の違反が出る
        理由: 仕様番号はテストとの対応キーであり、重複すると対応が決まらないため
        """
        text = VALID.replace("`<2-2>`", "`<2-1>`")
        doc = build_usdm.parse_document(text, slice_id="S02")
        self.assertIn("duplicate-spec", [v.kind for v in doc.violations])

    def test_slice_number_mismatch_is_violation(self):
        """テスト対象: parse_document
        入力: ファイルが S02 なのに最上位要求が REQ3
        期待値: 種別 slice-number-mismatch の違反が出る
        理由: バックログのスライス行が要求一覧を兼ねる前提が崩れるため
        """
        text = VALID.replace("【REQ2】", "【REQ3】").replace("`<2-", "`<3-")
        doc = build_usdm.parse_document(text, slice_id="S02")
        self.assertIn("slice-number-mismatch", [v.kind for v in doc.violations])


class MainTest(unittest.TestCase):
    """コマンドとしての終了コードと --check の検証。"""

    def test_valid_document_generates_html_and_exits_zero(self):
        """テスト対象: main
        入力: 正しい USDM 文書 1 本を含むディレクトリ
        期待値: 終了コード 0 で、出力先の HTML が生成される
        理由: 正常な入力で誤検出しないことの確認（tool-authoring の必須項目）
        """
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "slices"
            src.mkdir()
            _write(src, "S02-csv-filter.md", VALID)
            out = Path(tmp) / "usdm" / "index.html"

            buf = io.StringIO()
            with redirect_stdout(buf):
                code = build_usdm.main(["--source", str(src), "--out", str(out)])

            self.assertEqual(code, 0, buf.getvalue())
            self.assertTrue(out.exists())

    def test_violation_exits_one(self):
        """テスト対象: main
        入力: 理由が無い USDM 文書
        期待値: 終了コード 1 で、違反の種別が標準出力に出る
        理由: 検査結果が終了コードで機械判定できること（呼び出し側の契約）のため
        """
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "slices"
            src.mkdir()
            _write(src, "S02-csv-filter.md", VALID.replace("- **理由**: 実データが 5 万行あり、全件出ると目的の行を目で探すことになる\n", ""))
            out = Path(tmp) / "usdm" / "index.html"

            buf = io.StringIO()
            with redirect_stdout(buf):
                code = build_usdm.main(["--source", str(src), "--out", str(out)])

            self.assertEqual(code, 1)
            self.assertIn("missing-reason", buf.getvalue())

    def test_no_source_file_exits_two(self):
        """テスト対象: main
        入力: USDM 文書が 1 本も無いディレクトリ
        期待値: 終了コード 2
        理由: 対象 0 件を成功にすると、何も検査しないまま緑を返すツールになるため
        """
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "slices"
            src.mkdir()
            out = Path(tmp) / "usdm" / "index.html"

            buf = io.StringIO()
            with redirect_stdout(buf):
                code = build_usdm.main(["--source", str(src), "--out", str(out)])

            self.assertEqual(code, 2)

    def test_check_reports_stale_after_requirement_changes(self):
        """テスト対象: main --check
        入力: HTML を生成した後、要求の本文を 1 行変える
        期待値: 変更前は 0（最新）、変更後は 1（STALE）
        理由: 生成物を gitignore する運用では、古さの検出だけが乖離を防ぐため
        """
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "slices"
            src.mkdir()
            doc = _write(src, "S02-csv-filter.md", VALID)
            out = Path(tmp) / "usdm" / "index.html"

            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(
                    build_usdm.main(["--source", str(src), "--out", str(out)]), 0
                )
                self.assertEqual(
                    build_usdm.main(
                        ["--source", str(src), "--out", str(out), "--check"]
                    ),
                    0,
                )

                doc.write_text(
                    VALID.replace("絞り込みたい", "絞り込んで並べ替えたい"),
                    encoding="utf-8",
                )
                self.assertEqual(
                    build_usdm.main(
                        ["--source", str(src), "--out", str(out), "--check"]
                    ),
                    1,
                )
            self.assertIn("STALE", buf.getvalue())


class HtmlTest(unittest.TestCase):
    """生成される HTML が自己完結かつ日本語を保つことの検証。"""

    def test_japanese_text_survives_into_html(self):
        """テスト対象: render_html
        入力: 日本語の要求・理由・仕様を含む文書
        期待値: HTML の中に日本語がそのまま現れる
        理由: Windows のコードページ由来の文字化けを検出するため（既知の事故）
        """
        doc = build_usdm.parse_document(VALID, slice_id="S02")
        html = build_usdm.render_html([doc])

        self.assertIn("列を指定して絞り込みたい", html)
        self.assertIn("目で探すことになる", html)
        self.assertIn("完全一致する行だけを数える", html)

    def test_html_has_no_external_reference(self):
        """テスト対象: render_html
        入力: 正しい USDM 文書
        期待値: http(s):// への参照・fetch・外部 src/href が含まれない
        理由: file:// で開ける自己完結ページであることが要求のため
        """
        doc = build_usdm.parse_document(VALID, slice_id="S02")
        html = build_usdm.render_html([doc])

        for forbidden in ("http://", "https://", "fetch(", "XMLHttpRequest", "<script src", "<link "):
            self.assertNotIn(forbidden, html, f"外部参照が残っている: {forbidden}")


if __name__ == "__main__":
    unittest.main()
