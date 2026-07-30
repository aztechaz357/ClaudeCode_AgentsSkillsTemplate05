"""Claude Code（Anthropic Messages API）を Ollama につなぐ変換ブリッジ。

Claude Code が話すのは Anthropic Messages API（`POST /v1/messages`）だが、
Ollama が提供するのは独自 API（`/api/chat`）と OpenAI 互換 API だけで、
`/v1/messages` は 404 になる。その差を埋める最小のアダプタ。

    Claude Code  --Anthropic 形式-->  本ブリッジ  --/api/chat-->  Ollama

依存は Python 標準ライブラリのみ。追加インストールは要らない。

使い方（既定は EdgeXpert 上の Ollama を向く）:
    <ツール実行コマンド> .claude/local-llm/ollama_bridge.py
    <ツール実行コマンド> .claude/local-llm/ollama_bridge.py \
        --ollama http://192.168.11.17:11434 --listen 127.0.0.1:8787 \
        --default-model gemma4:26b --small-model gemma4:e4b

別シェルで Claude Code を起動する:
    $env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8787"
    $env:ANTHROPIC_AUTH_TOKEN = "local"      # 値は何でもよい（検証しない）
    claude --settings .claude/local-llm/settings.json

対応している範囲:
    - `/v1/messages`（非ストリーム・ストリーム both）
    - system（文字列 / ブロック配列）・複数ターン
    - tools / tool_use / tool_result の往復
    - max_tokens・temperature・top_p・stop_sequences
    - `/v1/messages/count_tokens`（概算。文字数からの見積もり）

対応していない範囲（要求が来たら 400 か無視で明示する）:
    - 画像・PDF などのテキスト以外の入力（[unsupported block] に置換）
    - 拡張思考（thinking）ブロックの返却。Ollama の思考出力は既定で捨てる
      （`--reasoning text` を付けるとテキストとして流す）
    - prompt caching（cache_control は無視する）

終了コード:
    0 = 正常終了（Ctrl-C）
    2 = 引数・環境のエラー
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ANTHROPIC_VERSION = "2023-06-01"


class Config:
    """ブリッジの動作設定。

    Attributes:
        ollama: Ollama のベース URL
        default_model: 既定のモデル（sonnet / opus 相当）
        small_model: 軽量モデル（haiku 相当・背景処理用）
        timeout: Ollama への 1 リクエストのタイムアウト秒
        reasoning: 思考出力の扱い（"hide" / "text"）
        think: モデル側の思考を有効にするか（既定は無効）
        verbose: リクエストの要約を標準出力に出すか
    """

    def __init__(
        self,
        ollama: str,
        default_model: str,
        small_model: str,
        timeout: int,
        reasoning: str,
        think: bool,
        verbose: bool,
    ) -> None:
        self.ollama = ollama.rstrip("/")
        self.default_model = default_model
        self.small_model = small_model
        self.timeout = timeout
        self.reasoning = reasoning
        self.think = think
        self.verbose = verbose


def resolve_model(requested: str, config: Config) -> str:
    """Claude Code が指定したモデル名を Ollama のタグへ解決する。

    環境変数で Ollama のタグを直接指定していればそのまま通す。Claude Code が
    内蔵の名前（claude-*-haiku 等）を送ってきた場合だけ、役割に応じて
    既定モデルへ読み替える（Ollama に無い名前で 404 にしないため）。

    Args:
        requested: リクエストの model フィールド
        config: 設定

    Returns:
        Ollama に渡すモデルタグ
    """
    name = (requested or "").strip()
    if not name:
        return config.default_model
    lowered = name.lower()
    if "haiku" in lowered:
        return config.small_model
    if "claude" in lowered or "sonnet" in lowered or "opus" in lowered:
        return config.default_model
    return name


def _blocks_to_text(content: object) -> str:
    """Anthropic のコンテンツ（文字列 / ブロック配列）を平文にする。

    Args:
        content: 文字列またはブロックの配列

    Returns:
        連結した平文
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            parts.append(str(block.get("text", "")))
        elif kind in ("image", "document"):
            parts.append("[unsupported block: %s]" % kind)
    return "\n".join(p for p in parts if p)


