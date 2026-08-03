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
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_usdm

# 記入例（`.claude/skills/usdm/example/`）。テンプレートと実装が
# 食い違ったらここが落ちる。
SKILL_DIR = Path(__file__).resolve().parent.parent / "skills" / "usdm"
EXAMPLE_DIR = SKILL_DIR / "example"


def _doc(rows: str, kind: str = "functional", title: str = "S02. フィルタ") -> str:
    """要求 HTML 1 枚を組み立てる（テストの読みやすさのための最小骨格）。"""
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>{title}</title></head>
<body>
<h1>{title}</h1>
<p class="meta"><span class="badge maturity">L1 動く</span></p>
<table class="usdm {kind}">
<thead><tr><th>カテゴリ名</th><th>要求</th><th>要求ID</th><th>要求仕様</th></tr></thead>
<tbody>
{rows}
</tbody>
</table>
</body></html>
"""


VALID = _doc("""\
<tr class="requirement">
  <td class="category">抽出</td><td class="kind">要求</td>
  <td class="id">REQ2</td><td class="body">列を指定して絞り込みたい</td>
</tr>
<tr class="reason">
  <td></td><td></td><td class="kind">理由</td>
  <td class="body">実データが 5 万行あり、全件出ると目で探すことになる</td>
</tr>
<tr class="spec-group">
  <td></td><td></td><td class="kind">＜列指定＞</td><td></td>
</tr>
<tr class="spec">
  <td></td><td class="check">□</td><td class="id">2-1</td>
  <td class="body">--col NAME=値 を渡すと完全一致する行だけを数える</td>
</tr>
""")

WITH_CHILD = _doc("""\
<tr class="requirement">
  <td class="category">抽出</td><td class="kind">要求</td>
  <td class="id">REQ2</td><td class="body">列を指定して絞り込みたい</td>
</tr>
<tr class="reason">
  <td></td><td></td><td class="kind">理由</td>
  <td class="body">実データが 5 万行ある</td>
</tr>
<tr class="spec">
  <td></td><td class="check">☑</td><td class="id">2-1</td>
  <td class="body">--col NAME=値 で完全一致する行を数える</td>
</tr>
<tr class="requirement">
  <td></td><td class="kind">要求</td>
  <td class="id">REQ2.1</td><td class="body">複数列を AND で指定したい</td>
</tr>
<tr class="reason">
  <td></td><td></td><td class="kind">理由</td>
  <td class="body">1 列では絞り切れないデータがある</td>
</tr>
<tr class="spec">
  <td></td><td class="check">□</td><td class="id">2.1-1</td>
  <td class="body">--col を 2 回渡すと両方に一致する行だけを数える</td>
