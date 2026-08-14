"""チケット追跡のモード設定を、読む / 書き換える。

規約の正は `.claude/skills/issue-tracking/SKILL.md`。
設定の正は `CLAUDE.md` のプロジェクトプロファイルの
「チケット追跡」節にある **`- 使用:` の 1 行だけ** 。

    ### チケット追跡

    - 使用: github
    - リポジトリ: owner/repo
    - ホスト: なし
    - ラベル: slice / debt / L1 / L2 / L3

**チケット駆動が既定** 。置き場所がどこかだけが違う:

    github … GitHub Issue（既定。リモートがあり gh が認証済みのとき）
    gitlab … GitLab Issue（glab が認証済みのとき。自前ホストは `ホスト:` に書く）
    local  … ハブ（docs/slices/S##-*.md）の「## チケット」節
    off    … チケットを使わない（工房レーンだけの短命なリポジトリ向け）

このツールがあるのは、モードを **エージェントの記憶や自然言語の解釈ではなく
終了コードで判定させる** ため。`github` のつもりで `local` のプロジェクトに
書き込む事故、`off` のプロジェクトから外部へ出す事故は取り消せないので、
判定を LLM に任せない。 **`github` と `gitlab` を取り違える事故も同じ** ——
別のサービスへ起票すると消して回ることになる。

判定不能（節が無い・値が不正）は **`github` ではなく 2** を返す。
「読めなかったから外部へ出してよい」という解釈を構造的に禁じる。

`on` は `github` の別名として読む（この節が 2 値だった頃の設定を壊さないため）。
書き込むときは常に正式な値（`github`）に正規化する。

`ホスト:` は **`gitlab` のときだけ意味を持つ** （自前ホストの GitLab）。
`なし` なら gitlab.com。他のモードへ移すときは「なし」に戻す
（使われない値が残っていると、次に読んだ人が現状と誤解する）。

使い方（前置コマンドはプロファイルの
「.claude/tools/ の Python ツール実行」。例: uv run python）:
    <ツール実行コマンド> .claude/tools/issue_mode.py
    <ツール実行コマンド> .claude/tools/issue_mode.py --set github --repo owner/repo
    <ツール実行コマンド> .claude/tools/issue_mode.py --set gitlab --repo group/project
    <ツール実行コマンド> .claude/tools/issue_mode.py --set gitlab --repo g/p --host gitlab.example.com
    <ツール実行コマンド> .claude/tools/issue_mode.py --set local
    <ツール実行コマンド> .claude/tools/issue_mode.py --set off
    <ツール実行コマンド> .claude/tools/issue_mode.py <リポジトリルート>

終了コード（`--set` のときは書き換えた後のモードを返す）:
    0 = 使用: github
    1 = 使用: off
    2 = 判定不能（CLAUDE.md が無い・節が無い・値が不正・引数のエラー）
    3 = 使用: local
    4 = 使用: gitlab
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# 節の見出し（記号や括弧の揺れを許すため、言葉だけで探す）。
# 「チケット追跡」が正だが、旧名「Issue 追跡」の節も読めるようにしておく
SECTION_WORDS = ("チケット追跡", "Issue 追跡")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
# 機械が読む 2 行。値だけを差し替えられるよう、前置きを捕獲する
_USE = re.compile(r"^(\s*-\s*使用\s*[:：]\s*)(.*)$")
_REPO = re.compile(r"^(\s*-\s*リポジトリ\s*[:：]\s*)(.*)$")
_HOST = re.compile(r"^(\s*-\s*ホスト\s*[:：]\s*)(.*)$")

MODES = ("github", "gitlab", "local", "off")
# リモートのサービスへ書き込むモード（`リポジトリ:` が要る）
REMOTE_MODES = ("github", "gitlab")
# 旧設定（2 値だった頃）の値。読むときだけ許し、書くときは正式名に直す
ALIASES = {"on": "github"}
# 「未設定」を意味する値（雛形の `{…}` は `_is_placeholder` で別に見る）
_UNSET = ("なし", "none", "-", "")

UNSET_REPO = "なし"
UNSET_HOST = "なし"

# モードごとの終了コード。`github` を 0 に据え、判定不能は 2 のまま据え置く。
# `gitlab` を後から 4 に足したのは、既存のプロジェクトで 0〜3 の意味を
# 変えないため（1 を「off」以外の意味にすると、古い分岐が黙って壊れる）
EXIT_CODES = {"github": 0, "off": 1, "local": 3, "gitlab": 4}


class ProfileError(Exception):
    """プロファイルに Issue 追跡の節が無い / 形が壊れている。"""


@dataclass
class Setting:
    """プロファイルから読み取った Issue 追跡の設定。

    Attributes:
        mode: `github` / `gitlab` / `local` / `off`。判定不能なら None
            （読めなかったときに `github` へ倒さない —— 外部書き込みは戻せない）。
        repo: `owner/repo`（GitLab では `group/project`）。未設定なら None。
        line: `使用:` の行番号（1 始まり）。見つからなければ 0。
        host: 自前ホストの GitLab のホスト名。gitlab.com なら None。
    """

    mode: str | None
    repo: str | None
    line: int = 0
    host: str | None = None


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
            if any(word in matched.group(2) for word in SECTION_WORDS):
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
    host: str | None = None
    line_number = 0
    for offset in range(start, end):
        line = lines[offset]
        used = _USE.match(line)
        if used and mode is None:
            value = used.group(2).strip().lower()
            value = ALIASES.get(value, value)
            mode = value if value in MODES else None
            line_number = offset + 1
            continue
        found = _REPO.match(line)
        if found and repo is None:
            value = found.group(2).strip()
            if value.lower() not in _UNSET and not _is_placeholder(value):
                repo = value
            continue
        named = _HOST.match(line)
        if named and host is None:
            value = named.group(2).strip()
            if value.lower() not in _UNSET and not _is_placeholder(value):
                host = value
    return Setting(mode, repo, line_number, host)


def set_mode(
    text: str, mode: str, repo: str | None = None, host: str | None = None
) -> str:
    """`使用:` の行（必要なら `リポジトリ:` `ホスト:` の行）だけを書き換える。

    Args:
        text: `CLAUDE.md` の全文。
        mode: `github` / `gitlab` / `local` / `off`（`on` は `github` の別名）。
        repo: `owner/repo`（GitLab では `group/project`）。None なら既存の値を保つ
            （リモートを使わないモードでは「なし」に戻す —— 使われない値が
            残っていると、次に読んだ人が現状と誤解する）。
        host: 自前ホストの GitLab のホスト名。`gitlab` 以外では「なし」に戻す。

    Returns:
        書き換えた全文（他の行は 1 文字も変えない）。

    Raises:
        ValueError: `mode` が `github` / `gitlab` / `local` / `off` でない。
        ProfileError: チケット追跡の節、または `使用:` の行が無い。
    """
    mode = ALIASES.get(mode, mode)
    if mode not in MODES:
        raise ValueError(f"モードは {' / '.join(MODES)} のいずれか: {mode}")

    lines = text.splitlines(keepends=True)
    plain = text.splitlines()
    start, end = _section_range(plain)
    if start < 0:
        raise ProfileError(
            "CLAUDE.md に「チケット追跡」の節が無い。プロファイルに節を作ってから切り替える"
        )

    use_at = -1
    repo_at = -1
    host_at = -1
    for offset in range(start, end):
        if use_at < 0 and _USE.match(plain[offset]):
            use_at = offset
        elif repo_at < 0 and _REPO.match(plain[offset]):
            repo_at = offset
        elif host_at < 0 and _HOST.match(plain[offset]):
            host_at = offset
    if use_at < 0:
        raise ProfileError("「チケット追跡」の節に `- 使用:` の行が無い")

    newline = "\n" if not lines[use_at].endswith("\r\n") else "\r\n"
    lines[use_at] = _USE.match(plain[use_at]).group(1) + mode + newline

    # 既にある行は置き換え、無い行は「足りない分だけ」まとめて差し込む。
    # 差し込みを最後に 1 回だけにするのは、先に差し込むと後続の行番号が
    # ずれて別の行を書き換えてしまうため
    added: list[str] = []

    wanted = repo if mode in REMOTE_MODES else UNSET_REPO
    if wanted is not None:
        if repo_at >= 0:
            lines[repo_at] = _REPO.match(plain[repo_at]).group(1) + wanted + newline
        else:
            added.append(f"- リポジトリ: {wanted}{newline}")

    # ホストは gitlab 専用。行が無いモードでわざわざ作らない
    # （プロファイルに意味の無い行が増えると、読む側が値を探す手間だけ増える）
    # `repo` と同じく None は「既存の値を保つ」。gitlab.com を使うなら
    # `--host` を渡さなければよく、既に書いてある自前ホストが消えない
    named = host if mode == "gitlab" else UNSET_HOST
    if named is not None:
        if host_at >= 0:
            lines[host_at] = _HOST.match(plain[host_at]).group(1) + named + newline
        elif mode == "gitlab":
            added.append(f"- ホスト: {named}{newline}")
    elif host_at < 0:
        added.append(f"- ホスト: {UNSET_HOST}{newline}")

    if added:
        at = (repo_at if repo_at >= 0 else use_at) + 1
        lines[at:at] = added
    return "".join(lines)


def _report(setting: Setting, path: Path) -> None:
    """読み取った設定を出力する（`gitlab` のときだけホストの行が増える）。"""
    if setting.mode is None:
        print(f"UNKNOWN: {path} にチケット追跡の設定が無い（節または `- 使用:` の行）")
        print("HINT: `### チケット追跡` の節を作り `- 使用: github` を置く")
        return
    print(f"チケット追跡: {setting.mode}")
    print(f"リポジトリ: {setting.repo or UNSET_REPO}")
    if setting.mode == "gitlab":
        print(f"ホスト: {setting.host or 'gitlab.com'}")
    print(f"設定: {path}:{setting.line}")


def main(argv: list[str] | None = None) -> int:
    """CLI 入口。終了コードでモードを返す。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(
        description="チケット追跡（github / gitlab / local / off）の設定を読む / 書き換える"
    )
    parser.add_argument("root", nargs="?", default=".", help="リポジトリルート")
    parser.add_argument(
        "--set", dest="target", default="", help="github / gitlab / local / off"
    )
    parser.add_argument(
        "--repo", default="", help="owner/repo（gitlab では group/project）"
    )
    parser.add_argument(
        "--host", default="", help="自前ホストの GitLab のホスト名（--set gitlab のとき）"
    )
    args = parser.parse_args(argv)

    path = Path(args.root) / "CLAUDE.md"
    if not path.is_file():
        print(f"UNKNOWN: CLAUDE.md がない（{path}）")
        return 2

    text = path.read_text(encoding="utf-8")
    if args.target:
        try:
            changed = set_mode(
                text,
                args.target.strip().lower(),
                args.repo or None,
                args.host.strip() or None,
            )
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
    return EXIT_CODES[setting.mode]


if __name__ == "__main__":
    sys.exit(main())
