"""実物のディレクトリ構成を読み、`docs/structure.md` を生成する。

手書きの構造スナップショットは **必ず実物とずれる** 。ずれた瞬間、
エージェントは嘘の地図を見てファイルを置き始める。だから構成は
手で書かず、実物から生成し、`--check` で古さを終了コードで落とす
（`build_usdm.py` と同じ考え方）。

出力に日時を埋め込まない。埋め込むと `--check` が常に STALE になる。

説明の付け方（任意）:
    `.claude/structure-notes.txt` に「相対パス <TAB> 説明」を並べると、
    ツリーの該当行に説明が付く。`#` で始まる行は無視する。
    説明は人が書く（構造の意図は実物からは読めないため）。

使い方（前置コマンドはプロファイルの
「.claude/tools/ の Python ツール実行」。例: uv run python）:
    <ツール実行コマンド> .claude/tools/build_structure.py
    <ツール実行コマンド> .claude/tools/build_structure.py --check
    <ツール実行コマンド> .claude/tools/build_structure.py --depth 4

終了コード:
    0 = 生成に成功（--check では最新）
    1 = --check で STALE（実物と文書が食い違っている）
    2 = 引数のエラー
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 探索から外すディレクトリ。プロファイルの「探索除外」と同じ考え方で、
# 生成物・依存・エディタの作業領域は構成の意味を持たない。
_EXCLUDE = {
    ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "node_modules", "dist", "build",
    ".steering", ".idea", ".DS_Store", ".uv-cache", "htmlcov", ".tox",
}
_OUT = Path("docs") / "structure.md"
_NOTES = Path(".claude") / "structure-notes.txt"
_NL = chr(10)
_HEADER = """\
# ディレクトリ構成（生成物）

> **このファイルは手で編集しない。** `.claude/tools/build_structure.py` が
> 実物のツリーから生成する。構成を変えたら再生成する（`--check` で古さを
> 検出できる）。説明は `.claude/structure-notes.txt` に書く。
>
> 層と依存の向きの正は `.claude/skills/layered-architecture/SKILL.md`、
> 文書の置き場所の正は `CLAUDE.md` の「ドキュメント構成」表。
"""


def load_notes(path: Path) -> dict[str, str]:
    """`相対パス <TAB> 説明` の対応表を読む。無ければ空。"""
    notes: dict[str, str] = {}
    if not path.is_file():
        return notes
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("\t")
        if not value:
            key, _, value = line.partition("  ")
        if value.strip():
            notes[key.strip().replace("\\", "/").rstrip("/")] = value.strip()
    return notes


def walk(root: Path, depth: int) -> list[tuple[int, Path, bool]]:
    """ツリーを深さ優先で並べる（ディレクトリが先、次に名前順）。

    Args:
        root: 起点。
        depth: 何階層まで下りるか（1 = 直下だけ）。

    Returns:
        `(深さ, パス, ディレクトリか)` の一覧。root 自身は含めない。
    """
    found: list[tuple[int, Path, bool]] = []

    def visit(current: Path, level: int) -> None:
        if level > depth:
            return
        try:
            entries = sorted(
                current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
            )
        except PermissionError:
            return
        for entry in entries:
            if entry.name in _EXCLUDE:
                continue
            is_dir = entry.is_dir()
            found.append((level, entry, is_dir))
            if is_dir:
                visit(entry, level + 1)

    visit(root, 1)
    return found


def render(root: Path, entries: list[tuple[int, Path, bool]], notes: dict[str, str]) -> str:
    """ツリーを Markdown の文書にする（日時は入れない）。"""
    lines = [f"{root.resolve().name}/"]
    for level, path, is_dir in entries:
        rel = path.relative_to(root).as_posix()
        name = path.name + ("/" if is_dir else "")
        note = notes.get(rel, "")
        indent = "  " * (level - 1)
        lines.append(f"{indent}{name}" + (f"  # {note}" if note else ""))

    body = [
        _HEADER,
        "```text",
        *lines,
        "```",
        "",
        "## 数",
        "",
        f"- ディレクトリ: {sum(1 for _, _, d in entries if d)} 個",
        f"- ファイル: {sum(1 for _, _, d in entries if not d)} 個",
        "",
    ]
    return _NL.join(body)


def main(argv: list[str] | None = None) -> int:
    """コマンドとして実行する。詳しくはモジュールの docstring を参照。"""
    parser = argparse.ArgumentParser(
        description="実物のディレクトリ構成から docs/structure.md を生成する"
    )
    parser.add_argument("root", nargs="?", default=".", help="リポジトリルート")
    parser.add_argument("--depth", type=int, default=3, help="下りる階層数（既定 3）")
    parser.add_argument(
        "--check", action="store_true", help="生成せず、古ければ 1 を返す"
    )
    args = parser.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"NG: ディレクトリがない（{root}）")
        return 2
    if args.depth < 1:
        print("NG: --depth は 1 以上")
        return 2

    out = root / _OUT
    if not args.check and not out.exists():
        # 生成物自身もツリーに載る。先に作っておかないと
        # 1 回目と 2 回目の出力が変わる（冪等でなくなる）。
        out.parent.mkdir(parents=True, exist_ok=True)
        out.touch()

    entries = walk(root, args.depth)
    notes = load_notes(root / _NOTES)
    body = render(root, entries, notes)

    if args.check:
        current = out.read_text(encoding="utf-8") if out.is_file() else ""
        if current == body:
            print(f"OK: {_OUT.as_posix()} は最新")
            return 0
        reason = "未生成" if not current else "実物と食い違っている"
        print(f"STALE: {_OUT.as_posix()} が{reason}（再生成が必要）")
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    dirs = sum(1 for _, _, d in entries if d)
    files = len(entries) - dirs
    print(
        f"OK: {_OUT.as_posix()} を生成"
        f"（ディレクトリ {dirs} 個 / ファイル {files} 個 / 深さ {args.depth}）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
