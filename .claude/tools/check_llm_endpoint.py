"""ローカル LLM のエンドポイントが Claude Code を駆動できるかを検査する。

Claude Code は Anthropic Messages API（`POST <base>/v1/messages`）を話す。
ローカルランタイム（Ollama / LM Studio / vLLM 等）は OpenAI 互換が普通なので、
間に変換プロキシを置くことになる。 **その変換が Claude Code の要求を満たして
いるか** は、実際に投げてみないと分からない。

「動かない」の原因を、Claude Code を起動する前に切り分けるためのツール。
検査するのは次の 4 つで、上から順に厳しくなる。

    1. messages    - 最小リクエストに Anthropic 形式の応答を返すか
    2. system      - system プロンプトと複数ターンを受け付けるか
    3. tools       - ツール定義を渡すと tool_use ブロックを返すか（最重要）
    4. streaming   - stream=true で SSE を返すか

3 が通らないエンドポイント（またはモデル）では、Claude Code は
ファイル読み書きすら行えない。「走り切らない」の大半はここが弱い。

使い方（前置コマンドはプロファイルの
「.claude/tools/ の Python ツール実行」。例: uv run python）:
    <ツール実行コマンド> .claude/tools/check_llm_endpoint.py
    <ツール実行コマンド> .claude/tools/check_llm_endpoint.py --model qwen3-coder
    <ツール実行コマンド> .claude/tools/check_llm_endpoint.py \
        --base-url http://localhost:4000 --model gemma3 --timeout 120

既定値は環境変数から読む:
    ANTHROPIC_BASE_URL / ANTHROPIC_MODEL /
    ANTHROPIC_AUTH_TOKEN（無ければ ANTHROPIC_API_KEY）

終了コード:
    0 = 4 項目すべて合格
    1 = 落ちた項目がある（どれが落ちたかを出力する）
    2 = 引数・環境の不足（base URL / model 未指定など）
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ANTHROPIC_VERSION = "2023-06-01"

WEATHER_TOOL = {
    "name": "get_weather",
    "description": "指定した都市の現在の天気を返す。天気を聞かれたら必ず使う。",
    "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string", "description": "都市名"}},
        "required": ["city"],
    },
}


def _post(
    base_url: str, token: str, header: str, body: dict, timeout: int, stream: bool
) -> tuple[int, str]:
    """/v1/messages に POST する。

    Args:
        base_url: エンドポイントのベース URL
        token: 資格情報（空文字なら認証ヘッダを付けない）
        header: 資格情報を載せるヘッダ名（Authorization / x-api-key）
        body: リクエストボディ
        timeout: タイムアウト秒
        stream: SSE を期待するか（True なら生テキストを返す）

    Returns:
        (HTTP ステータス, 応答本文)。接続失敗は (0, エラーメッセージ)
    """
    url = base_url.rstrip("/") + "/v1/messages"
    data = json.dumps(body).encode("utf-8")
    headers = {
        "content-type": "application/json",
        "anthropic-version": ANTHROPIC_VERSION,
    }
    if token:
        headers[header] = f"Bearer {token}" if header == "Authorization" else token

    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return 0, f"{type(error).__name__}: {error}"


def _report(name: str, ok: bool, detail: str) -> bool:
    """1 項目の結果を出力する。

    Args:
        name: 検査項目名
        ok: 合格か
        detail: 補足（不合格のときの理由や応答の断片）

    Returns:
        ok をそのまま返す
    """
    print(f"{'PASS' if ok else 'FAIL'}  {name}")
    if detail:
        for line in detail.splitlines():
            print(f"        {line}")
    return ok


def _excerpt(text: str, limit: int = 300) -> str:
    """応答本文を出力用に短く切る。

    Args:
        text: 応答本文
        limit: 残す文字数

    Returns:
        切り詰めた文字列
    """
    flattened = " ".join(text.split())
    return flattened[:limit] + ("..." if len(flattened) > limit else "")


def check_messages(base: str, token: str, header: str, model: str, timeout: int) -> bool:
    """最小リクエストが Anthropic 形式で返るかを検査する。

    Args:
        base: ベース URL
        token: 資格情報
        header: 資格情報のヘッダ名
        model: モデル名
        timeout: タイムアウト秒

    Returns:
        合格なら True
    """
    status, text = _post(
        base,
        token,
        header,
        {"model": model, "max_tokens": 16, "messages": [{"role": "user", "content": "ping"}]},
        timeout,
        stream=False,
    )
    if status == 0:
        return _report("messages", False, f"接続できない: {text}")
    if status == 401:
        return _report("messages", False, "401: 資格情報が拒否された（ヘッダの種類が違う可能性）")
    if status != 200:
        return _report("messages", False, f"HTTP {status}: {_excerpt(text)}")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _report("messages", False, f"JSON ではない応答: {_excerpt(text)}")
    if "content" not in payload:
        return _report("messages", False, f"content が無い: {_excerpt(text)}")
    return _report("messages", True, f"stop_reason={payload.get('stop_reason')}")


def check_system(base: str, token: str, header: str, model: str, timeout: int) -> bool:
    """system プロンプトと複数ターンを受け付けるかを検査する。

    Args:
        base: ベース URL
        token: 資格情報
        header: 資格情報のヘッダ名
        model: モデル名
        timeout: タイムアウト秒

    Returns:
        合格なら True
    """
    status, text = _post(
        base,
        token,
        header,
        {
            "model": model,
            "max_tokens": 32,
            "system": "あなたは簡潔に答える。",
            "messages": [
                {"role": "user", "content": "1 + 1 は?"},
                {"role": "assistant", "content": "2"},
                {"role": "user", "content": "それに 3 を足すと?"},
            ],
        },
        timeout,
        stream=False,
    )
    if status != 200:
        return _report("system", False, f"HTTP {status}: {_excerpt(text)}")
    return _report("system", True, "")


def check_tools(base: str, token: str, header: str, model: str, timeout: int) -> bool:
    """ツール定義を渡すと tool_use ブロックを返すかを検査する。

    Args:
        base: ベース URL
        token: 資格情報
        header: 資格情報のヘッダ名
        model: モデル名
        timeout: タイムアウト秒

    Returns:
        合格なら True
    """
    status, text = _post(
        base,
        token,
        header,
        {
            "model": model,
            "max_tokens": 256,
            "tools": [WEATHER_TOOL],
            "messages": [{"role": "user", "content": "東京の天気を教えて。"}],
        },
        timeout,
        stream=False,
    )
    if status != 200:
        return _report(
            "tools",
            False,
            f"HTTP {status}: {_excerpt(text)}\n"
            "ツール定義を受け付けないエンドポイントでは Claude Code は動かない",
        )
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return _report("tools", False, f"JSON ではない応答: {_excerpt(text)}")

    blocks = payload.get("content") or []
    used = [b for b in blocks if isinstance(b, dict) and b.get("type") == "tool_use"]
    if not used:
        return _report(
            "tools",
            False,
            "tool_use ブロックが返らなかった（テキストだけ返した）。\n"
            "モデルのツール呼び出し性能が不足しているか、プロキシが tools を捨てている。\n"
            f"応答: {_excerpt(text, 200)}",
        )
    if not isinstance(used[0].get("input"), dict):
        return _report("tools", False, "tool_use の input が object ではない")
    return _report("tools", True, f"呼んだツール: {used[0].get('name')} / input={used[0].get('input')}")


def check_streaming(base: str, token: str, header: str, model: str, timeout: int) -> bool:
    """stream=true で SSE が返るかを検査する。

    Args:
        base: ベース URL
        token: 資格情報
        header: 資格情報のヘッダ名
        model: モデル名
        timeout: タイムアウト秒

    Returns:
        合格なら True
    """
    status, text = _post(
        base,
        token,
        header,
        {
            "model": model,
            "max_tokens": 32,
            "stream": True,
            "messages": [{"role": "user", "content": "1 から 5 まで数えて。"}],
        },
        timeout,
        stream=True,
    )
    if status != 200:
        return _report("streaming", False, f"HTTP {status}: {_excerpt(text)}")
    if "event:" not in text and "data:" not in text:
        return _report("streaming", False, f"SSE ではない応答: {_excerpt(text)}")
    if "content_block_delta" not in text:
        return _report(
            "streaming",
            False,
            "content_block_delta が現れない（Anthropic 形式のストリームになっていない）",
        )
    return _report("streaming", True, "")


def main(argv: list[str]) -> int:
    """エントリポイント。

    Args:
        argv: コマンドライン引数

    Returns:
        終了コード
    """
    parser = argparse.ArgumentParser(description="ローカル LLM エンドポイントの適合検査")
    parser.add_argument("--base-url", default=os.environ.get("ANTHROPIC_BASE_URL", ""))
    parser.add_argument("--model", default=os.environ.get("ANTHROPIC_MODEL", ""))
    parser.add_argument(
        "--token",
        default=os.environ.get("ANTHROPIC_AUTH_TOKEN") or os.environ.get("ANTHROPIC_API_KEY", ""),
    )
    parser.add_argument(
        "--auth-header",
        choices=["Authorization", "x-api-key"],
        default="Authorization" if os.environ.get("ANTHROPIC_AUTH_TOKEN") else "x-api-key",
        help="資格情報を載せるヘッダ（既定は設定済みの環境変数から判定）",
    )
    parser.add_argument("--timeout", type=int, default=60, help="1 リクエストのタイムアウト秒")
    args = parser.parse_args(argv)

    if not args.base_url:
        print("ERROR: base URL が無い。--base-url か ANTHROPIC_BASE_URL を設定する")
        return 2
    if not args.model:
        print("ERROR: モデル名が無い。--model か ANTHROPIC_MODEL を設定する")
        return 2

    print(f"endpoint: {args.base_url.rstrip('/')}/v1/messages")
    print(f"model:    {args.model}")
    print(f"auth:     {args.auth_header if args.token else '(なし)'}")
    print()

    checks = [
        ("messages", check_messages),
        ("system", check_system),
        ("tools", check_tools),
        ("streaming", check_streaming),
    ]
    failed = []
    for name, func in checks:
        if not func(args.base_url, args.token, args.auth_header, args.model, args.timeout):
            failed.append(name)

    print()
    if failed:
        print(f"RESULT: {len(failed)} of {len(checks)} checks FAILED ({', '.join(failed)})")
        if "tools" in failed:
            print("        tools が落ちる構成では Claude Code は使えない。")
            print("        モデルを変えるか、変換プロキシの tools 対応を確認する。")
        return 1
    print(f"RESULT: all {len(checks)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
