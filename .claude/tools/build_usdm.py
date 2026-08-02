"""USDM 形式の要求（HTML の表）を検証し、要求一覧 1 枚の HTML を生成する。

記法の正は `.claude/skills/usdm/SKILL.md`。このツールは 2 つの仕事をする。

1. **機械検証** —— USDM の核心ルール（理由の必須性・仕様の導出関係）を
   終了コードで判定できる形に落とす。LLM の判断に頼らない
2. **生成** —— 手書きの要求 HTML（`docs/usdm/src/*.html`）を 1 枚に束ねる。
   外部参照ゼロなので `file://` でそのまま開ける

手書きの正と生成物は **同じ表構造** にする。1 枚を開いても一覧を開いても、
Excel テンプレートと同じ列（カテゴリ名 / 要求 / 要求ID / 要求仕様）が並ぶ。

検出する違反:

    unknown-row              class の無い / 未知の <tr>
    missing-id               要求ID・仕様ID が無い、または書式違反
    missing-reason           理由が無い要求（USDM の核心ルール違反）
    no-spec                  仕様が 0 条の要求
    spec-number-mismatch     仕様番号の要求部分が親要求と違う
    duplicate-requirement    要求番号の重複
    duplicate-spec           仕様番号の重複
    doc-number-mismatch      ファイルの S##/Q## と最上位要求の番号が違う
    kind-mismatch            ファイル名（S/Q）と表の種別（functional/quality）が違う
    orphan-requirement       親要求が宣言されていない下位要求
    spec-without-requirement 要求の外に置かれた仕様
    reason-without-requirement 要求の外に置かれた理由
    bad-check                検証欄が □ でも ☑ でもない
    missing-characteristic   品質要求に品質特性ブロックが無い
    missing-interpretation   品質特性に解釈が無い
    missing-metrics          品質特性にメトリクスが無い
    missing-measure          品質要求の仕様に評価尺度が無い

生成物に日時を埋め込まない。埋め込むと --check が常に STALE になる。

使い方（前置コマンドはプロファイルの
「.claude/tools/ の Python ツール実行」。例: uv run python）:
    <ツール実行コマンド> .claude/tools/build_usdm.py
    <ツール実行コマンド> .claude/tools/build_usdm.py --check
    <ツール実行コマンド> .claude/tools/build_usdm.py --source .claude/skills/usdm/example

終了コード:
    0 = 生成に成功（--check では HTML が最新）
    1 = USDM 違反がある、または --check で STALE
    2 = 引数のエラー、または対象の USDM 文書が 0 件
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

# 記法の契約（`.claude/skills/usdm/SKILL.md` と一対一で対応させる）
_DOC_FILE = re.compile(r"^([SQ][0-9]+)-.+\.html$", re.IGNORECASE)
_REQ_ID = re.compile(r"^(REQ|QUA)([0-9]+(?:\.[0-9]+)*)$")
_SPEC_ID = re.compile(r"^<?(Q?[0-9]+(?:\.[0-9]+)*)-([0-9]+)>?$")
_CHECKED = "☑"
_UNCHECKED = "□"
# 見出しの「S02.」は表示側が前置するので落とす（重複表示の防止）
_TITLE_PREFIX = re.compile(r"^[SQ][0-9]+\s*[.．]\s*", re.IGNORECASE)

# <tr class="..."> に書ける行の種別
_ROW_KINDS = {
    "requirement",
    "reason",
    "note",
    "req-group",
    "spec-group",
    "spec",
    "characteristic",
    "interpretation",
    "metrics",
}
# <td class="..."> に書けるセルの種別。`kind` はラベル欄で、
# グループ行（＜…＞）だけが意味を持つ（他の行では表示専用）。
_CELL_KINDS = {
    "category",
    "kind",
    "id",
    "body",
    "check",
    "measure",
    "knowledge",
    "characteristic",
    "subcharacteristic",
}


@dataclass
class Spec:
    """仕様 1 条。number は `<要求番号>-<連番>` の中身。"""

    number: str
    text: str
    verified: bool
    line: int
    group: str = ""
    measure: str = ""
    knowledge: str = ""


@dataclass
class Requirement:
    """要求 1 個。階層は number のドットだけが正（行の位置では表さない）。"""

    number: str
    title: str
    line: int
    category: str = ""
    group: str = ""
    reason: str = ""
    note: str = ""
    specs: list[Spec] = field(default_factory=list)
    children: list[Requirement] = field(default_factory=list)


@dataclass
class Characteristic:
    """品質特性ブロック 1 個（定義 → 解釈 → メトリクス）。品質要求だけが持つ。"""

    name: str
    sub: str
    definition: str
    line: int
    interpretation: str = ""
    metrics: str = ""
    note: str = ""


@dataclass
class Violation:
    """USDM 記法の違反 1 件。kind は機械判定用の種別。"""

    kind: str
    message: str
    line: int
    source: str = ""


@dataclass
class Document:
    """USDM 文書 1 本（スライス 1 枚、または品質特性 1 枚）。"""

    doc_id: str
    kind: str
    title: str
    maturity: str
    requirements: list[Requirement]
    characteristics: list[Characteristic]
    violations: list[Violation]
    source: str = ""


@dataclass
class _Row:
    """表の 1 行を、行種別とセル（class 名 → 文字列）に落としたもの。"""

    kind: str
    cells: dict[str, str]
    line: int


class _TableReader(HTMLParser):
    """要求 HTML から h1・成熟度・表の種別・行の一覧を取り出す。

    セルの意味は **位置ではなく class** で決める。空の `<td></td>` は
    Excel と同じ見た目にするためのもので、意味を持たない。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.maturity = ""
        self.table_kind = ""
        self.rows: list[_Row] = []
        self._in_h1 = False
        self._in_thead = False
        self._in_maturity = False
        self._row: _Row | None = None
        self._cell: str | None = None
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = _classes(attrs)
        if tag == "h1":
            self._in_h1 = True
            self._buf = []
        elif tag == "table" and "usdm" in classes:
            for candidate in ("functional", "quality"):
                if candidate in classes:
                    self.table_kind = candidate
        elif tag == "thead":
            self._in_thead = True
        elif tag == "tr" and not self._in_thead:
            kind = next((c for c in classes if c in _ROW_KINDS), "")
            self._row = _Row(kind, {}, self.getpos()[0])
            self.rows.append(self._row)
        elif tag == "td" and self._row is not None:
            self._cell = next((c for c in classes if c in _CELL_KINDS), "")
            self._buf = []
        elif tag == "span" and "maturity" in classes:
            self._in_maturity = True
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1" and self._in_h1:
            self.title = _flat("".join(self._buf))
            self._in_h1 = False
            self._buf = []
        elif tag == "thead":
            self._in_thead = False
        elif tag == "tr":
            self._row = None
        elif tag == "td" and self._row is not None and self._cell is not None:
            if self._cell:
                self._row.cells[self._cell] = _flat("".join(self._buf))
            self._cell = None
            self._buf = []
        elif tag == "span" and self._in_maturity:
            self.maturity = _flat("".join(self._buf))
            self._in_maturity = False
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._in_h1 or self._in_maturity or self._cell is not None:
            self._buf.append(data)


