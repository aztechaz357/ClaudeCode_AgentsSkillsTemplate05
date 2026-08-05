"""開発の現在地を 1 画面にまとめた `docs/status.html` を生成する。

**エージェントとスキルに任せると、ユーザーが大枠を見失う。**
このツールはその対策で、会話を追わなくても次の 5 つが 1 枚で読める状態を作る。

    1. ゴールと完走の定義（何ができたら終わりか）
    2. 進捗（スライスごとの成熟度と、全体の到達度）
    3. 7 点セットの充足マトリクス（どの成果物が欠けているか）
    4. 負債（未返却の件数と痛み 高 の件数）
    5. 直近の作業（コミットと、`.steering/` に残ったレポート）

読む元は `docs/backlog.md`（進捗の正）と実物のファイル。
このツールは何も書き換えず、集めて描くだけ。

生成物は外部参照ゼロの自己完結 HTML（`file://` でそのまま開ける）。

使い方（前置コマンドはプロファイルの
「.claude/tools/ の Python ツール実行」。例: uv run python）:
    <ツール実行コマンド> .claude/tools/build_status.py
    <ツール実行コマンド> .claude/tools/build_status.py --out docs/status.html

終了コード:
    0 = 生成に成功
    2 = docs/backlog.md が無い、または引数のエラー
"""

from __future__ import annotations

import argparse
import html
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_deliverables

_NL = chr(10)
_OUT = Path("docs") / "status.html"
_FIELD = re.compile(r"^-\s+\*\*(?P<name>[^*]+)\*\*\s*[:：]\s*(?P<value>.+)$")
_DEBT_ROW = re.compile(r"^\|\s*(D[0-9]+)\s*\|(.*)\|\s*$")
_LEVELS = ("L0 未着手", "L1 動く", "L2 固い", "L3 整った")
# 層と同じ色体系（`writing-conventions/guides/diagrams.md` の見た目の規約）
_STYLE = """\
:root{color-scheme:light dark;--bg:#fbfbfd;--fg:#1a1a1f;--muted:#5d5d6b;
 --line:#c9c9d4;--card:#fff;--head:#eceffb;--accent:#3a5ccc;--ok:#1f7a4d;
 --todo:#8a6d1f;--bad:#b3261e;--bar:#e3e6f2}
@media (prefers-color-scheme:dark){:root{--bg:#16161a;--fg:#ececf2;--muted:#a0a0b0;
 --line:#3a3a46;--card:#1e1e24;--head:#252a3d;--accent:#8fa6f5;--ok:#5fd39b;
 --todo:#e0bf6a;--bad:#f2857c;--bar:#2b3048}}
:root[data-theme="dark"]{--bg:#16161a;--fg:#ececf2;--muted:#a0a0b0;--line:#3a3a46;
 --card:#1e1e24;--head:#252a3d;--accent:#8fa6f5;--ok:#5fd39b;--todo:#e0bf6a;
 --bad:#f2857c;--bar:#2b3048}
*{box-sizing:border-box}
body{margin:0;padding:2rem 1.25rem 4rem;background:var(--bg);color:var(--fg);
 font-family:"Segoe UI","Hiragino Kaku Gothic ProN","Yu Gothic UI",Meiryo,sans-serif;
 line-height:1.7}
.wrap{max-width:72rem;margin:0 auto}
h1{font-size:1.3rem;margin:0 0 .2rem}
h2{font-size:1rem;margin:2rem 0 .6rem;padding-bottom:.25rem;
 border-bottom:2px solid var(--line)}
.goal{font-size:1.05rem;margin:.2rem 0 .1rem}
.sub{color:var(--muted);font-size:.85rem;margin:0 0 1rem}
.cards{display:flex;flex-wrap:wrap;gap:.75rem;margin:1rem 0}
.card{flex:1 1 11rem;background:var(--card);border:1px solid var(--line);
 border-radius:.6rem;padding:.7rem .9rem}
.card .k{color:var(--muted);font-size:.78rem}
.card .v{font-size:1.35rem;font-weight:700}
.bar{display:flex;height:.7rem;border-radius:.35rem;overflow:hidden;
 background:var(--bar);margin:.5rem 0 .2rem}
.bar span{display:block}
.legend{color:var(--muted);font-size:.78rem}
table{border-collapse:collapse;width:100%;background:var(--card);font-size:.88rem}
th,td{border:1px solid var(--line);padding:.35rem .6rem;text-align:left;
 vertical-align:top}
thead th{background:var(--head);white-space:nowrap;font-size:.82rem}
td.id{white-space:nowrap;color:var(--accent);font-weight:600}
td.mark{text-align:center;width:3.2rem}
.scroll{overflow-x:auto}
.ok{color:var(--ok)}.todo{color:var(--todo)}.bad{color:var(--bad);font-weight:700}
.muted{color:var(--muted)}
ul.log{margin:.3rem 0;padding-left:1.2rem;font-size:.85rem}
ul.log li{margin:.1rem 0}
code{font-family:ui-monospace,Consolas,"Cascadia Mono",monospace;font-size:.85em}
"""


