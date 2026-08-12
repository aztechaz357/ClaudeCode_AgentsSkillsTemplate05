"""Issue 追跡（GitHub Issues）を使うかどうかの設定を、読む / 書き換える。

規約の正は `.claude/skills/issue-tracking/SKILL.md`。
設定の正は `CLAUDE.md` のプロジェクトプロファイルの
「Issue 追跡（GitHub Issues）」節にある **`- 使用:` の 1 行だけ** 。

    ### Issue 追跡（GitHub Issues）

    - 使用: off
    - リポジトリ: なし
    - ラベル: slice / debt / L1 / L2 / L3

このツールがあるのは、モードを **エージェントの記憶や自然言語の解釈ではなく
終了コードで判定させる** ため。`off` のプロジェクトで誤って GitHub へ
書き込む事故は取り消せないので、判定を LLM に任せない。

判定不能（節が無い・値が `on` / `off` 以外）は **`on` ではなく 2** を返す。
「読めなかったから使ってよい」という解釈を構造的に禁じる。

使い方（前置コマンドはプロファイルの
「.claude/tools/ の Python ツール実行」。例: uv run python）:
    <ツール実行コマンド> .claude/tools/issue_mode.py
    <ツール実行コマンド> .claude/tools/issue_mode.py --set on --repo owner/repo
    <ツール実行コマンド> .claude/tools/issue_mode.py --set off
    <ツール実行コマンド> .claude/tools/issue_mode.py <リポジトリルート>

終了コード（`--set` のときは書き換えた後のモードを返す）:
    0 = 使用: on
    1 = 使用: off
    2 = 判定不能（CLAUDE.md が無い・節が無い・値が不正・引数のエラー）
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# 節の見出し（記号や括弧の揺れを許すため、言葉だけで探す）
SECTION_WORD = "Issue 追跡"
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
# 機械が読む 2 行。値だけを差し替えられるよう、前置きを捕獲する
_USE = re.compile(r"^(\s*-\s*使用\s*[:：]\s*)(.*)$")
_REPO = re.compile(r"^(\s*-\s*リポジトリ\s*[:：]\s*)(.*)$")

MODES = ("on", "off")
# 「未設定」を意味する値（雛形の `{…}` は `_is_placeholder` で別に見る）
_UNSET = ("なし", "none", "-", "")

UNSET_REPO = "なし"


class ProfileError(Exception):
    """プロファイルに Issue 追跡の節が無い / 形が壊れている。"""


@dataclass
class Setting:
    """プロファイルから読み取った Issue 追跡の設定。

    Attributes:
        mode: `on` / `off`。判定不能なら None（`on` に倒さない）。
        repo: `owner/repo`。未設定・雛形のままなら None。
        line: `使用:` の行番号（1 始まり）。見つからなければ 0。
    """

    mode: str | None
    repo: str | None
    line: int = 0


def _is_placeholder(value: str) -> bool:
    """雛形の穴（`{例: owner/repo}`）かどうか。"""
    return value.startswith("{")


def _section_range(lines: list[str]) -> tuple[int, int]:
    """Issue 追跡の節の行範囲 `[開始, 終了)` を返す。

    Args:
        lines: CLAUDE.md を行に分割したもの。

    Returns:
        見出しの次の行から、同じ深さ以上の次の見出しまでの範囲。
        節が無ければ `(-1, -1)`。
    """
    start = -1
    level = 0
    for index, line in enumerate(lines):
        matched = _HEADING.match(line)
        if not matched:
            continue
        if start < 0:
            if SECTION_WORD in matched.group(2):
                start = index + 1
                level = len(matched.group(1))
            continue
        if len(matched.group(1)) <= level:
            return start, index
    if start < 0:
        return -1, -1
    return start, len(lines)


def read_mode(text: str) -> Setting:
    """CLAUDE.md の全文から Issue 追跡の設定を読み取る。

    Args:
        text: `CLAUDE.md` の全文。

    Returns:
        読み取った設定。節・行・値のどれかが欠けていれば `mode` は None。
    """
    lines = text.splitlines()
    start, end = _section_range(lines)
    if start < 0:
        return Setting(None, None)

    mode: str | None = None
    repo: str | None = None
    line_number = 0
    for offset in range(start, end):
        line = lines[offset]
        used = _USE.match(line)
        if used and mode is None:
            value = used.group(2).strip().lower()
            mode = value if value in MODES else None
            line_number = offset + 1
            continue
        found = _REPO.match(line)
        if found and repo is None:
            value = found.group(2).strip()
            if value.lower() not in _UNSET and not _is_placeholder(value):
                repo = value
    return Setting(mode, repo, line_number)


def set_mode(text: str, mode: str, repo: str | None = None) -> str:
    """`使用:` の行（必要なら `リポジトリ:` の行）だけを書き換えた全文を返す。

    Args:
        text: `CLAUDE.md` の全文。
        mode: `on` または `off`。
        repo: `owner/repo`。None なら既存の値を保つ（`off` のときは消す）。

    Returns:
        書き換えた全文（他の行は 1 文字も変えない）。

    Raises:
        ValueError: `mode` が `on` / `off` でない。
        ProfileError: Issue 追跡の節、または `使用:` の行が無い。
    """
    if mode not in MODES:
        raise ValueError(f"モードは on / off のいずれか: {mode}")

    lines = text.splitlines(keepends=True)
    plain = text.splitlines()
    start, end = _section_range(plain)
    if start < 0:
        raise ProfileError(
            "CLAUDE.md に「Issue 追跡」の節が無い。プロファイルに節を作ってから切り替える"
        )

    use_at = -1
    repo_at = -1
    for offset in range(start, end):
        if use_at < 0 and _USE.match(plain[offset]):
            use_at = offset
        elif repo_at < 0 and _REPO.match(plain[offset]):
            repo_at = offset
    if use_at < 0:
        raise ProfileError("「Issue 追跡」の節に `- 使用:` の行が無い")

    newline = "\n" if not lines[use_at].endswith("\r\n") else "\r\n"
    lines[use_at] = _USE.match(plain[use_at]).group(1) + mode + newline

    wanted = UNSET_REPO if mode == "off" else repo
    if wanted is not None:
        if repo_at >= 0:
            lines[repo_at] = _REPO.match(plain[repo_at]).group(1) + wanted + newline
        else:
            lines.insert(use_at + 1, f"- リポジトリ: {wanted}{newline}")
    return "".join(lines)


def _report(setting: Setting, path: Path) -> None:
    """読み取った設定を 3 行で出力する。"""
    if setting.mode is None:
        print(f"UNKNOWN: {path} に Issue 追跡の設定が無い（節または `- 使用:` の行）")
        print("HINT: `### Issue 追跡（GitHub Issues）` の節を作り `- 使用: off` を置く")
        return
    print(f"Issue 追跡: {setting.mode}")
    print(f"リポジトリ: {setting.repo or UNSET_REPO}")
    print(f"設定: {path}:{setting.line}")


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。終了コードでモードを返す。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(
        description="Issue 追跡（GitHub Issues）の設定を読む / 書き換える"
    )
    parser.add_argument("root", nargs="?", default=".", help="リポジトリルート")
    parser.add_argument("--set", dest="target", default="", help="on または off")
    parser.add_argument("--repo", default="", help="owner/repo（--set on のとき）")
    args = parser.parse_args(argv)

    path = Path(args.root) / "CLAUDE.md"
    if not path.is_file():
        print(f"UNKNOWN: CLAUDE.md がない（{path}）")
        return 2

    text = path.read_text(encoding="utf-8")
    if args.target:
        try:
            changed = set_mode(text, args.target.strip().lower(), args.repo or None)
        except (ValueError, ProfileError) as error:
            print(f"NG: {error}")
            return 2
        if changed != text:
            path.write_text(changed, encoding="utf-8")
        text = changed

    setting = read_mode(text)
    _report(setting, path)
    if setting.mode is None:
        return 2
    return 0 if setting.mode == "on" else 1


if __name__ == "__main__":
    sys.exit(main())