def _classes(attrs: list[tuple[str, str | None]]) -> set[str]:
    """開始タグの属性から class の集合を取り出す。"""
    for name, value in attrs:
        if name == "class" and value:
            return set(value.split())
    return set()


def _flat(text: str) -> str:
    """セルの文字列を 1 行に畳む（改行とインデントは見た目のためのもの）。"""
    return re.sub(r"\s+", " ", text).strip()


def _doc_number(doc_id: str) -> str:
    """`S02` → `2`、`Q01` → `Q1`。要求番号と突き合わせるための正規化。"""
    prefix, digits = doc_id[0].upper(), doc_id[1:].lstrip("0") or "0"
    return digits if prefix == "S" else "Q" + digits


def parse_document(text: str, doc_id: str, source: str = "") -> Document:
    """要求 HTML を構造として取り出し、記法違反を集める。

    Args:
        text: HTML の全文。
        doc_id: ファイル名から取った文書番号（例: `S02` / `Q01`）。
        source: 表示用のパス（違反の出力に添える）。

    Returns:
        要求の一覧と違反の一覧を持つ Document。
    """
    reader = _TableReader()
    reader.feed(text)
    reader.close()

    violations: list[Violation] = []
    requirements: list[Requirement] = []
    characteristics: list[Characteristic] = []
    current: Requirement | None = None
    characteristic: Characteristic | None = None
    req_group = ""
    spec_group = ""

    expected_kind = "functional" if doc_id[0].upper() == "S" else "quality"
    if reader.table_kind and reader.table_kind != expected_kind:
        violations.append(
            Violation(
                "kind-mismatch",
                f"{doc_id} の表が {reader.table_kind}"
                f"（{expected_kind} であるべき）",
                1,
                source,
            )
        )
    kind = reader.table_kind or expected_kind

    for row in reader.rows:
        if not row.kind:
            violations.append(
                Violation("unknown-row", "class の無い <tr> がある", row.line, source)
            )
            continue

        cells = row.cells
        body = cells.get("body", "")

        if row.kind == "requirement":
            number = _requirement_number(cells.get("id", ""))
            if number is None:
                violations.append(
                    Violation(
                        "missing-id",
                        f"要求の ID が `REQ<番号>` / `QUA<番号>` の形ではない"
                        f"（{cells.get('id', '(空)')}）",
                        row.line,
                        source,
                    )
                )
                current = None
                continue
            current = Requirement(
                number=number,
                title=body,
                line=row.line,
                category=cells.get("category", ""),
                group=req_group,
            )
            requirements.append(current)
            spec_group = ""
            continue

        if row.kind == "spec":
            spec = _make_spec(cells, row.line, spec_group, violations, source)
            if spec is None:
                continue
            if current is None:
                violations.append(
                    Violation(
                        "spec-without-requirement",
                        f"仕様 {spec.number} が要求の外に置かれている",
                        row.line,
                        source,
                    )
                )
            else:
                current.specs.append(spec)
            continue

        if row.kind == "req-group":
            req_group = _group_label(row)
            continue

        if row.kind == "spec-group":
            spec_group = _group_label(row)
            continue

        if row.kind == "reason":
            if current is None:
                violations.append(
                    Violation(
                        "reason-without-requirement",
                        "理由が要求の外に置かれている",
                        row.line,
                        source,
                    )
                )
            elif not current.reason:
                current.reason = body
            continue

        if row.kind == "note":
            if current is not None and not current.note:
                current.note = body
            elif characteristic is not None and not characteristic.note:
                characteristic.note = body
            continue

        if row.kind == "characteristic":
            characteristic = Characteristic(
                name=cells.get("characteristic", ""),
                sub=cells.get("subcharacteristic", ""),
                definition=body,
                line=row.line,
            )
            characteristics.append(characteristic)
            continue

        if row.kind in ("interpretation", "metrics"):
            if characteristic is None:
                violations.append(
                    Violation(
                        "missing-characteristic",
                        f"{row.kind} が品質特性ブロックの外に置かれている",
                        row.line,
                        source,
                    )
                )
            elif row.kind == "interpretation":
                characteristic.interpretation = body
            else:
                characteristic.metrics = body

    violations.extend(_validate(requirements, doc_id, source))
    if kind == "quality":
        violations.extend(_validate_quality(characteristics, requirements, source))

    return Document(
        doc_id, kind, _TITLE_PREFIX.sub("", reader.title), reader.maturity,
        requirements, characteristics, violations, source,
    )


