"""実装（Python の AST）から UML を逆生成する。

規約の正は `.claude/skills/architecture-drift/SKILL.md`、
設計書側の図の正は `.claude/skills/functional-design/SKILL.md`。

**設計書の図は「こうしたい」** で、実装がそのとおりとは限らない。
人は絵で理解するので、乖離も絵で見せるのが最も速い。このツールは
実装側の図を機械的に起こし、設計書の図と目で突き合わせられるようにする。

対応する図（設計書が持つ 4 種のうち 3 種）:

    class    … クラス図（`classDiagram`）。構造・継承・保持
    sequence … シーケンス図（`sequenceDiagram`）。呼び出し関係のみ
    flow     … `build_arch.py` が担当（層と依存の flowchart）
    state    … **実装から復元できない**（下記）

**状態遷移図は起こさない。** 任意のコードから状態機械を一般に復元することは
できず、それらしい図を出すと「実装と一致している」という誤った確信を与える。
できないことをできるふりにしない（絶対ルール 7）。
代わりに、設計書の図に書いた状態名が実装の列挙型・定数に存在するかを
人が確かめる（`architecture-drift` の「名前の対応」）。

**実装より豪華な図を出さない。** 非公開メソッド（`_` 始まり）や
型注釈の無い属性は落とす —— 推測で足した要素は、設計書側の欠落として
誤検出され、乖離の検出が逆向きに壊れる。

対応言語は Python（`.py`）のみ。他言語では「未対応」として扱う。

使い方（前置コマンドはプロファイルの
「.claude/tools/ の Python ツール実行」。例: uv run python）:
    <ツール実行コマンド> .claude/tools/build_uml.py <ソースルート> --kind class
    <ツール実行コマンド> .claude/tools/build_uml.py <ソースルート> --kind sequence
    <ツール実行コマンド> .claude/tools/build_uml.py <ソースルート> --kind class --out docs/uml-actual.md

終了コード:
    0 = 生成できた
    2 = ソースルートが無い・`.py` が 1 つも無い・state を要求された・引数のエラー
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

KINDS = ("class", "sequence", "state")


@dataclass
class ClassInfo:
    """クラス 1 つ。

    Attributes:
        name: クラス名。
        module: 層を含むモジュールパス（`domain.reader`）。設計書と同じ id 規約。
        bases: 直接の基底クラス名（同一リポジトリ内のものだけが図で線になる）。
        methods: 公開メソッド名（`_` 始まりと dunder は除く）。
        attributes: 型注釈のある属性だけ（名前 → 型）。
    """

    name: str
    module: str
    bases: list[str] = field(default_factory=list)
    methods: list[str] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class Call:
    """呼び出し 1 本（シーケンス図の 1 本の矢印）。"""

    module: str
    caller: str
    callee: str


def _name_of(node: ast.expr) -> str:
    """式から名前を取り出す（`a.b.c` は `a.b.c`）。取れなければ空。"""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _name_of(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _annotation(node: ast.expr | None) -> str:
    """型注釈を短い文字列にする。無ければ空。"""
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except Exception:  # noqa: BLE001 - 版差で unparse が無い場合に落とさない
        return _name_of(node)


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def parse_classes(source: str, module: str) -> list[ClassInfo]:
    """1 ファイルの中身からクラスを読み取る。

    Args:
        source: `.py` の全文。
        module: 層を含むモジュールパス。

    Returns:
        現れた順のクラス。構文エラーのファイルは空
        （落とさない —— 1 つ壊れていても他の図は出せたほうがよい）。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    found: list[ClassInfo] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        info = ClassInfo(
            name=node.name,
            module=module,
            bases=[name for name in (_name_of(b) for b in node.bases) if name],
        )
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if _is_public(item.name):
                    info.methods.append(item.name)
            elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                if _is_public(item.target.id):
                    info.attributes[item.target.id] = _annotation(item.annotation)
        # `__init__` の中の `self.x: T = ...` も属性として拾う。
        # 注釈が無いものは拾わない（推測で図を膨らませない）
        for inner in ast.walk(node):
            if not isinstance(inner, ast.AnnAssign):
                continue
            target = inner.target
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                and _is_public(target.attr)
            ):
                info.attributes.setdefault(target.attr, _annotation(inner.annotation))
        found.append(info)
    return found