</tr>
""")


def _kinds(doc: build_usdm.Document) -> list[str]:
    """違反の種別だけを取り出す（メッセージ本文には依存しない）。"""
    return [v.kind for v in doc.violations]


class ParseTest(unittest.TestCase):
    """記法どおりの HTML を構造として取り出せること。"""

    def test_要求と理由と仕様を取り出す(self) -> None:
        doc = build_usdm.parse_document(VALID, doc_id="S02")
        self.assertEqual(doc.violations, [])
        self.assertEqual(doc.title, "フィルタ")
        self.assertEqual(doc.maturity, "L1 動く")
        self.assertEqual(doc.kind, "functional")
        self.assertEqual(len(doc.requirements), 1)

        req = doc.requirements[0]
        self.assertEqual(req.number, "2")
        self.assertEqual(req.title, "列を指定して絞り込みたい")
        self.assertEqual(req.category, "抽出")
        self.assertTrue(req.reason.startswith("実データが"))
        self.assertEqual([s.number for s in req.specs], ["2-1"])
        self.assertEqual(req.specs[0].group, "＜列指定＞")
        self.assertFalse(req.specs[0].verified)

    def test_チェック済みの仕様を検証済みとして読む(self) -> None:
        doc = build_usdm.parse_document(WITH_CHILD, doc_id="S02")
        self.assertEqual(doc.violations, [])
        self.assertTrue(doc.requirements[0].specs[0].verified)

    def test_番号のドットから親子を組む(self) -> None:
        doc = build_usdm.parse_document(WITH_CHILD, doc_id="S02")
        roots = build_usdm.build_tree(doc.requirements)
        self.assertEqual([r.number for r in roots], ["2"])
        self.assertEqual([c.number for c in roots[0].children], ["2.1"])

    def test_build_tree_は冪等(self) -> None:
        doc = build_usdm.parse_document(WITH_CHILD, doc_id="S02")
        build_usdm.build_tree(doc.requirements)
        roots = build_usdm.build_tree(doc.requirements)
        self.assertEqual(len(roots[0].children), 1)

    def test_セルの意味は位置ではなくclassで決まる(self) -> None:
        # 空の <td> を増やしても構造は変わらない（表示の都合に依存しない）
        padded = VALID.replace(
            '<td class="category">抽出</td>',
            '<td></td><td class="category">抽出</td>',
        )
        doc = build_usdm.parse_document(padded, doc_id="S02")
        self.assertEqual(doc.violations, [])
        self.assertEqual(doc.requirements[0].category, "抽出")

    def test_コメントの中の行は読まない(self) -> None:
        # テンプレートは使い方をコメントで示す。それが要求として拾われると困る
        commented = VALID.replace(
            "</tbody>",
            '<!-- <tr class="requirement"><td></td><td class="kind">要求</td>'
            '<td class="id">REQ9</td><td class="body">x</td></tr> -->\n</tbody>',
        )
        doc = build_usdm.parse_document(commented, doc_id="S02")
        self.assertEqual([r.number for r in doc.requirements], ["2"])


class ViolationTest(unittest.TestCase):
    """記法違反を検出できること（ここが本体）。"""

    def test_理由がなければ落とす(self) -> None:
        text = VALID.replace('<tr class="reason">', '<tr class="note">')
        doc = build_usdm.parse_document(text, doc_id="S02")
        self.assertIn("missing-reason", _kinds(doc))

    def test_仕様が0条なら落とす(self) -> None:
        text = _doc("""\
<tr class="requirement">
  <td></td><td class="kind">要求</td>
  <td class="id">REQ2</td><td class="body">絞り込みたい</td>
</tr>
<tr class="reason">
  <td></td><td></td><td class="kind">理由</td>
  <td class="body">5 万行ある</td>
</tr>
""")
        doc = build_usdm.parse_document(text, doc_id="S02")
        self.assertIn("no-spec", _kinds(doc))

    def test_仕様番号が親要求と違えば落とす(self) -> None:
        text = VALID.replace('<td class="id">2-1</td>', '<td class="id">3-1</td>')
        doc = build_usdm.parse_document(text, doc_id="S02")
        self.assertIn("spec-number-mismatch", _kinds(doc))

    def test_要求番号の重複を落とす(self) -> None:
        text = WITH_CHILD.replace("REQ2.1", "REQ2").replace(
            '<td class="id">2.1-1</td>', '<td class="id">2-9</td>'
        )
        doc = build_usdm.parse_document(text, doc_id="S02")
        self.assertIn("duplicate-requirement", _kinds(doc))

    def test_仕様番号の重複を落とす(self) -> None:
        text = WITH_CHILD.replace('<td class="id">2.1-1</td>', '<td class="id">2-1</td>')
        doc = build_usdm.parse_document(text, doc_id="S02")
        self.assertIn("duplicate-spec", _kinds(doc))

    def test_ファイル番号と最上位要求のずれを落とす(self) -> None:
        doc = build_usdm.parse_document(VALID, doc_id="S03")
        self.assertIn("doc-number-mismatch", _kinds(doc))

    def test_親のない下位要求を落とす(self) -> None:
        text = VALID.replace("REQ2", "REQ2.1").replace(
            '<td class="id">2-1</td>', '<td class="id">2.1-1</td>'
        )
        doc = build_usdm.parse_document(text, doc_id="S02")
        self.assertIn("orphan-requirement", _kinds(doc))

    def test_要求の外の仕様を落とす(self) -> None:
        text = _doc("""\
<tr class="spec">
  <td></td><td class="check">□</td><td class="id">2-1</td>
  <td class="body">迷子の仕様</td>