def _requirement_number(raw: str) -> str | None:
    """`REQ2` → `2`、`QUA1` → `Q1`。形が違えば None。"""
    matched = _REQ_ID.match(raw.strip())
    if not matched:
        return None
    prefix, digits = matched.group(1), matched.group(2)
    return digits if prefix == "REQ" else "Q" + digits


def _group_label(row: _Row) -> str:
    """グループ行の名前（`＜…＞`）。ラベル欄（`td.kind`）に書く。"""
    return row.cells.get("kind", "")


def _make_spec(
    cells: dict[str, str],
    line: int,
    group: str,
    violations: list[Violation],
    source: str,
) -> Spec | None:
    """仕様行 1 行を Spec にする。ID か検証欄が不正なら違反を積む。"""
    raw = cells.get("id", "")
    matched = _SPEC_ID.match(raw.strip())
    if not matched:
        violations.append(
            Violation(
                "missing-id",
                f"仕様の ID が `<要求番号>-<連番>` の形ではない（{raw or '(空)'}）",
                line,
                source,
            )
        )
        return None

    check = cells.get("check", "")
    if check not in (_CHECKED, _UNCHECKED):
        violations.append(
            Violation(
                "bad-check",
                f"仕様 {matched.group(0)} の検証欄が"
                f"「{check or '(空)'}」（{_UNCHECKED} か {_CHECKED} を書く）",
                line,
                source,
            )
        )

    return Spec(
        number=f"{matched.group(1)}-{matched.group(2)}",
        text=cells.get("body", ""),
        verified=check == _CHECKED,
        line=line,
        group=group,
        measure=cells.get("measure", ""),
        knowledge=cells.get("knowledge", ""),
    )


