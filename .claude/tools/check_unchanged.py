"""指定したファイル群が、ある地点から変更されていないことを確認する。

CLAUDE.md 家風パターンの「core 無変更」を機械検証するためのツール。
新しい実装を契約の別実装として追加するとき、中核クラスに手が入っていない
ことを毎フェーズ確認する必要があるが、git diff を手作業で組み立てるのは
間違いやすく再現性も無い。

対象ファイルの一覧は **プロジェクト固有** のため、ツールには埋め込まず
`.claude/core_files.txt` から読む（ツール自体はテンプレートとして
他プロジェクトへそのまま持ち出せる）。

使い方（前置コマンドはプロファイルの
「.claude/tools/ の Python ツール実行」。例: uv run python）:
    # 既定の一覧（.claude/core_files.txt）を、指定コミット以降で検査する
    <ツール実行コマンド> .claude/tools/check_unchanged.py --since <commit>

    # 一覧を明示する
    <ツール実行コマンド> .claude/tools/check_unchanged.py --since <commit> \
        --paths src/pkg/a.py src/pkg/b.py

    # 作業ツリーの未コミット分も含めて検査する
    <ツール実行コマンド> .claude/tools/check_unchanged.py --since <commit> --include-worktree

一覧ファイルの形式:
    1 行 1 パス。空行と # で始まる行は無視する。

終了コード:
    0 = 対象がすべて無変更
    1 = 変更されたファイルがある
    2 = 引数・環境のエラー
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_LIST = Path(".claude/core_files.txt")


def _git(args: list[str], repo_root: Path) -> tuple[int, str]:
    """git コマンドを実行する。

    Args:
        args: git に渡す引数
        repo_root: リポジトリルート

    Returns:
        (終了コード, 標準出力)
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(  # noqa: S603
        ["git", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=repo_root,
        env=env,
        shell=False,
    )
    return completed.returncode, completed.stdout or ""


def _load_paths(list_path: Path) -> list[str]:
    """一覧ファイルから対象パスを読む。

    Args:
        list_path: 一覧ファイルのパス

    Returns:
        対象パスの一覧

    Raises:
        SystemExit: ファイルが無い、または対象が 0 件のとき
    """
    if not list_path.is_file():
        print(f"ERROR: 一覧ファイルが無い: {list_path}")
        print("       --paths で明示するか、一覧ファイルを作成する")
        raise SystemExit(2)

    paths = []
    for line in list_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            paths.append(stripped)

    if not paths:
        print(f"ERROR: 一覧ファイルに対象が 1 件も無い: {list_path}")
        print("       テンプレートのままなら、このプロジェクトの中核ファイルを記入する")
        raise SystemExit(2)
    return paths


def _changed(
    since: str, paths: list[str], repo_root: Path, include_worktree: bool
) -> dict[str, int]:
    """変更されたファイルと変更行数を返す。

    Args:
        since: 比較の起点となるコミット
        paths: 検査対象のパス
        repo_root: リポジトリルート
        include_worktree: 未コミットの変更も含めるか

    Returns:
        変更されたパスから変更行数への辞書
    """
    args = ["diff", "--numstat", since]
    if not include_worktree:
        args.append("HEAD")
    args += ["--", *paths]

    code, output = _git(args, repo_root)
    if code != 0:
        print(f"ERROR: git diff に失敗した（コミット {since} は存在するか）")
        raise SystemExit(2)

    changed: dict[str, int] = {}
    for line in output.splitlines():
        fields = line.split("\t")
        if len(fields) < 3:
            continue
        added, removed, path = fields[0], fields[1], fields[2]
        total = 0
        for value in (added, removed):
            if value.isdigit():
                total += int(value)
        changed[path] = total
    return changed


def _verify_paths_exist(paths: list[str], repo_root: Path) -> None:
    """対象ファイルが実在することを確認する。

    存在しないパスを黙って無視すると「無変更」と誤報告するため、
    エラーとして扱う。

    Args:
        paths: 検査対象のパス
        repo_root: リポジトリルート

    Raises:
        SystemExit: 存在しないパスがあるとき
    """
    missing = [p for p in paths if not (repo_root / p).exists()]
    if missing:
        print("ERROR: 一覧に存在しないパスがある（誤報告を防ぐためエラーとする）:")
        for path in missing:
            print(f"    {path}")
        raise SystemExit(2)


def main(argv: list[str]) -> int:
    """エントリポイント。

    Args:
        argv: コマンドライン引数

    Returns:
        終了コード
    """
    parser = argparse.ArgumentParser(description="core 無変更の機械検証")
    parser.add_argument("--since", required=True, help="比較の起点となるコミット")
    parser.add_argument("--paths", nargs="*", help="検査対象（省略時は一覧ファイル）")
    parser.add_argument("--list", default=str(DEFAULT_LIST), help="一覧ファイルのパス")
    parser.add_argument(
        "--include-worktree",
        action="store_true",
        help="未コミットの変更も含めて検査する",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent.parent
    paths = args.paths if args.paths else _load_paths(repo_root / args.list)

    _verify_paths_exist(paths, repo_root)
    changed = _changed(args.since, paths, repo_root, args.include_worktree)

    scope = "作業ツリー含む" if args.include_worktree else "コミット済みのみ"
    print(f"起点: {args.since}（{scope}）  対象: {len(paths)} ファイル")

    if changed:
        print(f"NG: {len(changed)} ファイルが変更されている")
        for path, lines in sorted(changed.items()):
            print(f"    {path}: {lines} 行の差分")
        print("RESULT: core 無変更が破られている")
        return 1

    for path in paths:
        print(f"    OK  {path}")
    print(f"RESULT: 対象 {len(paths)} ファイルすべて無変更")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