</tr>
""")
        doc = build_usdm.parse_document(text, doc_id="S02")
        self.assertIn("spec-without-requirement", _kinds(doc))

    def test_class_のない行を落とす(self) -> None:
        text = VALID.replace("</tbody>", "<tr><td>なにか</td></tr>\n</tbody>")
        doc = build_usdm.parse_document(text, doc_id="S02")
        self.assertIn("unknown-row", _kinds(doc))

    def test_要求IDの書式違反を落とす(self) -> None:
        text = VALID.replace('<td class="id">REQ2</td>', '<td class="id">R-2</td>')
        doc = build_usdm.parse_document(text, doc_id="S02")
        self.assertIn("missing-id", _kinds(doc))

    def test_検証欄が空なら落とす(self) -> None:
        text = VALID.replace('<td class="check">□</td>', '<td class="check"></td>')
        doc = build_usdm.parse_document(text, doc_id="S02")
        self.assertIn("bad-check", _kinds(doc))

    def test_表の種別とファイル名の不一致を落とす(self) -> None:
        text = VALID.replace('class="usdm functional"', 'class="usdm quality"')
        doc = build_usdm.parse_document(text, doc_id="S02")
        self.assertIn("kind-mismatch", _kinds(doc))


class QualityTest(unittest.TestCase):
    """品質要求だけのルール（定義・解釈・メトリクス・評価尺度）。"""

    QUALITY = """<!doctype html>
<html lang="ja"><head><meta charset="utf-8"></head><body>
<h1>Q01. 性能効率性</h1>
<p class="meta"><span class="badge maturity">L2 固い</span></p>
<table class="usdm quality">
<thead><tr><th>品質特性</th><th>品質副特性</th><th>要求</th><th>要求ID</th>
<th>要求仕様</th><th>評価尺度</th><th>対応知識・技術</th></tr></thead>
<tbody>
<tr class="characteristic">
  <td class="characteristic">性能効率性</td>
  <td class="subcharacteristic">時間効率性</td>
  <td></td><td class="kind">定義</td>
  <td class="body">応答時間が要求事項を満足する度合い</td><td></td><td></td>
</tr>
<tr class="interpretation">
  <td></td><td></td><td></td><td class="kind">解釈</td>
  <td class="body">朝の支度に支障がない程度か</td><td></td><td></td>
</tr>
<tr class="metrics">
  <td></td><td></td><td></td><td class="kind">メトリクス</td>
  <td class="body">通電から沸騰までの経過時間</td><td></td><td></td>
</tr>
<tr class="requirement">
  <td></td><td></td><td class="kind">要求</td><td class="id">QUA1</td>
  <td class="body">沸騰までの待ち時間を少なくしたい</td><td></td><td></td>
</tr>
<tr class="reason">
  <td></td><td></td><td></td><td class="kind">理由</td>
  <td class="body">朝は 15 分しか余裕がない</td><td></td><td></td>
</tr>
<tr class="spec">
  <td></td><td></td><td class="check">□</td><td class="id">Q1-1</td>
  <td class="body">100 mL の水を 1 分以内に沸騰させる</td>
  <td class="measure">通電から沸騰検知までの秒数</td>
  <td class="knowledge">ヒータ出力設計</td>