def _validate(
    requirements: list[Requirement], doc_id: str, source: str
) -> list[Violation]:
    """要求の一覧を USDM のルールに照らし、違反を列挙する。"""
    violations: list[Violation] = []
    declared = {r.number for r in requirements}
    seen_requirements: set[str] = set()
    seen_specs: dict[str, int] = {}
    doc_number = _doc_number(doc_id)

    for req in requirements:
        if req.number in seen_requirements:
            violations.append(
                Violation(
                    "duplicate-requirement",
                    f"要求番号 {req.number} が重複している",
                    req.line,
                    source,
                )
            )
        seen_requirements.add(req.number)

        if not req.reason:
            violations.append(
                Violation(
                    "missing-reason",
                    f"{req.number} に理由がない（USDM では理由は必須）",
                    req.line,
                    source,
                )
            )

        if not req.specs:
            violations.append(
                Violation(
                    "no-spec", f"{req.number} に仕様が 1 条もない", req.line, source
                )
            )

        parent = req.number.rpartition(".")[0]
        if parent and parent not in declared:
            violations.append(
                Violation(
                    "orphan-requirement",
                    f"{req.number} の親 {parent} が宣言されていない",
                    req.line,
                    source,
                )
            )

        if not parent and req.number != doc_number:
            violations.append(
                Violation(
                    "doc-number-mismatch",
                    f"{doc_id} の最上位要求が {req.number}"
                    f"（{doc_number} であるべき）",
                    req.line,
                    source,
                )
            )

        for spec in req.specs:
            owner = spec.number.rpartition("-")[0]
            if owner != req.number:
                violations.append(
                    Violation(
                        "spec-number-mismatch",
                        f"仕様 {spec.number} が要求 {req.number} の配下にある"
                        f"（{req.number}-n であるべき）",
                        spec.line,
                        source,
                    )
                )
            if spec.number in seen_specs:
                violations.append(
                    Violation(
                        "duplicate-spec",
                        f"仕様番号 {spec.number} が重複している"
                        f"（{seen_specs[spec.number]} 行目と同じ）",
                        spec.line,
                        source,
                    )
                )
            else:
                seen_specs[spec.number] = spec.line

    return violations


def _validate_quality(
    characteristics: list[Characteristic],
    requirements: list[Requirement],
    source: str,
) -> list[Violation]:
    """品質要求だけのルール（定義・解釈・メトリクス・評価尺度）を検査する。"""
    violations: list[Violation] = []

    if not characteristics:
        violations.append(
            Violation(
                "missing-characteristic",
                "品質要求に品質特性ブロック（定義）が 1 つも無い",
                1,
                source,
            )
        )

    for char in characteristics:
        if not char.interpretation:
            violations.append(
                Violation(
                    "missing-interpretation",
                    f"品質特性「{char.name or '(無名)'}」に解釈がない"
                    "（定義を写しただけでは要求を導けない）",
                    char.line,
                    source,
                )
            )
        if not char.metrics:
            violations.append(
                Violation(
                    "missing-metrics",
                    f"品質特性「{char.name or '(無名)'}」にメトリクスがない",
                    char.line,
                    source,
                )
            )

    for req in requirements:
        for spec in req.specs:
            if not spec.measure:
                violations.append(
                    Violation(
                        "missing-measure",
                        f"仕様 {spec.number} に評価尺度がない"
                        "（測れない品質要求は書かない）",
                        spec.line,
                        source,
                    )
                )

    return violations


def build_tree(requirements: list[Requirement]) -> list[Requirement]:
    """番号のドットから親子を組み、根の要求だけを返す（冪等）。"""
    by_number = {r.number: r for r in requirements}
    for req in requirements:
        req.children = []

    roots: list[Requirement] = []
    for req in requirements:
        parent = req.number.rpartition(".")[0]
        if parent and parent in by_number:
            by_number[parent].children.append(req)
        else:
            roots.append(req)
    return roots


def collect(sources: list[str]) -> list[Document]:
    """指定パス配下の `S##-*.html` / `Q##-*.html` を読み、Document を返す。

    Args:
        sources: 探索するディレクトリまたはファイルのパス。

    Returns:
        文書番号で並べた Document の一覧（対象が無ければ空）。
    """
    paths: list[Path] = []
    for raw in sources:
        path = Path(raw)
        if path.is_file() and _DOC_FILE.match(path.name):
            paths.append(path)
        elif path.is_dir():
            paths.extend(p for p in path.glob("*.html") if _DOC_FILE.match(p.name))

    documents: list[Document] = []
    for path in sorted(set(paths), key=lambda p: (p.name, str(p))):
        matched = _DOC_FILE.match(path.name)
        assert matched is not None  # glob 側で保証済み
        documents.append(
            parse_document(
                path.read_text(encoding="utf-8"),
                doc_id=matched.group(1).upper(),
                source=str(path),
            )
        )
    return documents