def to_ollama_messages(payload: dict) -> list[dict]:
    """Anthropic のリクエストを Ollama の messages に変換する。

    Args:
        payload: Anthropic 形式のリクエストボディ

    Returns:
        Ollama `/api/chat` の messages
    """
    messages: list[dict] = []

    system = payload.get("system")
    system_text = _blocks_to_text(system) if system is not None else ""
    if system_text:
        messages.append({"role": "system", "content": system_text})

    # tool_use_id -> ツール名（tool_result を Ollama の tool メッセージへ戻すため）
    tool_names: dict[str, str] = {}

    for message in payload.get("messages", []):
        role = message.get("role", "user")
        content = message.get("content")

        if isinstance(content, str):
            messages.append({"role": role, "content": content})
            continue
        if not isinstance(content, list):
            continue

        text_parts: list[str] = []
        tool_calls: list[dict] = []

        for block in content:
            if not isinstance(block, dict):
                continue
            kind = block.get("type")

            if kind == "text":
                text_parts.append(str(block.get("text", "")))

            elif kind == "tool_use":
                tool_names[str(block.get("id"))] = str(block.get("name"))
                tool_calls.append(
                    {
                        "function": {
                            "name": block.get("name"),
                            "arguments": block.get("input") or {},
                        }
                    }
                )

            elif kind == "tool_result":
                # tool_result は独立した tool メッセージとして積む。
                used_id = str(block.get("tool_use_id"))
                body = _blocks_to_text(block.get("content"))
                if block.get("is_error"):
                    body = "ERROR: " + body
                tool_message = {"role": "tool", "content": body}
                name = tool_names.get(used_id)
                if name:
                    tool_message["tool_name"] = name
                messages.append(tool_message)

            elif kind in ("image", "document"):
                text_parts.append("[unsupported block: %s]" % kind)

        if text_parts or tool_calls:
            entry: dict = {"role": role, "content": "\n".join(text_parts)}
            if tool_calls:
                entry["tool_calls"] = tool_calls
            messages.append(entry)

    return messages


def to_ollama_request(payload: dict, config: Config) -> dict:
    """Anthropic のリクエスト全体を Ollama の /api/chat 形式へ変換する。

    Args:
        payload: Anthropic 形式のリクエストボディ
        config: 設定

    Returns:
        Ollama へ送るリクエストボディ
    """
    options: dict = {}
    if isinstance(payload.get("max_tokens"), int):
        options["num_predict"] = payload["max_tokens"]
    for key in ("temperature", "top_p"):
        if isinstance(payload.get(key), (int, float)):
            options[key] = payload[key]
    if isinstance(payload.get("stop_sequences"), list) and payload["stop_sequences"]:
        options["stop"] = payload["stop_sequences"]

    request: dict = {
        "model": resolve_model(str(payload.get("model", "")), config),
        "messages": to_ollama_messages(payload),
        "stream": bool(payload.get("stream")),
    }
    if options:
        request["options"] = options

    # 思考するモデル（gemma4 等）は既定で思考にトークンを使い切り、本文が
    # 空のまま max_tokens に達する。Claude Code は本文とツール呼び出しを
    # 必要とするので、既定では思考を止める（実測で踏んだ）。
    if not config.think:
        request["think"] = False

    tools = payload.get("tools")
    if isinstance(tools, list) and tools:
        converted = []
        for tool in tools:
            if not isinstance(tool, dict) or not tool.get("name"):
                continue
            converted.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.get("name"),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("input_schema")
                        or {"type": "object", "properties": {}},
                    },
                }
            )
        if converted:
            request["tools"] = converted

    return request