</tr>
</tbody></table></body></html>
"""

    def test_品質要求を取り出す(self) -> None:
        doc = build_usdm.parse_document(self.QUALITY, doc_id="Q01")
        self.assertEqual(doc.violations, [])
        self.assertEqual(doc.kind, "quality")
        self.assertEqual(doc.characteristics[0].name, "性能効率性")
        self.assertEqual(doc.characteristics[0].sub, "時間効率性")
        # QUA1 は番号 Q1（仕様 Q1-1 の親）として扱う
        self.assertEqual(doc.requirements[0].number, "Q1")
        self.assertEqual(doc.requirements[0].specs[0].measure, "通電から沸騰検知までの秒数")

    def test_解釈がなければ落とす(self) -> None:
        text = self.QUALITY.replace('<tr class="interpretation">', '<tr class="note">')
        doc = build_usdm.parse_document(text, doc_id="Q01")
        self.assertIn("missing-interpretation", _kinds(doc))

    def test_メトリクスがなければ落とす(self) -> None:
        text = self.QUALITY.replace('<tr class="metrics">', '<tr class="note">')
        doc = build_usdm.parse_document(text, doc_id="Q01")
        self.assertIn("missing-metrics", _kinds(doc))

    def test_評価尺度のない仕様を落とす(self) -> None:
        text = self.QUALITY.replace(
            '<td class="measure">通電から沸騰検知までの秒数</td>',
            '<td class="measure"></td>',
        )
        doc = build_usdm.parse_document(text, doc_id="Q01")
        self.assertIn("missing-measure", _kinds(doc))

    def test_品質特性ブロックがなければ落とす(self) -> None:
        text = self.QUALITY.replace('<tr class="characteristic">', '<tr class="note">')
        doc = build_usdm.parse_document(text, doc_id="Q01")
        self.assertIn("missing-characteristic", _kinds(doc))


class ExampleTest(unittest.TestCase):
    """配布する記入例が、実装した記法どおりであること。"""

    def test_記入例に違反がない(self) -> None:
        documents = build_usdm.collect([str(EXAMPLE_DIR)])
        self.assertEqual(len(documents), 2)
        for doc in documents:
            self.assertEqual(doc.violations, [], f"{doc.source} に違反がある")

    def test_記入例は機能要求と品質要求を1枚ずつ持つ(self) -> None:
        documents = build_usdm.collect([str(EXAMPLE_DIR)])
        self.assertEqual(
            sorted(d.kind for d in documents), ["functional", "quality"]
        )


class CommandTest(unittest.TestCase):
    """コマンドとしての終了コードと生成物。"""

    def _write(self, directory: Path, name: str, text: str) -> None:
        (directory / name).write_text(text, encoding="utf-8")

    def test_正常な文書なら0で生成する(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir()
            out = Path(tmp) / "usdm" / "index.html"
            self._write(src, "S02-filter.html", VALID)
            with redirect_stdout(io.StringIO()):
                code = build_usdm.main(["--source", str(src), "--out", str(out)])
            self.assertEqual(code, 0)
            self.assertTrue(out.exists())
            self.assertIn("要求一覧", out.read_text(encoding="utf-8"))

    def test_違反があれば1を返し生成しない(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir()
            out = Path(tmp) / "usdm" / "index.html"
            broken = VALID.replace('<tr class="reason">', '<tr class="note">')
            self._write(src, "S02-filter.html", broken)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = build_usdm.main(["--source", str(src), "--out", str(out)])
            self.assertEqual(code, 1)
            self.assertFalse(out.exists())
            self.assertIn("missing-reason", buf.getvalue())

    def test_対象が0件なら2を返す(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir()
            out = Path(tmp) / "usdm" / "index.html"
            with redirect_stdout(io.StringIO()):
                code = build_usdm.main(["--source", str(src), "--out", str(out)])
            self.assertEqual(code, 2)

    def test_checkは古い生成物を検出する(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            src.mkdir()
            out = Path(tmp) / "usdm" / "index.html"
            self._write(src, "S02-filter.html", VALID)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(
                    build_usdm.main(["--source", str(src), "--out", str(out)]), 0
                )
                self.assertEqual(
                    build_usdm.main(
                        ["--source", str(src), "--out", str(out), "--check"]
                    ),
                    0,
                )
            self._write(src, "S02-filter.html", WITH_CHILD)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = build_usdm.main(
                    ["--source", str(src), "--out", str(out), "--check"]
                )
            self.assertEqual(code, 1)
            self.assertIn("STALE", buf.getvalue())


class AssetTest(unittest.TestCase):
    """見た目と操作は共有の 2 ファイルが持ち、手書きと生成物で 1 つであること。"""

    def test_共有アセットが実在する(self) -> None:
        for name in ("usdm.css", "usdm.js"):
            self.assertTrue((SKILL_DIR / name).is_file(), name)

    def test_テンプレートと記入例は共有アセットを参照する(self) -> None:
        # 各ファイルに CSS/JS を写すと、直したときに片方だけ古くなる
        for path in [
            SKILL_DIR / "template.html",
            SKILL_DIR / "template-quality.html",
            *sorted(EXAMPLE_DIR.glob("*.html")),
        ]:
            text = path.read_text(encoding="utf-8")
            self.assertIn("usdm.css", text, path.name)
            self.assertIn("usdm.js", text, path.name)
            self.assertNotIn("<style>", text, f"{path.name} に CSS を写している")

    def test_操作は共有JSが組み立てる(self) -> None:
        script = (SKILL_DIR / "usdm.js").read_text(encoding="utf-8")
        for control in ("すべて開く", "すべて閉じる", "仕様: 未検証のみ",
                        "仕様: 検証済みのみ"):
            self.assertIn(control, script)
        # 折りたたみは 文書 / 要求グループ / 要求 / 仕様グループ の 4 段階
        for kind in ("characteristic", "req-group", "requirement", "spec-group"):
            self.assertIn(kind, script)


class RenderTest(unittest.TestCase):
    """生成物が自己完結で、手書きと同じ表であること。"""

    def test_外部参照を含まない(self) -> None:
        doc = build_usdm.parse_document(VALID, doc_id="S02")
        rendered = build_usdm.render_html([doc])
        for forbidden in ("http://", "https://", "<link", "src="):
            self.assertNotIn(forbidden, rendered)

    def test_共有アセットを埋め込む(self) -> None:
        doc = build_usdm.parse_document(VALID, doc_id="S02")
        rendered = build_usdm.render_html([doc])
        for name in ("usdm.css", "usdm.js"):
            self.assertIn((SKILL_DIR / name).read_text(encoding="utf-8"), rendered)

    def test_日時を埋め込まない(self) -> None:
        doc = build_usdm.parse_document(VALID, doc_id="S02")
        first = build_usdm.render_html([doc])
        second = build_usdm.render_html([doc])
        self.assertEqual(first, second)

    def test_手書きと同じ列見出しを持つ(self) -> None:
        doc = build_usdm.parse_document(VALID, doc_id="S02")
        rendered = build_usdm.render_html([doc])
        for column in ("カテゴリ名", "要求ID", "要求仕様"):
            self.assertIn(column, rendered)

    def test_生成物を読み直すと同じ要求になる(self) -> None:
        # 「手書きと生成物は同じ表構造」を機械で守る。生成した HTML を
        # 同じパーサに戻して、要求が一致し違反 0 件であることを確かめる。
        source = build_usdm.parse_document(WITH_CHILD, doc_id="S02")
        round_trip = build_usdm.parse_document(
            build_usdm.render_html([source]), doc_id="S02"
        )
        self.assertEqual(round_trip.violations, [])
        self.assertEqual(
            [(r.number, r.reason) for r in round_trip.requirements],
            [(r.number, r.reason) for r in source.requirements],
        )
        self.assertEqual(
            [(s.number, s.verified) for r in round_trip.requirements for s in r.specs],
            [(s.number, s.verified) for r in source.requirements for s in r.specs],
        )

    def test_品質要求も読み直せる(self) -> None:
        source = build_usdm.parse_document(QualityTest.QUALITY, doc_id="Q01")
        round_trip = build_usdm.parse_document(
            build_usdm.render_html([source]), doc_id="Q01"
        )
        self.assertEqual(round_trip.violations, [])
        self.assertEqual(round_trip.characteristics[0].metrics,
                         source.characteristics[0].metrics)
        self.assertEqual(round_trip.requirements[0].specs[0].measure,
                         source.requirements[0].specs[0].measure)

    def test_全ての行がヘッダと同じ列数を持つ(self) -> None:
        documents = build_usdm.collect([str(EXAMPLE_DIR)])
        rendered = build_usdm.render_html(documents)
        for table in re.findall(r"<table class=\"usdm[^\"]*\">.*?</table>",
                                rendered, re.DOTALL):
            width = table.count("<th>")
            for row in re.findall(r"<tr class=\"[^\"]*\">.*?</tr>", table, re.DOTALL):
                self.assertEqual(row.count("<td"), width, row[:60])


if __name__ == "__main__":
    unittest.main()