def _to_payload(documents: list[Document]) -> list[dict]:
    """HTML に埋め込む JSON 構造へ変換する（要求は木の形にする）。"""

    def node(req: Requirement) -> dict:
        return {
            "number": req.number,
            "title": req.title,
            "category": req.category,
            "group": req.group,
            "reason": req.reason,
            "note": req.note,
            "specs": [
                {
                    "number": s.number,
                    "text": s.text,
                    "verified": s.verified,
                    "group": s.group,
                    "measure": s.measure,
                    "knowledge": s.knowledge,
                }
                for s in req.specs
            ],
            "children": [node(c) for c in req.children],
        }

    return [
        {
            "id": doc.doc_id,
            "kind": doc.kind,
            "title": doc.title,
            "maturity": doc.maturity,
            "source": doc.source.replace("\\", "/"),
            "characteristics": [
                {
                    "name": c.name,
                    "sub": c.sub,
                    "definition": c.definition,
                    "interpretation": c.interpretation,
                    "metrics": c.metrics,
                    "note": c.note,
                }
                for c in doc.characteristics
            ],
            "requirements": [node(r) for r in build_tree(doc.requirements)],
        }
        for doc in documents
    ]


# 手書きの正（`docs/usdm/src/*.html`）と同じ見た目にする。
# 片方だけ直すと「同じ表構造」という約束が崩れるので、必ず両方を直す。
_STYLE = """\
:root{color-scheme:light dark;--bg:#fbfbfd;--fg:#1a1a1f;--muted:#5d5d6b;
 --line:#c9c9d4;--card:#fff;--head:#eceffb;--accent:#3a5ccc;--req:#f2f5ff;
 --ok:#1f7a4d;--todo:#8a6d1f}
@media (prefers-color-scheme:dark){:root{--bg:#16161a;--fg:#ececf2;--muted:#a0a0b0;
 --line:#3a3a46;--card:#1e1e24;--head:#252a3d;--accent:#8fa6f5;--req:#212739;
 --ok:#5fd39b;--todo:#e0bf6a}}
*{box-sizing:border-box}
body{margin:0;padding:2rem 1.25rem 4rem;background:var(--bg);color:var(--fg);
 font-family:"Segoe UI","Hiragino Kaku Gothic ProN","Yu Gothic UI",Meiryo,sans-serif;
 line-height:1.7}
.wrap{max-width:78rem;margin:0 auto}
h1{font-size:1.4rem;margin:0 0 .25rem}
.lead{color:var(--muted);margin:0 0 1.25rem;font-size:.88rem}
.tools{position:sticky;top:0;background:var(--bg);padding:.75rem 0 1rem;z-index:2}
input[type=search]{width:100%;padding:.6rem .8rem;font-size:1rem;color:var(--fg);
 background:var(--card);border:1px solid var(--line);border-radius:.5rem}
.chips{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin-top:.5rem}
.chips select,.chips button{font:inherit;font-size:.85rem;color:var(--fg);
 background:var(--card);border:1px solid var(--line);border-radius:.4rem;
 padding:.25rem .7rem;cursor:pointer}
.chips select:hover,.chips button:hover{border-color:var(--accent)}
.count{color:var(--muted);font-size:.85rem;margin:0 0 0 auto}
.caret{display:inline-block;width:1em;color:var(--muted);font-size:.8rem}
tr.foldable{cursor:pointer}
tr.foldable:hover>td{filter:brightness(1.05)}
.section-title{font-size:1.05rem;margin:1.75rem 0 .9rem;padding-bottom:.3rem;
 border-bottom:2px solid var(--line)}
.doc{margin:0 0 2.5rem}
.doc>header{display:flex;flex-wrap:wrap;gap:.4rem;align-items:baseline;
 margin:0 0 .6rem;cursor:pointer}
.doc h2{font-size:1.05rem;margin:0 .4rem 0 0}
.badge{display:inline-block;border:1px solid var(--line);border-radius:1rem;
 padding:.05rem .55rem;font-size:.75rem;color:var(--muted);white-space:nowrap}
.scroll{overflow-x:auto}
table.usdm{border-collapse:collapse;width:100%;background:var(--card);font-size:.92rem}
table.usdm.functional{min-width:48rem}
table.usdm.quality{min-width:62rem}
table.usdm th,table.usdm td{border:1px solid var(--line);padding:.35rem .6rem;
 vertical-align:top;text-align:left}
table.usdm thead th{background:var(--head);white-space:nowrap;font-size:.85rem}
td.kind{white-space:nowrap;color:var(--muted);font-weight:600}
td.id{white-space:nowrap;color:var(--accent);
 font-family:ui-monospace,Consolas,"Cascadia Mono",monospace}
td.check{text-align:center;width:2.6rem;font-size:1rem}
td.category,td.characteristic,td.subcharacteristic{white-space:nowrap;color:var(--muted)}
td.measure,td.knowledge{font-size:.86rem;color:var(--muted)}
tr.requirement>td{background:var(--req);font-weight:600}
tr.req-group>td.kind,tr.spec-group>td.kind{font-weight:700;color:var(--fg)}
tr.characteristic>td,tr.interpretation>td,tr.metrics>td{background:var(--head)}
tr.note>td{color:var(--muted)}
.empty{color:var(--muted);padding:2rem 0}
"""

