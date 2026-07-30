"""USDM 形式の要求を検証し、自己完結 HTML の要求ビューアを生成する。

記法の正は `.claude/skills/usdm/SKILL.md`。このツールは 2 つの仕事をする。

1. **機械検証** —— USDM の核心ルール（理由の必須性・仕様の導出関係）を
   終了コードで判定できる形に落とす。LLM の判断に頼らない
2. **生成** —— 要求ツリーを 1 枚の HTML にする。外部参照ゼロなので
   `file://` でそのまま開ける（ローカルサーバを要求しない）

検出する違反:

    missing-reason           理由が無い要求（USDM の核心ルール違反）
    no-spec                  仕様が 0 条の要求
    spec-number-mismatch     仕様番号の要求部分が親要求と違う
    duplicate-requirement    要求番号の重複
    duplicate-spec           仕様番号の重複
    slice-number-mismatch    ファイルの S## と最上位要求の REQ## が違う
    orphan-requirement       親要求が宣言されていない下位要求
    spec-without-requirement 要求の外に置かれた仕様

生成物に日時を埋め込まない。埋め込むと --check が常に STALE になる。

使い方（前置コマンドはプロファイルの
「.claude/tools/ の Python ツール実行」。例: uv run python）:
    <ツール実行コマンド> .claude/tools/build_usdm.py
    <ツール実行コマンド> .claude/tools/build_usdm.py --check
    <ツール実行コマンド> .claude/tools/build_usdm.py --source docs/slices --out docs/usdm/index.html

終了コード:
    0 = 生成に成功（--check では HTML が最新）
    1 = USDM 違反がある、または --check で STALE
    2 = 引数のエラー、または対象の USDM 文書が 0 件
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 記法の契約（`.claude/skills/usdm/SKILL.md` と一対一で対応させる）
_TITLE = re.compile(r"^#\s+(.+?)\s*$")
_MATURITY = re.compile(r"\*\*成熟度:\s*`([^`]+)`\*\*")
_REQ = re.compile(r"^###\s*【REQ([0-9]+(?:\.[0-9]+)*)】\s*(.+?)\s*$")
_REASON = re.compile(r"^-\s*\*\*理由\*\*\s*[:：]\s*(.+?)\s*$")
_SCOPE = re.compile(r"^-\s*\*\*範囲\*\*\s*[:：]\s*(.+?)\s*$")
_SPEC = re.compile(
    r"^-\s*\[([ xX])\]\s*`?<([0-9]+(?:\.[0-9]+)*-[0-9]+)>`?\s*(.+?)\s*$"
)
_SLICE_FILE = re.compile(r"^(S[0-9]+)-.+\.md$")
# 見出しの「S02.」は表示側が前置するので落とす（重複表示の防止）
_TITLE_PREFIX = re.compile(r"^S[0-9]+\s*[.．]\s*")


@dataclass
class Spec:
    """仕様 1 条。番号は `<要求番号-連番>` の中身、verified は `[x]` かどうか。"""

    number: str
    text: str
    verified: bool
    line: int


@dataclass
class Requirement:
    """要求 1 個。階層は number のドットだけが正（見出しレベルは使わない）。"""

    number: str
    title: str
    line: int
    reason: str = ""
    scope: str = ""
    specs: list[Spec] = field(default_factory=list)
    children: list["Requirement"] = field(default_factory=list)


@dataclass
class Violation:
    """USDM 記法の違反 1 件。kind は機械判定用の種別。"""

    kind: str
    message: str
    line: int
    source: str = ""


@dataclass
class Document:
    """USDM 文書 1 本（スライス文書または厚い経路の要求仕様書）。"""

    slice_id: str
    title: str
    maturity: str
    requirements: list[Requirement]
    violations: list[Violation]
    source: str = ""


def parse_document(text: str, slice_id: str, source: str = "") -> Document:
    """USDM 記法の Markdown を構造として取り出し、記法違反を集める。

    Args:
        text: Markdown の全文。
        slice_id: ファイル名から取ったスライス番号（例: `S02`）。
        source: 表示用のパス（違反の出力に添える）。

    Returns:
        要求の一覧と違反の一覧を持つ Document。
    """
    title = ""
    maturity = ""
    requirements: list[Requirement] = []
    violations: list[Violation] = []
    current: Requirement | None = None

    for lineno, line in enumerate(text.splitlines(), start=1):
        if not title:
            matched = _TITLE.match(line)
            if matched:
                title = _TITLE_PREFIX.sub("", matched.group(1))
        if not maturity:
            matched = _MATURITY.search(line)
            if matched:
                maturity = matched.group(1)

        matched = _REQ.match(line)
        if matched:
            current = Requirement(
                number=matched.group(1), title=matched.group(2), line=lineno
            )
            requirements.append(current)
            continue

        matched = _SPEC.match(line)
        if matched:
            spec = Spec(
                number=matched.group(2),
                text=matched.group(3),
                verified=matched.group(1).lower() == "x",
                line=lineno,
            )
            if current is None:
                violations.append(
                    Violation(
                        "spec-without-requirement",
                        f"仕様 <{spec.number}> が要求の外に置かれている",
                        lineno,
                        source,
                    )
                )
            else:
                current.specs.append(spec)
            continue

        if current is None:
            continue

        matched = _REASON.match(line)
        if matched and not current.reason:
            current.reason = matched.group(1)
            continue

        matched = _SCOPE.match(line)
        if matched and not current.scope:
            current.scope = matched.group(1)

    violations.extend(_validate(requirements, slice_id, source))
    return Document(slice_id, title, maturity, requirements, violations, source)


def _validate(
    requirements: list[Requirement], slice_id: str, source: str
) -> list[Violation]:
    """要求の一覧を USDM のルールに照らし、違反を列挙する。"""
    violations: list[Violation] = []
    declared = {r.number for r in requirements}
    seen_requirements: set[str] = set()
    seen_specs: dict[str, int] = {}
    slice_number = slice_id.lstrip("Ss").lstrip("0") or "0"

    for req in requirements:
        if req.number in seen_requirements:
            violations.append(
                Violation(
                    "duplicate-requirement",
                    f"要求番号 REQ{req.number} が重複している",
                    req.line,
                    source,
                )
            )
        seen_requirements.add(req.number)

        if not req.reason:
            violations.append(
                Violation(
                    "missing-reason",
                    f"REQ{req.number} に理由がない（USDM では理由は必須）",
                    req.line,
                    source,
                )
            )

        if not req.specs:
            violations.append(
                Violation(
                    "no-spec",
                    f"REQ{req.number} に仕様が 1 条もない",
                    req.line,
                    source,
                )
            )

        parent = req.number.rpartition(".")[0]
        if parent and parent not in declared:
            violations.append(
                Violation(
                    "orphan-requirement",
                    f"REQ{req.number} の親 REQ{parent} が宣言されていない",
                    req.line,
                    source,
                )
            )

        if not parent and req.number != slice_number:
            violations.append(
                Violation(
                    "slice-number-mismatch",
                    f"{slice_id} の最上位要求が REQ{req.number}"
                    f"（REQ{slice_number} であるべき）",
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
                        f"仕様 <{spec.number}> が REQ{req.number} の配下にある"
                        f"（<{req.number}-n> であるべき）",
                        spec.line,
                        source,
                    )
                )
            if spec.number in seen_specs:
                violations.append(
                    Violation(
                        "duplicate-spec",
                        f"仕様番号 <{spec.number}> が重複している"
                        f"（{seen_specs[spec.number]} 行目と同じ）",
                        spec.line,
                        source,
                    )
                )
            else:
                seen_specs[spec.number] = spec.line

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
    """指定パス配下の `S##-*.md` を読み、Document の一覧を返す。

    Args:
        sources: 探索するディレクトリまたはファイルのパス。

    Returns:
        スライス番号で並べた Document の一覧（対象が無ければ空）。
    """
    paths: list[Path] = []
    for raw in sources:
        path = Path(raw)
        if path.is_file() and _SLICE_FILE.match(path.name):
            paths.append(path)
        elif path.is_dir():
            paths.extend(p for p in path.glob("*.md") if _SLICE_FILE.match(p.name))

    documents: list[Document] = []
    for path in sorted(set(paths), key=lambda p: (p.name, str(p))):
        matched = _SLICE_FILE.match(path.name)
        assert matched is not None  # glob 側で保証済み
        text = path.read_text(encoding="utf-8")
        documents.append(
            parse_document(text, slice_id=matched.group(1), source=str(path))
        )
    return documents


def _to_payload(documents: list[Document]) -> list[dict]:
    """HTML に埋め込む JSON 構造へ変換する（要求は木の形にする）。"""

    def node(req: Requirement) -> dict:
        return {
            "number": req.number,
            "title": req.title,
            "reason": req.reason,
            "scope": req.scope,
            "specs": [
                {"number": s.number, "text": s.text, "verified": s.verified}
                for s in req.specs
            ],
            "children": [node(c) for c in req.children],
        }

    return [
        {
            "slice": doc.slice_id,
            "title": doc.title,
            "maturity": doc.maturity,
            "source": doc.source.replace("\\", "/"),
            "requirements": [node(r) for r in build_tree(doc.requirements)],
        }
        for doc in documents
    ]


_STYLE = """\
:root { color-scheme: light dark;
  --bg:#fbfbfd; --fg:#1a1a1f; --muted:#5d5d6b; --line:#e2e2ea;
  --card:#ffffff; --accent:#3a5ccc; --ok:#1f7a4d; --todo:#8a6d1f; }
@media (prefers-color-scheme: dark) { :root {
  --bg:#16161a; --fg:#ececf2; --muted:#a0a0b0; --line:#2e2e38;
  --card:#1e1e24; --accent:#8fa6f5; --ok:#5fd39b; --todo:#e0bf6a; } }
* { box-sizing: border-box; }
body { margin:0; padding:2rem 1.25rem 4rem; background:var(--bg); color:var(--fg);
  font-family: "Segoe UI", "Hiragino Kaku Gothic ProN", "Yu Gothic UI", Meiryo, sans-serif;
  line-height:1.75; }
.wrap { max-width: 60rem; margin: 0 auto; }
h1 { font-size:1.5rem; margin:0 0 .25rem; }
.lead { color:var(--muted); margin:0 0 1.5rem; font-size:.9rem; }
.tools { position:sticky; top:0; background:var(--bg); padding:.75rem 0 1rem; z-index:2; }
input[type=search] { width:100%; padding:.6rem .8rem; font-size:1rem; color:var(--fg);
  background:var(--card); border:1px solid var(--line); border-radius:.5rem; }
.count { color:var(--muted); font-size:.85rem; margin-top:.4rem; }
.doc { margin: 0 0 2rem; }
.doc > header { display:flex; flex-wrap:wrap; gap:.5rem; align-items:baseline;
  border-bottom:1px solid var(--line); padding-bottom:.4rem; margin-bottom:.75rem; }
.doc h2 { font-size:1.1rem; margin:0; }
.badge { font-size:.75rem; padding:.1rem .5rem; border-radius:1rem;
  border:1px solid var(--line); color:var(--muted); white-space:nowrap; }
.req { background:var(--card); border:1px solid var(--line); border-radius:.6rem;
  padding:.9rem 1rem; margin:.75rem 0; }
.req .num { font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
  color:var(--accent); font-weight:600; margin-right:.4rem; }
.req h3 { font-size:1rem; margin:0 0 .4rem; font-weight:600; }
.reason { margin:0 0 .3rem; font-size:.92rem; }
.reason b, .scope b { color:var(--muted); font-weight:600; }
.scope { margin:0 0 .3rem; font-size:.88rem; color:var(--muted); }
details { margin-top:.5rem; }
summary { cursor:pointer; font-size:.85rem; color:var(--muted); }
ul.specs { list-style:none; margin:.5rem 0 0; padding:0; }
ul.specs li { display:flex; gap:.5rem; align-items:flex-start; padding:.25rem 0;
  font-size:.93rem; overflow-wrap:anywhere; }
.spec-num { font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
  color:var(--muted); white-space:nowrap; }
.state { white-space:nowrap; font-size:.8rem; }
.state.done { color:var(--ok); }
.state.todo { color:var(--todo); }
.children { margin-left:1rem; border-left:2px solid var(--line); padding-left:.75rem; }
.empty { color:var(--muted); padding:2rem 0; }
"""

_SCRIPT = """\
var DATA = JSON.parse(document.getElementById('usdm-data').textContent);
var root = document.getElementById('docs');
var counter = document.getElementById('count');
var box = document.getElementById('q');

function el(tag, cls, text) {
  var n = document.createElement(tag);
  if (cls) { n.className = cls; }
  if (text !== undefined && text !== null) { n.textContent = text; }
  return n;
}

function hit(req, q) {
  if (!q) { return true; }
  var hay = [req.number, req.title, req.reason, req.scope].join(' ');
  req.specs.forEach(function (s) { hay += ' ' + s.number + ' ' + s.text; });
  if (hay.toLowerCase().indexOf(q) !== -1) { return true; }
  return req.children.some(function (c) { return hit(c, q); });
}

function renderReq(req, q) {
  var card = el('article', 'req');
  var head = el('h3');
  head.appendChild(el('span', 'num', 'REQ' + req.number));
  head.appendChild(document.createTextNode(req.title));
  card.appendChild(head);

  var reason = el('p', 'reason');
  reason.appendChild(el('b', null, '理由: '));
  reason.appendChild(document.createTextNode(req.reason || '(未記入)'));
  card.appendChild(reason);

  if (req.scope) {
    var scope = el('p', 'scope');
    scope.appendChild(el('b', null, '範囲: '));
    scope.appendChild(document.createTextNode(req.scope));
    card.appendChild(scope);
  }

  if (req.specs.length) {
    var done = req.specs.filter(function (s) { return s.verified; }).length;
    var box2 = el('details');
    box2.open = true;
    box2.appendChild(el('summary', null,
      '仕様 ' + req.specs.length + ' 条（検証済み ' + done + '）'));
    var list = el('ul', 'specs');
    req.specs.forEach(function (s) {
      var li = el('li');
      li.appendChild(el('span', 'state ' + (s.verified ? 'done' : 'todo'),
        s.verified ? '検証済' : '未検証'));
      li.appendChild(el('span', 'spec-num', '<' + s.number + '>'));
      li.appendChild(el('span', null, s.text));
      list.appendChild(li);
    });
    box2.appendChild(list);
    card.appendChild(box2);
  }

  var kids = req.children.filter(function (c) { return hit(c, q); });
  if (kids.length) {
    var wrap = el('div', 'children');
    kids.forEach(function (c) { wrap.appendChild(renderReq(c, q)); });
    card.appendChild(wrap);
  }
  return card;
}

function render() {
  var q = box.value.trim().toLowerCase();
  root.textContent = '';
  var shown = 0;
  DATA.forEach(function (doc) {
    var reqs = doc.requirements.filter(function (r) { return hit(r, q); });
    if (!reqs.length) { return; }
    var section = el('section', 'doc');
    var header = el('header');
    header.appendChild(el('h2', null, doc.slice + '. ' + doc.title));
    if (doc.maturity) { header.appendChild(el('span', 'badge', doc.maturity)); }
    header.appendChild(el('span', 'badge', doc.source));
    section.appendChild(header);
    reqs.forEach(function (r) { shown += 1; section.appendChild(renderReq(r, q)); });
    root.appendChild(section);
  });
  if (!shown) { root.appendChild(el('p', 'empty', '一致する要求がありません。')); }
  counter.textContent = '表示中の要求: ' + shown + ' 件';
}

box.addEventListener('input', render);
render();
"""


def render_html(documents: list[Document]) -> str:
    """要求ツリーを 1 枚の自己完結 HTML にする。

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

    return f"""<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>要求ビューア（USDM）</title>
<style>
{_STYLE}</style>
</head>
<body>
<div class="wrap">
<h1>要求ビューア（USDM）</h1>
<p class="lead">要求 {total} 個 / 仕様 {specs} 条。
理由は USDM の核心なので常に表示する。この HTML は生成物 ——
要求を直したら再生成する（<code>build_usdm.py</code>）。</p>
<div class="tools">
<input type="search" id="q" placeholder="要求・理由・仕様を検索" autocomplete="off">
<p class="count" id="count"></p>
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
        description="USDM の要求を検証し、自己完結 HTML のビューアを生成する"
    )
    parser.add_argument(
        "--source",
        nargs="+",
        default=["docs/slices", "docs/requirements"],
        help="USDM 文書を探すディレクトリまたはファイル",
    )
    parser.add_argument(
        "--out", default="docs/usdm/index.html", help="生成する HTML のパス"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="生成せず、既存の HTML が最新かどうかだけを判定する",
    )
    args = parser.parse_args(argv)

    documents = collect(args.source)
    if not documents:
        print(
            "ERROR: USDM 文書（S##-*.md）が見つかりません: "
            + ", ".join(args.source),
        )
        return 2

    violations = [v for doc in documents for v in doc.violations]
    if violations:
        for v in violations:
            print(f"NG: {v.source}:{v.line}: [{v.kind}] {v.message}")
        print(f"RESULT: {len(violations)} 件の USDM 違反（文書 {len(documents)} 本）")
        return 1

    html = render_html(documents)
    out = Path(args.out)

    if args.check:
        current = out.read_text(encoding="utf-8") if out.exists() else None
        if current != html:
            reason = "未生成" if current is None else "要求より古い"
            print(f"STALE: {out} が{reason}。build_usdm.py で再生成してください")
            return 1
        print(f"OK: {out} は最新（文書 {len(documents)} 本 / 要求 {sum(len(d.requirements) for d in documents)} 個）")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(
        f"OK: {out} を生成（文書 {len(documents)} 本 / "
        f"要求 {sum(len(d.requirements) for d in documents)} 個 / 違反 0 件）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
