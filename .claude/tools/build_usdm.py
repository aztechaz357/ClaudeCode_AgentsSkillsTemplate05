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
_NL = chr(10)
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


# 手書きの正（`docs/usdm/src/*.html`）と同じ見た目・同じ操作にするため、
# CSS と JS は共有ファイルを 1 か所から読む。要求一覧は自己完結にしたいので
# 参照ではなく埋め込む（`file://` で開けることを守る）。
_ASSETS = Path(__file__).resolve().parent.parent / "skills" / "usdm"

_COLUMNS = {
    "functional": ["カテゴリ名", "要求", "要求ID", "要求仕様"],
    "quality": [
        "品質特性", "品質副特性", "要求", "要求ID", "要求仕様",
        "評価尺度", "対応知識・技術",
    ],
}
_WIDTHS = {
    "functional": ["8rem", "5rem", "7rem", ""],
    "quality": ["8rem", "8rem", "5rem", "7rem", "", "12rem", "10rem"],
}


def _cell(css: str, text: str = "", indent: int = 0) -> str:
    """セル 1 つ。意味は class が持つ（位置ではない）。"""
    if not css and not text:
        return "<td></td>"
    attrs = f' class="{css}"' if css else ""
    style = f' style="padding-left:{0.6 + indent * 1.2:.1f}rem"' if indent else ""
    return f"<td{attrs}{style}>{html.escape(text)}</td>"


def _row(
    kind: str,
    cls: str,
    *,
    category: str = "",
    characteristic: str = "",
    sub: str = "",
    mark: str = "",
    label: str = "",
    check: str | None = None,
    ident: str = "",
    body: str = "",
    indent: int = 0,
    measure: str = "",
    knowledge: str = "",
) -> str:
    """行 1 つ。列の並びはテンプレート（`skills/usdm/template*.html`）と同じ。"""
    cells = []
    if kind == "quality":
        cells.append(_cell("characteristic", characteristic))
        cells.append(_cell("subcharacteristic", sub))
    else:
        cells.append(_cell("category", category))
    cells.append(_cell("check", check) if check is not None else _cell("kind", mark))
    cells.append(_cell("id", ident) if ident else _cell("kind", label))
    cells.append(_cell("body", body, indent))
    if kind == "quality":
        cells.append(_cell("measure", measure))
        cells.append(_cell("knowledge", knowledge))
    return f'<tr class="{cls}">' + "".join(cells) + "</tr>"


def _append_requirements(
    rows: list[str], requirements: list[Requirement], kind: str
) -> None:
    """同じ要求グループが続く間はグループ行を 1 本だけ出す。"""
    group = None
    for req in requirements:
        if req.group and req.group != group:
            group = req.group
            rows.append(_row(kind, "req-group", label=req.group))
        elif not req.group:
            group = None
        _append_requirement(rows, req, kind)


def _append_requirement(rows: list[str], req: Requirement, kind: str) -> None:
    """要求 → 理由 → 説明 → 仕様グループ → 仕様 → 下位要求 の順に並べる。"""
    depth = req.number.count(".")
    ident = ("QUA" + req.number[1:]) if kind == "quality" else ("REQ" + req.number)

    rows.append(_row(kind, "requirement", category=req.category, mark="要求",
                     ident=ident, body=req.title, indent=depth))
    rows.append(_row(kind, "reason", label="理由", body=req.reason or "(未記入)"))
    if req.note:
        rows.append(_row(kind, "note", label="説明", body=req.note))

    group = None
    for spec in req.specs:
        if spec.group and spec.group != group:
            group = spec.group
            rows.append(_row(kind, "spec-group", label=spec.group))
        elif not spec.group:
            group = None
        rows.append(_row(
            kind, "spec",
            check=_CHECKED if spec.verified else _UNCHECKED,
            ident=spec.number, body=spec.text, indent=depth,
            measure=spec.measure, knowledge=spec.knowledge,
        ))

    _append_requirements(rows, req.children, kind)