def parse_calls(source: str, module: str) -> list[Call]:
    """メソッド・関数の中の呼び出しを読み取る。

    Args:
        source: `.py` の全文。
        module: 層を含むモジュールパス。

    Returns:
        `<クラス.メソッド> → <呼び先>` の一覧。
        呼び先は書かれたとおりの名前（`self.reader.read`）。
        **解決を試みない** —— 推測した解決先は実装に無い矢印を生む。
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    calls: list[Call] = []

    def scan(func: ast.AST, caller: str) -> None:
        for node in ast.walk(func):
            if isinstance(node, ast.Call):
                callee = _name_of(node.func)
                if callee:
                    calls.append(Call(module, caller, callee))

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    scan(item, f"{node.name}.{item.name}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            parents = [
                parent
                for parent in ast.walk(tree)
                if isinstance(parent, ast.ClassDef) and node in parent.body
            ]
            if not parents:
                scan(node, node.name)
    return calls


def module_id(path: Path, root: Path) -> str:
    """層を含むモジュールパス（`domain.reader`）。`build_arch.py` と同じ規約。"""
    relative = path.relative_to(root).with_suffix("")
    return ".".join(relative.parts)


def _walk(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def collect_classes(root: Path) -> list[ClassInfo]:
    """ソースルート全体からクラスを集める。"""
    found: list[ClassInfo] = []
    for path in _walk(root):
        found += parse_classes(path.read_text(encoding="utf-8"), module_id(path, root))
    return found


def collect_calls(root: Path) -> list[Call]:
    """ソースルート全体から呼び出しを集める。"""
    found: list[Call] = []
    for path in _walk(root):
        found += parse_calls(path.read_text(encoding="utf-8"), module_id(path, root))
    return found


def to_class_diagram(classes: list[ClassInfo]) -> str:
    """クラス図（Mermaid）にする。

    Note:
        継承の線は **同じリポジトリで見つかったクラスにだけ** 引く。
        標準ライブラリや外部ライブラリの基底まで描くと、設計書の図には
        絶対に無いノードが増えて、乖離が常に「実装だけにある」と出る。
    """
    known = {info.name for info in classes}
    lines = ["```mermaid", "classDiagram"]
    for info in classes:
        lines.append(f"  class {info.name} {{")
        for name, kind in info.attributes.items():
            lines.append(f"    +{name} {kind}".rstrip())
        for name in info.methods:
            lines.append(f"    +{name}()")
        lines.append("  }")
    for info in classes:
        for base in info.bases:
            if base in known:
                lines.append(f"  {base} <|-- {info.name}")
    lines.append("```")
    return "\n".join(lines)


def to_sequence_diagram(calls: list[Call]) -> str:
    """シーケンス図（Mermaid）にする。

    Note:
        参加者は呼び出し元のメソッドと呼び先の名前だけ。
        **時間の順は実装の出現順** であって、実行時の順ではない
        （条件分岐・ループは表現しない）。設計書のシーケンス図と
        突き合わせるための素材であって、置き換えるものではない。
    """
    lines = ["```mermaid", "sequenceDiagram", "  autonumber"]
    seen: set[tuple[str, str]] = set()
    for call in calls:
        pair = (call.caller, call.callee)
        if pair in seen:
            continue
        seen.add(pair)
        lines.append(f"  {call.caller}->>{call.callee}: 呼ぶ")
    lines.append("```")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(description="実装から UML を逆生成する")
    parser.add_argument("root", help="ソースルート")
    parser.add_argument("--kind", choices=KINDS, default="class", help="図の種類")
    parser.add_argument("--out", default="", help="書き出し先（省略時は標準出力）")
    args = parser.parse_args(argv)

    if args.kind == "state":
        print(
            "REFUSED: 状態遷移図は実装から復元できない"
            "（任意のコードから状態機械は一般に復元できない）。"
        )
        print(
            "HINT: 設計書の図に書いた状態名が実装の列挙型・定数にあるかを"
            "人が確かめる（architecture-drift の「名前の対応」）"
        )
        return 2

    root = Path(args.root)
    if not root.is_dir():
        print(f"NG: ソースルートがない（{root}）")
        return 2
    if not _walk(root):
        print(f"NG: .py が 1 つも無い（{root}）。この言語は未対応")
        return 2

    if args.kind == "class":
        text = to_class_diagram(collect_classes(root))
    else:
        text = to_sequence_diagram(collect_calls(root))

    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        print(f"書き出した: {path}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