_SCRIPT = """\
var DATA = JSON.parse(document.getElementById('usdm-data').textContent);
var root = document.getElementById('docs');
var counter = document.getElementById('count');
var box = document.getElementById('q');
var filterBox = document.getElementById('f');

var COLUMNS = {
  functional: ['カテゴリ名', '要求', '要求ID', '要求仕様'],
  quality: ['品質特性', '品質副特性', '要求', '要求ID', '要求仕様',
            '評価尺度', '対応知識・技術']
};

// 折りたたみ状態。キーは 文書 / 要求グループ / 要求 / 仕様グループ の 4 段階。
// 検索中は折りたたみを無視して開く（畳んだせいで結果が消えるのを防ぐ）。
var closed = {};
var query = '';

function isClosed(key) { return !query && closed[key] === true; }
function caretFor(key) { return isClosed(key) ? '▸' : '▾'; }
function toggle(key) { closed[key] = !closed[key]; render(); }

function el(tag, cls, text) {
  var n = document.createElement(tag);
  if (cls) { n.className = cls; }
  if (text !== undefined && text !== null) { n.textContent = text; }
  return n;
}

// 手書きの HTML と同じ列の並びを 1 か所で決める。
// 先頭（カテゴリ名 / 品質特性・品質副特性）→ 要求欄 → 要求ID欄 →
// 要求仕様 →（品質のみ）評価尺度・対応知識。
function makeRow(kind, cls, f) {
  var cells = [];
  if (kind === 'quality') {
    cells.push(['characteristic', f.characteristic]);
    cells.push(['subcharacteristic', f.sub]);
  } else {
    cells.push(['category', f.category]);
  }
  // 開閉の三角は、ラベル欄（要求 / ＜グループ名＞）の頭に置く
  cells.push(f.check !== undefined
    ? ['check', f.check]
    : ['kind', f.mark, null, f.mark ? f.caret : null]);
  cells.push(f.id
    ? ['id', f.id]
    : ['kind', f.label, null, f.mark ? null : f.caret]);
  cells.push(['body', f.body, f.indent]);
  if (kind === 'quality') {
    cells.push(['measure', f.measure]);
    cells.push(['knowledge', f.knowledge]);
  }

  var tr = el('tr', cls);
  cells.forEach(function (c) {
    var td = el('td', c[0]);
    if (c[3]) { td.appendChild(el('span', 'caret', c[3])); }
    td.appendChild(document.createTextNode(c[1] === undefined ? '' : c[1]));
    if (c[2]) { td.style.paddingLeft = c[2]; }
    tr.appendChild(td);
  });
  return tr;
}

function foldRow(kind, cls, f, key) {
  var tr = makeRow(kind, cls + ' foldable', f);
  tr.addEventListener('click', function () { toggle(key); });
  return tr;
}

function depth(number) {
  return number.split('.').length - 1;
}

function indent(number) {
  var d = depth(number);
  return d ? (0.6 + d * 1.2) + 'rem' : null;
}

function hit(req, q) {
  if (!q) { return true; }
  var hay = [req.number, req.title, req.reason, req.note, req.category,
             req.group].join(' ');
  req.specs.forEach(function (s) {
    hay += ' ' + s.number + ' ' + s.text + ' ' + s.measure + ' ' + s.knowledge;
  });
  if (hay.toLowerCase().indexOf(q) !== -1) { return true; }
  return req.children.some(function (c) { return hit(c, q); });
}

function specVisible(spec) {
  if (filterBox.value === 'todo') { return !spec.verified; }
  if (filterBox.value === 'done') { return spec.verified; }
  return true;
}

// 同じグループが続く間はグループ行を 1 本だけ出す（手書きの HTML と同じ並び）
function appendRequirements(body, reqs, kind, q, docId, level) {
  var name = null;
  var key = null;
  reqs.forEach(function (req) {
    if (req.group) {
      if (req.group !== name) {
        name = req.group;
        key = 'G:' + docId + ':' + level + ':' + req.group;
        body.appendChild(
          foldRow(kind, 'req-group', { label: req.group, caret: caretFor(key) }, key)
        );
      }
      if (isClosed(key)) { return; }
    } else {
      name = null;
      key = null;
    }
    appendRequirement(body, req, kind, q, docId);
  });
}

// 手書きの HTML と同じ行の並び（要求 → 理由 → 説明 → 仕様グループ → 仕様）。
// 要求のキャレットが畳むのは **自分の詳細（理由・説明・仕様）だけ** 。
// 下位要求は自分のキャレットを持つので、全部畳めば要求だけの一覧になる。
function appendRequirement(body, req, kind, q, docId) {
  var key = 'R:' + docId + ':' + req.number;

  body.appendChild(foldRow(kind, 'requirement', {
    category: req.category,
    mark: '要求',
    caret: caretFor(key),
    id: kind === 'quality' ? 'QUA' + req.number.slice(1) : 'REQ' + req.number,
    body: req.title,
    indent: indent(req.number)
  }, key));

  if (!isClosed(key)) {
    body.appendChild(makeRow(kind, 'reason', {
      label: '理由', body: req.reason || '(未記入)'
    }));

    if (req.note) {
      body.appendChild(makeRow(kind, 'note', { label: '説明', body: req.note }));
    }

    var name = null;
    var groupKey = null;
    req.specs.forEach(function (s) {
      if (!specVisible(s)) { return; }
      if (s.group) {
        if (s.group !== name) {
          name = s.group;
          groupKey = 'S:' + docId + ':' + req.number + ':' + s.group;
          body.appendChild(foldRow(kind, 'spec-group',
            { label: s.group, caret: caretFor(groupKey) }, groupKey));
        }
        if (isClosed(groupKey)) { return; }
      } else {
        name = null;
        groupKey = null;
      }
      body.appendChild(makeRow(kind, 'spec', {
        check: s.verified ? '☑' : '□',
        id: s.number,
        body: s.text,
        indent: indent(req.number),
        measure: s.measure,
        knowledge: s.knowledge
      }));
    });
  }

  appendRequirements(body,
    req.children.filter(function (c) { return hit(c, q); }),
    kind, q, docId, req.number);
}

function appendCharacteristic(body, c) {
  body.appendChild(makeRow('quality', 'characteristic', {
    characteristic: c.name, sub: c.sub, label: '定義', body: c.definition
  }));
  body.appendChild(makeRow('quality', 'interpretation', {
    label: '解釈', body: c.interpretation
  }));
  body.appendChild(makeRow('quality', 'metrics', {
    label: 'メトリクス', body: c.metrics
  }));
  if (c.note) {
    body.appendChild(makeRow('quality', 'note', { label: '説明', body: c.note }));
  }
}

// 下位要求も 1 個として数える（表示件数を実体に合わせる）
function countReq(req, q) {
  return req.children.filter(function (c) { return hit(c, q); })
    .reduce(function (a, c) { return a + countReq(c, q); }, 1);
}

function renderDoc(doc, q) {
  var reqs = doc.requirements.filter(function (r) { return hit(r, q); });
  if (!reqs.length) { return null; }

  var key = 'D:' + doc.id;
  var section = el('section', 'doc');
  var header = el('header');
  header.appendChild(el('span', 'caret', caretFor(key)));
  header.appendChild(el('h2', null, doc.id + '. ' + doc.title));
  if (doc.maturity) { header.appendChild(el('span', 'badge', doc.maturity)); }
  header.appendChild(el('span', 'badge',
    doc.kind === 'quality' ? '品質要求' : '機能要求'));
  header.appendChild(el('span', 'badge', doc.source));
  header.addEventListener('click', function () { toggle(key); });
  section.appendChild(header);

  var count = reqs.reduce(function (a, r) { return a + countReq(r, q); }, 0);
  if (isClosed(key)) { return { section: section, count: count }; }

  var scroll = el('div', 'scroll');
  var table = el('table', 'usdm ' + doc.kind);
  var thead = el('thead');
  var head = el('tr');
  COLUMNS[doc.kind].forEach(function (c) { head.appendChild(el('th', null, c)); });
  thead.appendChild(head);
  table.appendChild(thead);

  var body = el('tbody');
  if (doc.kind === 'quality') {
    doc.characteristics.forEach(function (c) { appendCharacteristic(body, c); });
  }
  appendRequirements(body, reqs, doc.kind, q, doc.id, '');
  table.appendChild(body);
  scroll.appendChild(table);
  section.appendChild(scroll);
  return { section: section, count: count };
}

function render() {
  query = box.value.trim().toLowerCase();
  root.textContent = '';
  var shown = 0;
  ['functional', 'quality'].forEach(function (kind) {
    var rendered = [];
    DATA.filter(function (d) { return d.kind === kind; }).forEach(function (d) {
      var r = renderDoc(d, query);
      if (r) { shown += r.count; rendered.push(r.section); }
    });
    if (!rendered.length) { return; }
    root.appendChild(el('h2', 'section-title',
      kind === 'quality' ? '品質要求' : '機能要求'));
    rendered.forEach(function (s) { root.appendChild(s); });
  });
  if (!shown) { root.appendChild(el('p', 'empty', '一致する要求がありません。')); }
  counter.textContent = '該当する要求: ' + shown + ' 件';
}

// 「すべて閉じる」は要求の詳細だけを畳む。要求行・グループ行・文書は残るので、
// 要求の一覧（アウトライン）として読める。
function closeAllRequirements() {
  closed = {};
  DATA.forEach(function (doc) {
    (function walk(reqs) {
      reqs.forEach(function (r) {
        closed['R:' + doc.id + ':' + r.number] = true;
        walk(r.children);
      });
    })(doc.requirements);
  });
  render();
}

box.addEventListener('input', render);
filterBox.addEventListener('change', render);
document.getElementById('open').addEventListener('click', function () {
  closed = {};
  render();
});
document.getElementById('close').addEventListener('click', closeAllRequirements);
render();
"""


