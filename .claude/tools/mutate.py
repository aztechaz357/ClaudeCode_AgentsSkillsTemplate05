"""実装に意図的な変異を加え、テストがそれを検出できるかを確認する。

テストが緑であることは「テストが有効であること」を意味しない。
実装を壊してもテストが通るなら、そのテストは何も守っていない。
本ツールは「壊してみて、落ちることを確かめる」作業を機械化する。

合否の意味が通常のテスト実行と **逆** である点に注意する。

- 変異を加えてテストが落ちた -> KILLED（正常。テストが有効）
- 変異を加えてもテストが通った -> SURVIVED（**テストの穴** ）

使い方（前置コマンドはプロファイルの
「.claude/tools/ の Python ツール実行」。例: uv run python）:
    <ツール実行コマンド> .claude/tools/mutate.py --file <path> --find <str>
        --replace <str> [--tests <path>] [--expect <テスト名の一部>] [--count <n>]

    # 変異仕様をまとめて実行する
    <ツール実行コマンド> .claude/tools/mutate.py --spec <spec.json> [--tests <path>]

    # テストランナーがプロファイルで別のものなら明示する
    <ツール実行コマンド> .claude/tools/mutate.py --spec <spec.json>
        --test-command "npm test --"

仕様ファイル（JSON）の形（詳細は .claude/mutations/README.md）:
    [
      {"file": "src/pkg/mod.py", "find": "+ x", "replace": "- x",
       "expect": "test_sign", "label": "符号を反転"},
      ...
    ]

テストコマンドは --test-command で与える（既定は "uv run pytest -q"）。
失敗を非 0 の終了コードで返すコマンドであれば言語は問わない。
--tests を渡すと、そのパスをコマンドの末尾に追加する。

終了コード:
    0 = 全ての変異が検出された（KILLED）
    1 = 検出されなかった変異がある（SURVIVED。テストの穴）
    2 = 引数・環境のエラー（置換対象が見つからない等）

安全性:
    対象ファイルは必ず元へ戻す。テストが失敗しても、例外が出ても、
    Ctrl-C で中断されても finally で復元する。復元に失敗した場合は
    バックアップの場所を表示する。
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_TEST_COMMAND = "uv run pytest -q"


@dataclass(frozen=True)
class Mutation:
    """1 つの変異の指定。

    Attributes:
        file: 変異を加えるファイル
        find: 置換前の文字列
        replace: 置換後の文字列
        expect: 落ちるべきテスト名の一部（省略可）
        label: 出力に表示する説明（省略時は find の先頭）
        count: 置換する出現回数（既定 1。0 なら全て）
    """

    file: str
    find: str
    replace: str
    expect: str | None = None
    label: str | None = None
    count: int = 1

    @property
    def title(self) -> str:
        """出力に使う説明を返す。

        Returns:
            label があればそれ、無ければ find を短く切ったもの
        """
        if self.label:
            return self.label
        head = self.find.strip().splitlines()[0] if self.find.strip() else self.find
        return head[:40]


def _run_tests(
    tests: str | None, repo_root: Path, test_command: str
) -> tuple[bool, str]:
    """テストを実行し、全て通ったかと出力を返す。

    Args:
        tests: テスト対象のパス。None なら全体
        repo_root: リポジトリルート
        test_command: テストコマンド（プロファイルの「テスト（全体）」）

    Returns:
        (全て通ったか, 標準出力と標準エラーを連結したもの)
    """
    command = shlex.split(test_command, posix=False)
    if tests:
        command.append(tests)

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"

    completed = subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=repo_root,
        env=env,
        shell=False,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode == 0, output


def _failed_test_names(output: str) -> list[str]:
    """テスト出力から失敗したテスト名を拾う。

    `FAILED <name>` 形式（pytest 等）の行を対象とする。別形式のランナーでは
    名前が拾えないだけで、KILLED / SURVIVED の判定（終了コード）には影響しない。

    Args:
        output: テストコマンドの出力

    Returns:
        FAILED 行から取り出したテスト名の一覧
    """
    names = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("FAILED "):
            names.append(stripped[len("FAILED ") :].split(" ")[0])
    return names


def _apply(path: Path, mutation: Mutation) -> str:
    """変異を適用し、元の内容を返す。

    Args:
        path: 対象ファイル
        mutation: 適用する変異

    Returns:
        変異前のファイル内容

    Raises:
        ValueError: 置換対象が見つからない、または期待した数と一致しないとき
    """
    original = path.read_text(encoding="utf-8")
    occurrences = original.count(mutation.find)

    if occurrences == 0:
        raise ValueError(
            f"置換対象が見つからない: {mutation.find!r}\n"
            "        空振りの変異は「検出されなかった」と誤報告するため、"
            "エラーとして扱う"
        )
    if mutation.count and occurrences > mutation.count:
        raise ValueError(
            f"置換対象が {occurrences} 箇所ある（期待 {mutation.count} 箇所）: "
            f"{mutation.find!r}\n"
            "        意図しない箇所を書き換えないため、"
            "find をより具体的にするか --count を指定する"
        )

    count = mutation.count if mutation.count else -1
    mutated = original.replace(mutation.find, mutation.replace, count)
    path.write_text(mutated, encoding="utf-8", newline="\n")
    return original


def _check_one(
    mutation: Mutation, tests: str | None, repo_root: Path, test_command: str
) -> bool:
    """1 つの変異を適用してテストを実行し、必ず元へ戻す。

    Args:
        mutation: 適用する変異
        tests: テスト対象のパス
        repo_root: リポジトリルート
        test_command: テストコマンド

    Returns:
        変異が検出された（KILLED）なら True
    """
    path = repo_root / mutation.file
    if not path.is_file():
        print(f"ERROR: file not found: {mutation.file}")
        raise SystemExit(2)

    try:
        original = _apply(path, mutation)
    except ValueError as error:
        print(f"ERROR: {mutation.file}: {error}")
        raise SystemExit(2) from error

    try:
        passed, output = _run_tests(tests, repo_root, test_command)
    finally:
        try:
            path.write_text(original, encoding="utf-8", newline="\n")
        except OSError as error:  # pragma: no cover - 復元失敗は異常事態
            print(f"FATAL: 復元に失敗した: {path}: {error}")
            raise

    if passed:
        print(f"SURVIVED: {mutation.title}")
        print("    変異を加えてもテストが通った。テストがこの誤りを守っていない")
        return False

    failed = _failed_test_names(output)
    print(f"KILLED:   {mutation.title}  ({len(failed)} tests failed)")

    if mutation.expect:
        matched = [name for name in failed if mutation.expect in name]
        if not matched:
            print(
                f"    WARNING: 期待したテスト（{mutation.expect}）は落ちていない。"
                f"落ちたのは: {', '.join(failed[:3])}"
            )
        else:
            print(f"    期待どおり {matched[0]} が落ちた")
    return True


def _load_spec(spec_path: Path) -> list[Mutation]:
    """仕様ファイルから変異の一覧を読む。

    Args:
        spec_path: JSON ファイルのパス

    Returns:
        変異の一覧

    Raises:
        SystemExit: 形式が不正なとき
    """
    try:
        raw = json.loads(spec_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"ERROR: 仕様ファイルを読めない: {spec_path}: {error}")
        raise SystemExit(2) from error

    if not isinstance(raw, list):
        print("ERROR: 仕様ファイルは変異の配列である必要がある")
        raise SystemExit(2)

    mutations = []
    for index, item in enumerate(raw, start=1):
        missing = {"file", "find", "replace"} - set(item)
        if missing:
            print(f"ERROR: 仕様 {index} に必須キーがない: {sorted(missing)}")
            raise SystemExit(2)
        mutations.append(
            Mutation(
                file=item["file"],
                find=item["find"],
                replace=item["replace"],
                expect=item.get("expect"),
                label=item.get("label"),
                count=int(item.get("count", 1)),
            )
        )
    return mutations


def main(argv: list[str]) -> int:
    """エントリポイント。

    Args:
        argv: コマンドライン引数

    Returns:
        終了コード
    """
    parser = argparse.ArgumentParser(description="変異テストの補助")
    parser.add_argument("--file", help="変異を加えるファイル")
    parser.add_argument("--find", help="置換前の文字列")
    parser.add_argument("--replace", help="置換後の文字列")
    parser.add_argument("--expect", help="落ちるべきテスト名の一部")
    parser.add_argument("--label", help="出力に表示する説明")
    parser.add_argument("--count", type=int, default=1, help="置換する出現回数（0 で全て）")
    parser.add_argument("--spec", help="変異仕様の JSON ファイル")
    parser.add_argument("--tests", help="テスト対象のパス（省略時は全体）")
    parser.add_argument(
        "--test-command",
        default=DEFAULT_TEST_COMMAND,
        help=f"テストコマンド（既定: {DEFAULT_TEST_COMMAND}）",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent.parent

    if args.spec:
        mutations = _load_spec(Path(args.spec))
    elif args.file and args.find is not None and args.replace is not None:
        mutations = [
            Mutation(
                file=args.file,
                find=args.find,
                replace=args.replace,
                expect=args.expect,
                label=args.label,
                count=args.count,
            )
        ]
    else:
        print("ERROR: --spec か、--file / --find / --replace の 3 つを指定する")
        return 2

    survived = 0
    for mutation in mutations:
        if not _check_one(mutation, args.tests, repo_root, args.test_command):
            survived += 1

    total = len(mutations)
    if survived:
        print(f"RESULT: {survived} of {total} mutations SURVIVED（テストの穴）")
        return 1
    print(f"RESULT: all {total} mutations KILLED")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