def render_document(doc: Document) -> str:
    """文書 1 本を、手書きの HTML と同じ表として描く。"""
    cols = "".join(
        (f'<col style="width:{w}">' if w else "<col>") for w in _WIDTHS[doc.kind]
    )
    head = "".join(f"<th>{html.escape(c)}</th>" for c in _COLUMNS[doc.kind])

    rows: list[str] = []
    for char in doc.characteristics:
        rows.append(_row(doc.kind, "characteristic", characteristic=char.name,
                         sub=char.sub, label="定義", body=char.definition))
        rows.append(_row(doc.kind, "interpretation", label="解釈",
                         body=char.interpretation))
        rows.append(_row(doc.kind, "metrics", label="メトリクス", body=char.metrics))
        if char.note:
            rows.append(_row(doc.kind, "note", label="説明", body=char.note))
    _append_requirements(rows, build_tree(doc.requirements), doc.kind)

    badges = []
    if doc.maturity:
        badges.append(f'<span class="badge">{html.escape(doc.maturity)}</span>')
    badges.append(
        '<span class="badge">'
        + ("品質要求" if doc.kind == "quality" else "機能要求")
        + "</span>"
    )
    badges.append(
        f'<span class="badge">{html.escape(doc.source.replace(chr(92), "/"))}</span>'
    )

    header = (
        f"<header><h2>{html.escape(doc.doc_id)}. {html.escape(doc.title)}</h2>"
        + "".join(badges)
        + "</header>"
    )
    return _NL.join([
        '<section class="doc">',
        header,
        '<div class="scroll">',
        f'<table class="usdm {doc.kind}">',
        f"<colgroup>{cols}</colgroup>",
        f"<thead><tr>{head}</tr></thead>",
        "<tbody>",
        *rows,
        "</tbody>",
        "</table>",
        "</div>",
        "</section>",
    ])


def render_html(documents: list[Document]) -> str:
    """要求を 1 枚の自己完結 HTML（要求一覧）にする。

    外部への参照（CDN・リモート画像・通信）を一切含めない。
    日時などの実行ごとに変わる値も埋め込まない（--check が壊れるため）。
    折りたたみ・絞り込み・検索は、手書きの 1 枚と同じ `usdm.js` が付ける。

    Args:
        documents: 表示する USDM 文書の一覧。

    Returns:
        HTML の全文。
    """
    css = (_ASSETS / "usdm.css").read_text(encoding="utf-8")
    script = (_ASSETS / "usdm.js").read_text(encoding="utf-8")

    sections: list[str] = []
    for kind, label in (("functional", "機能要求"), ("quality", "品質要求")):
        chosen = [d for d in documents if d.kind == kind]
        if not chosen:
            continue
        sections.append(f'<h2 class="section-title">{label}</h2>')
        sections.extend(render_document(d) for d in chosen)

    total = sum(len(d.requirements) for d in documents)
    specs = sum(len(r.specs) for d in documents for r in d.requirements)
    functional = sum(1 for d in documents if d.kind == "functional")
    quality = len(documents) - functional

    return _NL.join([
        "<!doctype html>",
        '<html lang="ja">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>要求一覧（USDM）</title>",
        "<style>",
        css + "</style>",
        "</head>",
        "<body>",
        '<div class="wrap">',
        "<h1>要求一覧（USDM）</h1>",
        f'<p class="lead">機能要求 {functional} 枚 / 品質要求 {quality} 枚 ——',
        f"要求 {total} 個 / 仕様 {specs} 条。",
        "理由は USDM の核心なので常に表示する。この HTML は",
        "docs/usdm/src/ の手書き HTML を束ねた <b>生成物</b> ——",
        "要求を直したら再生成する（<code>build_usdm.py</code>）。</p>",
        '<div id="docs">',
        *sections,
        "</div>",
        "</div>",
        "<script>",
        script + "</script>",
        "</body>",
        "</html>",
        "",
    ])


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