def parse_fields(text: str) -> dict[str, str]:
    """「現在地」節の `- **名前**: 値` を辞書にする。"""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        matched = _FIELD.match(line.strip())
        if matched:
            fields.setdefault(
                matched.group("name").strip(),
                matched.group("value").strip().strip("`"),
            )
    return fields


def parse_debts(text: str) -> list[dict[str, str]]:
    """負債表の行を読む（`D##` で始まる行だけ）。"""
    debts: list[dict[str, str]] = []
    for line in text.splitlines():
        matched = _DEBT_ROW.match(line.strip())
        if not matched:
            continue
        cells = [c.strip() for c in matched.group(2).split("|")]
        if len(cells) < 5:
            continue
        debts.append({
            "id": matched.group(1),
            "body": cells[0],
            "from": cells[1],
            "pain": cells[2],
            "when": cells[3],
            "state": cells[4],
        })
    return debts


def recent_commits(root: Path, count: int = 8) -> list[str]:
    """直近のコミット。git が無い環境では空を返す（落とさない）。"""
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "log", f"-{count}", "--oneline", "--no-decorate"],
            capture_output=True, text=True, encoding="utf-8", timeout=10, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if done.returncode != 0 or not done.stdout:
        return []
    return [line for line in done.stdout.splitlines() if line.strip()]