def _stop_reason(done_reason: str, has_tool_use: bool) -> str:
    """Ollama の done_reason を Anthropic の stop_reason に写す。

    Args:
        done_reason: Ollama の終了理由
        has_tool_use: ツール呼び出しを含むか

    Returns:
        Anthropic の stop_reason
    """
    if has_tool_use:
        return "tool_use"
    if done_reason == "length":
        return "max_tokens"
    if done_reason == "stop":
        return "end_turn"
    return "end_turn"


def _tool_use_blocks(tool_calls: object) -> list[dict]:
    """Ollama の tool_calls を Anthropic の tool_use ブロックへ変換する。

    Args:
        tool_calls: Ollama の tool_calls

    Returns:
        tool_use ブロックの一覧
    """
    blocks = []
    if not isinstance(tool_calls, list):
        return blocks
    for call in tool_calls:
        function = (call or {}).get("function") or {}
        arguments = function.get("arguments")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                arguments = {"_raw": arguments}
        if not isinstance(arguments, dict):
            arguments = {}
        blocks.append(
            {
                "type": "tool_use",
                "id": "toolu_" + uuid.uuid4().hex[:24],
                "name": function.get("name", "unknown"),
                "input": arguments,
            }
        )
    return blocks


def _post_ollama(config: Config, body: dict, stream: bool):
    """Ollama の /api/chat を呼ぶ。

    Args:
        config: 設定
        body: リクエストボディ
        stream: ストリーム応答を読むか

    Returns:
        stream=False なら応答 dict、True なら行を返すイテレータ

    Raises:
        urllib.error.URLError: 接続できないとき
    """
    def send(payload: dict):
        request = urllib.request.Request(
            config.ollama + "/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"content-type": "application/json"},
            method="POST",
        )
        return urllib.request.urlopen(request, timeout=config.timeout)  # noqa: S310

    try:
        response = send(body)
    except urllib.error.HTTPError as error:
        # think を解さない古い Ollama / 非対応モデルでは 400 になる。
        # そのときだけフィールドを外して 1 度だけ再送する。
        detail = error.read().decode("utf-8", errors="replace")
        if error.code == 400 and "think" in detail and "think" in body:
            retry = dict(body)
            retry.pop("think", None)
            response = send(retry)
        else:
            raise urllib.error.HTTPError(
                error.url, error.code, detail, error.headers, None
            ) from error

    if not stream:
        with response:
            return json.loads(response.read().decode("utf-8"))
    return response