def render_html(documents: list[Document]) -> str:
    """要求を 1 枚の自己完結 HTML（要求一覧）にする。

    外部への参照（CDN・リモート画像・通信）を一切含めない。
    日時などの実行ごとに変わる値も埋め込まない（--check が壊れるため）。

    Args:
        documents: 表示する USDM 文書の一覧。

    Returns:
        HTML の全文。
    """
    payload = json.dumps(_to_payload(documents), ensure_ascii=False, indent=1)
    # <script> の中に閉じタグや < が生で出ないようにする
    payload = payload.replace("<", "\\u003c").replace("&", "\\u0026")
    total = sum(len(d.requirements) for d in documents)
    specs = sum(len(r.specs) for d in documents for r in d.requirements)
    functional = sum(1 for d in documents if d.kind == "functional")
    quality = len(documents) - functional

    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>要求一覧（USDM）</title>
<style>
{_STYLE}</style>
</head>
<body>
<div class="wrap">
<h1>要求一覧（USDM）</h1>
<p class="lead">機能要求 {functional} 枚 / 品質要求 {quality} 枚 ——
要求 {total} 個 / 仕様 {specs} 条。
理由は USDM の核心なので常に表示する。この HTML は
{html.escape('docs/usdm/src/*.html')} を束ねた <b>生成物</b> ——
要求を直したら再生成する（<code>build_usdm.py</code>）。</p>
<div class="tools">
<input type="search" id="q" placeholder="要求・理由・仕様・評価尺度を検索"
 autocomplete="off">