def recent_reports(root: Path, count: int = 8) -> list[str]:
    """`.steering/` に残った役割エージェントのレポート（新しい順）。"""
    steering = root / ".steering"
    if not steering.is_dir():
        return []
    found = sorted(
        steering.glob("*/reports/*.md"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return [p.relative_to(root).as_posix() for p in found[:count]]


def _bar(counts: dict[int, int], total: int) -> str:
    """成熟度の到達度を 1 本の帯で描く。"""
    if not total:
        return ""
    colors = {3: "var(--ok)", 2: "#4c8bf5", 1: "var(--todo)", 0: "var(--bar)"}
    parts = []
    for level in (3, 2, 1, 0):
        width = counts.get(level, 0) * 100 / total
        if width:
            parts.append(
                f'<span style="width:{width:.1f}%;background:{colors[level]}"></span>'
            )
    return '<div class="bar">' + "".join(parts) + "</div>"


def render(
    root: Path,
    fields: dict[str, str],
    results: list[check_deliverables.Result],
    debts: list[dict[str, str]],
) -> str:
    """1 画面の HTML を組み立てる（外部参照ゼロ）。"""
    esc = html.escape
    total = len(results)
    counts: dict[int, int] = {}
    for result in results:
        counts[result.maturity] = counts.get(result.maturity, 0) + 1

    open_debts = [d for d in debts if not d["state"].startswith("済")]
    high = [d for d in open_debts if d["pain"] == "高"]
    started = [r for r in results if r.maturity >= 1]
    complete = [r for r in started if r.ok]

    cards = [
        ("スライス", f"{total} 本", "、".join(
            f"{_LEVELS[level]} {counts.get(level, 0)}" for level in (3, 2, 1, 0)
            if counts.get(level, 0)
        ) or "なし"),
        ("7 点セット", f"{len(complete)}/{len(started)}",
         "着手済みのうち、そろっているスライス"),
        ("負債", f"未返却 {len(open_debts)} 件", f"痛み 高 {len(high)} 件"),
        ("骨組み", esc(fields.get("骨組み", "不明")), "通っていなければ他のことをしない"),
    ]
    card_html = "".join(
        f'<div class="card"><div class="k">{esc(k)}</div>'
        f'<div class="v">{v}</div><div class="k">{esc(note)}</div></div>'
        for k, v, note in cards
    )

    head = "".join(
        f"<th>{esc(name)}</th>" for name in ("S##", "成熟度", *check_deliverables.ITEMS)
    )
    rows = []
    for result in results:
        marks = []
        for name in check_deliverables.ITEMS:
            if result.maturity < 1:
                marks.append('<td class="mark muted">—</td>')
            elif result.items.get(name):
                marks.append('<td class="mark ok">✅</td>')
            else:
                marks.append('<td class="mark bad">⬜</td>')
        rows.append(
            f'<tr><td class="id">{esc(result.ident)}</td>'
            f"<td>{esc(_LEVELS[result.maturity])}</td>" + "".join(marks) + "</tr>"
        )

    debt_rows = "".join(
        f'<tr><td class="id">{esc(d["id"])}</td><td>{esc(d["body"])}</td>'
        f'<td>{esc(d["from"])}</td>'
        f'<td class="{"bad" if d["pain"] == "高" else ""}">{esc(d["pain"])}</td>'
        f'<td>{esc(d["when"])}</td></tr>'
        for d in open_debts
    ) or '<tr><td colspan="5" class="muted">未返却の負債はない</td></tr>'

    commits = recent_commits(root)
    reports = recent_reports(root)
    log_html = "".join(f"<li><code>{esc(line)}</code></li>" for line in commits)
    report_html = "".join(f"<li><code>{esc(line)}</code></li>" for line in reports)

    return _NL.join([
        '<!doctype html>',
        '<html lang="ja"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>開発の現在地</title>",
        f"<style>{_STYLE}</style>",
        "</head><body><div class=\"wrap\">",
        "<h1>開発の現在地</h1>",
        f'<p class="goal">{esc(fields.get("ゴール", "（未設定）"))}</p>',
        f'<p class="sub">完走の定義: {esc(fields.get("完走の定義", "（未設定）"))}<br>'
        f'いま着手中: <strong>{esc(fields.get("いま着手中", "なし"))}</strong>'
        f' ／ 次の一手: {esc(fields.get("次の一手", "（未設定）"))}</p>',
        f'<div class="cards">{card_html}</div>',
        _bar(counts, total),
        '<p class="legend">緑 = L3 整った ／ 青 = L2 固い ／ 黄 = L1 動く ／ 灰 = L0 未着手</p>',
        "<h2>スライスと 7 点セットの充足</h2>",
        '<div class="scroll"><table>',
        f"<thead><tr>{head}</tr></thead><tbody>",
        *rows,
        "</tbody></table></div>",
        '<p class="legend">⬜ はまだ無い成果物。'
        "実装コードと単体テストの線は要求一覧（USDM のトレース表）が見る。</p>",
        "<h2>負債（未返却）</h2>",
        '<div class="scroll"><table>',
        "<thead><tr><th>D##</th><th>内容</th><th>出所</th><th>痛み</th>"
        "<th>返す条件</th></tr></thead><tbody>",
        debt_rows,
        "</tbody></table></div>",
        "<h2>直近の作業</h2>",
        "<p class=\"legend\">コミット（新しい順）</p>",
        f'<ul class="log">{log_html or "<li class=\"muted\">なし</li>"}</ul>',
        "<p class=\"legend\">役割エージェントのレポート（新しい順）</p>",
        f'<ul class="log">{report_html or "<li class=\"muted\">なし</li>"}</ul>',
        "</div></body></html>",
    ])


def main(argv: list[str] | None = None) -> int:
    """コマンドとして実行する。詳しくはモジュールの docstring を参照。"""
    parser = argparse.ArgumentParser(description="開発の現在地を 1 画面にまとめる")
    parser.add_argument("root", nargs="?", default=".", help="リポジトリルート")
    parser.add_argument("--out", default="", help="出力先（既定 docs/status.html）")
    args = parser.parse_args(argv)

    root = Path(args.root)
    backlog = root / "docs" / "backlog.md"
    if not backlog.is_file():
        print(f"NG: docs/backlog.md がない（{backlog}）")
        return 2

    text = backlog.read_text(encoding="utf-8")
    manual_path = root / "docs" / "manual.md"
    manual = manual_path.read_text(encoding="utf-8") if manual_path.is_file() else ""
    results = [
        check_deliverables.check_slice(root, item, manual)
        for item in check_deliverables.parse_backlog(text)
    ]

    out = root / (args.out or _OUT)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        render(root, parse_fields(text), results, parse_debts(text)), encoding="utf-8"
    )
    started = [r for r in results if r.maturity >= 1]
    print(
        f"OK: {out.as_posix()} を生成"
        f"（スライス {len(results)} 本 / 着手済み {len(started)} 本）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