class Handler(BaseHTTPRequestHandler):
    """Anthropic Messages API を受けるハンドラ。"""

    protocol_version = "HTTP/1.1"
    config: Config = None  # type: ignore[assignment]

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        """既定のアクセスログを抑止する（verbose のときだけ出す）。"""
        if self.config and self.config.verbose:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # ------------------------------------------------------------- 応答補助
    def _send_json(self, status: int, payload: dict) -> None:
        """JSON を返す。

        Args:
            status: HTTP ステータス
            payload: 返す辞書
        """
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: int, message: str) -> None:
        """Anthropic 形式のエラーを返す。

        Args:
            status: HTTP ステータス
            message: エラーメッセージ
        """
        self._send_json(
            status,
            {"type": "error", "error": {"type": "api_error", "message": message}},
        )

    def _sse(self, event: str, data: dict) -> None:
        """SSE イベントを 1 つ書き出す。

        HTTP/1.1 で長さ未定の本文を返すため chunked 転送で送る
        （content-length も chunked も無いと、クライアントは本文の終わりを
        判断できずタイムアウトするまで待ち続ける。実測で踏んだ）。

        Args:
            event: イベント名
            data: data 行に載せる辞書
        """
        body = ("event: %s\ndata: %s\n\n" % (event, json.dumps(data))).encode("utf-8")
        self.wfile.write(b"%x\r\n" % len(body) + body + b"\r\n")
        self.wfile.flush()

    def _sse_end(self) -> None:
        """chunked 転送の終端を書き出す。"""
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    # --------------------------------------------------------------- ルート
    def do_GET(self) -> None:  # noqa: N802
        """疎通確認用のエンドポイント。"""
        if self.path.rstrip("/") in ("/health", ""):
            self._send_json(200, {"status": "ok", "ollama": self.config.ollama})
            return
        self._send_error_json(404, "not found: %s" % self.path)

    def do_POST(self) -> None:  # noqa: N802
        """/v1/messages と /v1/messages/count_tokens を処理する。"""
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            self._send_error_json(400, "invalid JSON: %s" % error)
            return

        path = self.path.split("?")[0].rstrip("/")
        if path.endswith("/count_tokens"):
            self._handle_count_tokens(payload)
            return
        if not path.endswith("/v1/messages"):
            self._send_error_json(404, "not found: %s" % self.path)
            return

        try:
            if payload.get("stream"):
                self._handle_stream(payload)
            else:
                self._handle_once(payload)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            self._send_error_json(502, "ollama HTTP %s: %s" % (error.code, detail[:500]))
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            self._send_error_json(502, "ollama unreachable: %s" % error)

    def _handle_count_tokens(self, payload: dict) -> None:
        """トークン数を概算で返す。

        Ollama は事前カウント API を持たないため、文字数からの見積もりを返す。
        Claude Code は文脈量の目安に使うだけなので、厳密でなくても破綻しない。

        Args:
            payload: Anthropic 形式のリクエスト
        """
        text = _blocks_to_text(payload.get("system") or "")
        for message in payload.get("messages", []):
            text += "\n" + _blocks_to_text(message.get("content"))
        # 日本語は 1 文字 ~1 トークン、英字は ~4 文字 1 トークンとして粗く見積もる。
        ascii_chars = len(re.findall(r"[\x00-\x7F]", text))
        wide_chars = len(text) - ascii_chars
        self._send_json(200, {"input_tokens": int(ascii_chars / 4) + wide_chars})

    def _handle_once(self, payload: dict) -> None:
        """非ストリームの /v1/messages を処理する。

        Args:
            payload: Anthropic 形式のリクエスト
        """
        body = to_ollama_request(payload, self.config)
        result = _post_ollama(self.config, body, stream=False)

        message = result.get("message") or {}
        blocks: list[dict] = []
        text = message.get("content") or ""
        if self.config.reasoning == "text":
            thinking = message.get("thinking") or message.get("reasoning") or ""
            if thinking:
                text = thinking + ("\n\n" + text if text else "")
        if text:
            blocks.append({"type": "text", "text": text})
        tool_blocks = _tool_use_blocks(message.get("tool_calls"))
        blocks.extend(tool_blocks)
        if not blocks:
            blocks.append({"type": "text", "text": ""})

        self._send_json(
            200,
            {
                "id": "msg_" + uuid.uuid4().hex[:24],
                "type": "message",
                "role": "assistant",
                "model": body["model"],
                "content": blocks,
                "stop_reason": _stop_reason(result.get("done_reason", "stop"), bool(tool_blocks)),
                "stop_sequence": None,
                "usage": {
                    "input_tokens": int(result.get("prompt_eval_count") or 0),
                    "output_tokens": int(result.get("eval_count") or 0),
                },
            },
        )

    def _handle_stream(self, payload: dict) -> None:
        """ストリーム（SSE）の /v1/messages を処理する。

        Args:
            payload: Anthropic 形式のリクエスト
        """
        body = to_ollama_request(payload, self.config)
        response = _post_ollama(self.config, body, stream=True)

        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("cache-control", "no-cache")
        self.send_header("transfer-encoding", "chunked")
        self.end_headers()

        message_id = "msg_" + uuid.uuid4().hex[:24]
        self._sse(
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": message_id,
                    "type": "message",
                    "role": "assistant",
                    "model": body["model"],
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            },
        )

        index = 0
        text_open = False
        has_tool_use = False
        done_reason = "stop"
        output_tokens = 0
        input_tokens = 0

        with response:
            for line in response:
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue

                message = chunk.get("message") or {}
                piece = message.get("content") or ""
                if self.config.reasoning == "text" and not piece:
                    piece = message.get("thinking") or message.get("reasoning") or ""

                if piece:
                    if not text_open:
                        self._sse(
                            "content_block_start",
                            {
                                "type": "content_block_start",
                                "index": index,
                                "content_block": {"type": "text", "text": ""},
                            },
                        )
                        text_open = True
                    self._sse(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": index,
                            "delta": {"type": "text_delta", "text": piece},
                        },
                    )

                for block in _tool_use_blocks(message.get("tool_calls")):
                    if text_open:
                        self._sse(
                            "content_block_stop",
                            {"type": "content_block_stop", "index": index},
                        )
                        text_open = False
                        index += 1
                    has_tool_use = True
                    self._sse(
                        "content_block_start",
                        {
                            "type": "content_block_start",
                            "index": index,
                            "content_block": {
                                "type": "tool_use",
                                "id": block["id"],
                                "name": block["name"],
                                "input": {},
                            },
                        },
                    )
                    self._sse(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": index,
                            "delta": {
                                "type": "input_json_delta",
                                "partial_json": json.dumps(block["input"]),
                            },
                        },
                    )
                    self._sse(
                        "content_block_stop",
                        {"type": "content_block_stop", "index": index},
                    )
                    index += 1

                if chunk.get("done"):
                    done_reason = chunk.get("done_reason") or "stop"
                    output_tokens = int(chunk.get("eval_count") or 0)
                    input_tokens = int(chunk.get("prompt_eval_count") or 0)

        if text_open:
            self._sse("content_block_stop", {"type": "content_block_stop", "index": index})

        self._sse(
            "message_delta",
            {
                "type": "message_delta",
                "delta": {
                    "stop_reason": _stop_reason(done_reason, has_tool_use),
                    "stop_sequence": None,
                },
                "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
            },
        )
        self._sse("message_stop", {"type": "message_stop"})
        self._sse_end()