<div class="chips">
<select id="f" aria-label="仕様の絞り込み">
<option value="all">仕様: すべて</option>
<option value="todo">仕様: 未検証のみ</option>
<option value="done">仕様: 検証済みのみ</option>
</select>
<button type="button" id="open">すべて開く</button>
<button type="button" id="close">すべて閉じる</button>
<p class="count" id="count"></p>
</div>
</div>
<div id="docs"></div>
</div>
<script id="usdm-data" type="application/json">
{payload}
</script>
<script>
{_SCRIPT}</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    """コマンドとしての入口。終了コードは module docstring のとおり。"""
    parser = argparse.ArgumentParser(
        description="USDM の要求 HTML を検証し、要求一覧 1 枚を生成する"
    )
    parser.add_argument(
        "--source",
        nargs="+",
        default=["docs/usdm/src"],
        help="要求 HTML（S##-*.html / Q##-*.html）を探すディレクトリまたはファイル",
    )
    parser.add_argument(
        "--out", default="docs/usdm/index.html", help="生成する要求一覧のパス"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="生成せず、既存の要求一覧が最新かどうかだけを判定する",
    )
    args = parser.parse_args(argv)

    documents = collect(args.source)
    if not documents:
        print(
            "ERROR: 要求 HTML（S##-*.html / Q##-*.html）が見つかりません: "
            + ", ".join(args.source),
        )
        return 2

    violations = [v for doc in documents for v in doc.violations]
    if violations:
        for v in violations:
            print(f"NG: {v.source}:{v.line}: [{v.kind}] {v.message}")
        print(f"RESULT: {len(violations)} 件の USDM 違反（文書 {len(documents)} 枚）")
        return 1

    rendered = render_html(documents)
    out = Path(args.out)
    total = sum(len(d.requirements) for d in documents)

    if args.check:
        current = out.read_text(encoding="utf-8") if out.exists() else None
        if current != rendered:
            reason = "未生成" if current is None else "要求より古い"
            print(f"STALE: {out} が{reason}。build_usdm.py で再生成してください")
            return 1
        print(f"OK: {out} は最新（文書 {len(documents)} 枚 / 要求 {total} 個）")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rendered, encoding="utf-8")
    print(
        f"OK: {out} を生成（文書 {len(documents)} 枚 / "
        f"要求 {total} 個 / 違反 0 件）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