def main(argv: list[str]) -> int:
    """エントリポイント。

    Args:
        argv: コマンドライン引数

    Returns:
        終了コード
    """
    parser = argparse.ArgumentParser(description="Anthropic Messages API -> Ollama ブリッジ")
    parser.add_argument("--listen", default="127.0.0.1:8787", help="待ち受け host:port")
    parser.add_argument(
        "--ollama", default="http://192.168.11.17:11434", help="Ollama のベース URL"
    )
    parser.add_argument("--default-model", default="gemma4:26b", help="sonnet / opus 相当")
    parser.add_argument("--small-model", default="gemma4:e4b", help="haiku 相当（背景処理）")
    parser.add_argument("--timeout", type=int, default=900, help="Ollama への タイムアウト秒")
    parser.add_argument(
        "--reasoning",
        choices=["hide", "text"],
        default="hide",
        help="思考出力を捨てる（hide）か本文として流す（text）か",
    )
    parser.add_argument(
        "--think",
        action="store_true",
        help="モデル側の思考を有効にする（既定は無効。思考でトークンを使い切る事故を防ぐ）",
    )
    parser.add_argument("--verbose", action="store_true", help="アクセスログを出す")
    args = parser.parse_args(argv)

    if ":" not in args.listen:
        print("ERROR: --listen は host:port の形で指定する")
        return 2
    host, _, port_text = args.listen.rpartition(":")
    if not port_text.isdigit():
        print("ERROR: ポート番号が数値ではない: %s" % port_text)
        return 2

    Handler.config = Config(
        ollama=args.ollama,
        default_model=args.default_model,
        small_model=args.small_model,
        timeout=args.timeout,
        reasoning=args.reasoning,
        think=args.think,
        verbose=args.verbose,
    )

    server = ThreadingHTTPServer((host, int(port_text)), Handler)
    print("ollama_bridge: http://%s:%s -> %s" % (host, port_text, args.ollama))
    print("  default model: %s" % args.default_model)
    print("  small model  : %s" % args.small_model)
    print("  ANTHROPIC_BASE_URL=http://%s:%s を設定して Claude Code を起動する" % (host, port_text))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nollama_bridge: 停止")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
