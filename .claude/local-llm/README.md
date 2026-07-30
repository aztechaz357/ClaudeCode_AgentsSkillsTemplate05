# ローカル LLM で駆動する（`.claude/local-llm/`）

このテンプレート（エージェント・スキル・コマンド）を、Claude 以外の
ローカルモデル（gemma・qwen など）で動かすための設定一式です。

> **既定は Claude Code の基盤モデル（Opus / Sonnet / Haiku）** 。
> ここの設定は、ローカル LLM に切り替えるときだけ読み込みます。
> 通常運用では何も変わりません。

## 操作手順（これだけ）

理由と仕組みは次章以降。 **やることだけ** をここにまとめる。

### 初回だけ

```powershell
# 環境変数ファイルを自分用にコピーする（そのまま使えるが、置き場所は git 管理外に）
Copy-Item .claude\local-llm\env.example.ps1 ..\my-local-llm.ps1
```

### ローカル LLM に切り替える（毎回）

**シェル 1 — ブリッジを起動して開いたままにする**

```powershell
powershell -NoProfile -File .claude\local-llm\start-bridge.ps1
```

> EdgeXpert のモデル一覧が出れば成功。出なければ EdgeXpert
> （`192.168.11.17:11434`）に届いていない。Ctrl-C で停止。

**シェル 2 — 環境変数を読み込んで Claude Code を起動する**

```powershell
. ..\my-local-llm.ps1
claude --settings .claude\local-llm\settings.json
```

> `--model` は不要（`ANTHROPIC_MODEL` が効く）。 **必ず環境変数を
> 読み込んだのと同じシェルから起動する** 。

**Claude Code の中で**

```
/status         … Anthropic base URL が http://127.0.0.1:8787 か確認する
/local-mode on  … 小さいモデル向けの進め方に切り替える
```

### 基盤モデル（Opus / Sonnet / Haiku）に戻す

**新しいシェルを開いて `claude` を起動するだけ** 。環境変数はシェル限りなので、
それだけで基盤モデルに戻る（ブリッジは止めても止めなくてもよい）。

同じシェルのまま戻す場合は、環境変数を消してから起動する。

```powershell
Remove-Item Env:ANTHROPIC_BASE_URL, Env:ANTHROPIC_AUTH_TOKEN, Env:ANTHROPIC_MODEL, `
  Env:ANTHROPIC_DEFAULT_OPUS_MODEL, Env:ANTHROPIC_DEFAULT_SONNET_MODEL, `
  Env:ANTHROPIC_DEFAULT_HAIKU_MODEL
claude
```

Claude Code の中では `/local-mode off`（小さいモデル向けの進め方を解除）、
`/status` で `Anthropic base URL` の行が消えていることを確認する。

### うまくいかないときの最初の一手

```powershell
# エンドポイントの適合を機械的に確かめる（4 項目すべて PASS が正常）
uv run python .claude\tools\check_llm_endpoint.py --base-url http://127.0.0.1:8787 --model gemma4:26b
```

`tools` が FAIL したらモデルを変える。それ以外は
「[うまく動かないとき](#うまく動かないとき)」の表を見る。

## 先に知っておくこと

- **Anthropic は Claude Code を非 Claude モデルへルーティングすることを
  サポートしていません**（公式ドキュメントに明記）。動く構成でも、
  Claude Code の更新で壊れることがあります。壊れたらまず基盤モデルに戻して
  切り分けてください
- Claude Code が話すのは **Anthropic Messages API**（`POST <base>/v1/messages`）。
  Ollama / LM Studio / vLLM は OpenAI 互換が普通なので、
  **間に Anthropic 形式へ変換するプロキシが要ります**
- 変換プロキシが `tools`（ツール呼び出し）を落とすと、Claude Code は
  ファイル 1 つ読めません。 **まず疎通ではなくツール呼び出しを検査する**

## この環境の構成（EdgeXpert + Ollama）

```
Claude Code --Anthropic形式--> ollama_bridge.py --/api/chat--> EdgeXpert
             (localhost:8787)   (開発PCで起動)               192.168.11.17:11434
```

`/v1/messages` を Ollama は持たない（実測で 404）ため、同梱の
`ollama_bridge.py` が変換する。 **追加インストールは不要** （Python 標準
ライブラリのみ）。

### 実測したモデルの適合（2026-07-26 時点）

`.claude/tools/check_llm_endpoint.py` をブリッジ越しに実行した結果。

| Ollama タグ | messages | system | tools | streaming | 用途 |
|---|---|---|---|---|---|
| `gemma4:26b` | ✅ | ✅ | ✅ | ✅ | **既定**（sonnet / opus 相当） |
| `gemma4:e4b` | ✅ | ✅ | ✅ | ✅ | **軽量枠**（haiku 相当・8B） |
| `gpt-oss:20b` | ✅ | ✅ | ✅ | ❌ | 要注意（下記） |
| `batiai/qwen3.6-35b:iq4` | 未検証 | — | — | — | 思考が長く要トークン枠 |

> **`gpt-oss:20b` は `think: false` を無視して常に思考を出す** ため、
> 短い出力枠だと本文が空のまま終わる（実測）。使うなら
> `--reasoning text` で思考を本文として流すか、`max_tokens` を大きく取る。
> gemma4 系は `think: false` が効くので、そのまま使える。

## 手順（各ステップの説明）

冒頭の「操作手順（これだけ）」を、1 ステップずつ説明したもの。
初めて設定するとき・詰まったときに読む。

### 1. ブリッジを起動する（開発PCで、別シェル）

```powershell
powershell -NoProfile -File .claude\local-llm\start-bridge.ps1
```

起動時に EdgeXpert の `/api/tags` を叩き、モデル一覧を表示してから待ち受ける
（到達できなければその場で失敗する）。Ctrl-C で停止。

`uv` 環境なら `-Python "uv run python"`、宛先や既定モデルを変えるなら
`-Ollama` / `-DefaultModel` / `-SmallModel` を渡す。

### 2. 環境変数を設定する

`env.example.ps1`（PowerShell）/ `env.example.sh`（bash）をコピーして使う。

| 変数 | 役割 |
|---|---|
| `ANTHROPIC_BASE_URL` | プロキシのベース URL（`/v1/messages` は付けない） |
| `ANTHROPIC_AUTH_TOKEN` | 資格情報。`Authorization: Bearer` で送られる |
| `ANTHROPIC_API_KEY` | 資格情報。`x-api-key` で送られる（プロキシがこちらを読むとき） |
| `ANTHROPIC_MODEL` | メインセッションのモデル名 |
| `ANTHROPIC_DEFAULT_HAIKU_MODEL` | `haiku` エイリアスとバックグラウンド処理のモデル |
| `ANTHROPIC_DEFAULT_SONNET_MODEL` | `sonnet` エイリアスのモデル |
| `ANTHROPIC_DEFAULT_OPUS_MODEL` | `opus` エイリアスのモデル |
| `CLAUDE_CODE_SUBAGENT_MODEL` | 全サブエージェントを 1 モデルに固定（`inherit` で通常解決） |

> `ANTHROPIC_SMALL_FAST_MODEL` は非推奨。`ANTHROPIC_DEFAULT_HAIKU_MODEL` を使う。

**このテンプレートのエージェントは frontmatter に `model: haiku|sonnet|opus`
を持っています** （15 体）。エイリアスの解決先を上の 3 変数で差し替えれば、
定義を書き換えずに「軽い調査は小さいモデル、実装は大きいモデル」の
振り分けがそのまま活きます。モデルを 1 つしか動かせないなら
`CLAUDE_CODE_SUBAGENT_MODEL` で全部まとめて固定します。

**資格情報を `.claude/settings.json` に書かないこと** （コミットされ共有される）。
シェルの export か `~/.claude/settings.json` の `env` ブロックに置く。

### 3. エンドポイントを検査する（Claude Code を起動する前に）

```
<プロファイルの「.claude/tools/ の Python ツール実行」コマンド> \
    .claude/tools/check_llm_endpoint.py --base-url http://127.0.0.1:8787 --model gemma4:26b
```

`messages` / `system` / `tools` / `streaming` の 4 項目を実際に投げて確かめる。
**`tools` が FAIL する構成では、この先は無駄** —— モデルを変えるか、
プロキシのツール対応を直す。

### 4. Claude Code を起動して確認する

**環境変数を読み込んだのと同じシェルから** 起動する（別のシェルや、
ドックから開いたエディタには環境変数が届かない）。

```
claude --settings .claude/local-llm/settings.json
```

`--model` は要らない。`ANTHROPIC_MODEL` を設定してあれば、それが
そのセッションのモデルになる。

#### モデルの指定方法は 3 通り（上が優先）

| 方法 | 書き方 | 使いどころ |
|---|---|---|
| 起動フラグ | `claude --model gemma4:26b --settings .claude/local-llm/settings.json` | その 1 回だけ別モデルを試す |
| 環境変数 | `$env:ANTHROPIC_MODEL = "gemma4:26b"` → `claude ...` | **通常はこれ**（env ファイルに書いてある） |
| ブリッジの読み替え | 何も指定しない | 保険。Claude 内蔵名（`claude-opus-5` 等）が来たら `gemma4:26b`、`*haiku*` なら `gemma4:e4b` に振る（実測済み） |

つまり **素の `claude` でも動く** （最終的にブリッジが振り分けるため）。
ただし `/status` の表示は内蔵名のままになるので、どのモデルで走っているかを
自分で分かるようにするなら `ANTHROPIC_MODEL` を設定しておくほうがよい。

> `/model` の一覧には Ollama のモデルは出ない（本ブリッジはモデル探索
> エンドポイントを実装していない）。 **モデルを変えるときはセッションを
> 起動し直す** —— `--model` を付けるか、`ANTHROPIC_MODEL` を変える。

#### 起動できたかの確認

`/status` の **Status** タブで次の 2 行を見る。

- `Anthropic base URL` … `http://127.0.0.1:8787` になっているか
  （この行が無ければ環境変数がセッションに届いていない）
- `Auth token` … `ANTHROPIC_AUTH_TOKEN` が使われているか
  （claude.ai のログインが使われていると、基盤モデルに繋がってしまう）

そのうえで一言送ってみて、EdgeXpert 側に負荷がかかることを確認する
（`curl http://192.168.11.17:11434/api/ps` でモデルがロードされる）。

> 毎回の手順と、基盤モデルへ戻す手順は冒頭の
> 「[操作手順（これだけ）](#操作手順これだけ)」にまとめてある
> （同じ手順を 2 か所に置くと必ず片方が古くなるため、ここには再掲しない）。

### 5. 進め方をローカル LLM 向けに切り替える

```
/local-mode on
```

小さいモデルで「走り切らない」のはモデルの問題だけでなく、
**このテンプレートが前提にしている自律実行の粒度が大きすぎる** ためです。
`/local-mode` は 1 ターン 1 タスクの進め方へ切り替えます（`policy.md`）。

## 同梱の設定オーバーレイ（`settings.json`）

`claude --settings .claude/local-llm/settings.json` で重ねる。
プロキシ越しで問題になりやすい機能を先回りで切ってある。

| 設定 | 理由 |
|---|---|
| `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` | 上流が知らないフィールドで `400`（`context_management` / `Extra inputs are not permitted`）になるのを防ぐ |
| `MAX_THINKING_TOKENS=0` | 拡張思考を要求しない（対応しないモデルで `400` になる） |
| `alwaysThinkingEnabled: false` | 同上 |
| `CLAUDE_CODE_MAX_OUTPUT_TOKENS` | ローカルモデルの出力上限を超えないようにする |
| `CLAUDE_CODE_AUTO_COMPACT_WINDOW` | 自動圧縮をモデルの文脈長に合わせる |
| `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1` | 外向きの補助通信を止める（自動更新も止まる点に注意） |

> `CLAUDE_CODE_AUTO_COMPACT_WINDOW` は **100,000 未満に下げられません**
> （下限で丸められる）。32k などの小さいモデルでは効かないので、
> 文脈があふれたら `/compact` で回復する運用になります。

## うまく動かないとき

| 症状 | 原因 | 対処 |
|---|---|---|
| `401` | 資格情報のヘッダ種別違い | `ANTHROPIC_AUTH_TOKEN`（Bearer）と `ANTHROPIC_API_KEY`（x-api-key）を入れ替える |
| `Unable to connect to API` | URL 違い・プロキシ未起動 | `check_llm_endpoint.py` で切り分ける |
| `API returned an empty or malformed response (HTTP 200)` | プロキシが JSON 以外（HTML 等）を返した | プロキシのルート設定 |
| `400` で `context_management` / `Extra inputs are not permitted` | 上流が知らないフィールド | `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` |
| `400` で `thinking` | 拡張思考の非対応 | `MAX_THINKING_TOKENS=0` |
| 文脈超過のエラー（プロキシ独自の文言） | 自動圧縮が発火しない | `/compact`、`CLAUDE_CODE_AUTO_COMPACT_WINDOW` と `CLAUDE_CODE_MAX_OUTPUT_TOKENS` |
| `/model` にモデルが出ない | 名前が組み込み一覧に無い | `CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY=1`、または `ANTHROPIC_MODEL` で直接指定 |
| ツールを呼ばずに喋るだけ | モデルのツール呼び出しが弱い / プロキシが `tools` を捨てる | `check_llm_endpoint.py` の `tools` を見る。モデル変更が最短 |
| 途中で止まる・同じことを繰り返す | 自律実行の粒度が大きすぎる | `/local-mode on` |

Remote Control・音声入力・fast mode は、ゲートウェイ資格情報を設定している
間は使えません（claude.ai の identity を要求するため）。

## モデル選びの目安

- **ツール呼び出しの質が最優先** 。`check_llm_endpoint.py` の `tools` が
  通らないモデルは、性能の話以前に使えない
- **文脈長** —— このテンプレートは CLAUDE.md と規約文書を読ませる前提。
  32k では厳しく、余裕があるほど安定する
- **日本語の指示追従** —— 文書もコミットメッセージも日本語で書かせる
- 実際に走らせて、`.steering/` の記録（どこで止まったか）を見て選ぶ

## 1 モデル運用の場合

「メインセッションのモデルは 1 つしか選べない」のは事実です。
ただし **サブエージェントは別モデルにできる** ので、階層分けが完全に
死ぬわけではありません。

| | いくつ選べるか |
|---|---|
| メインセッション（親スレッド） | 1 つ（`ANTHROPIC_MODEL` / `--model`） |
| サブエージェント 15 体 | frontmatter の `opus` / `sonnet` / `haiku` ごとに別モデル |

EdgeXpert は複数モデルを同時に VRAM へ載せられることを確認済み
（`gemma4:26b` 25.8GB + `gemma4:e4b` 13.0GB + 35B 級 23.6GB が同時常駐）。
搭載メモリに余裕がある間は、2 モデルの使い分けで問題ありません。

### 1 モデルに固定するとき

メモリが厳しい、あるいは切り替えのロード待ちが煩わしいときは固定する。

```powershell
$env:ANTHROPIC_MODEL = "gemma4:26b"
$env:CLAUDE_CODE_SUBAGENT_MODEL = "gemma4:26b"   # frontmatter を全部上書き
```

### 1 モデルでもテンプレートが機能する理由

このテンプレートの価値の大半はモデルの階層分けではなく、
**モデルに依存しない仕組み** の側にあります。

| 1 モデルでも残るもの | なぜ |
|---|---|
| **コンテキスト隔離** | 長いテスト出力・ログをサブエージェントに読ませ、親には要約だけ返す。文脈長の短いローカルモデルほど効く |
| **決定論的な検証** | 番号・図・変異テスト・core 無変更・フックはスクリプトと終了コードで判定する。モデルの賢さと無関係 |
| **状態をファイルに置く設計** | `.steering/` から復帰できる。途中で止まりやすいローカルモデルほど効く |
| **役割の限定** | 各エージェント定義が「やること」を狭く縛る。同じ重みでも狭い指示のほうが安定する |

| 1 モデルで失われるもの | 緩和策 |
|---|---|
| 速度・メモリの最適化（軽い調査も大きいモデルで走る） | 軽い作業だけ `gemma4:e4b` を明示指定して別セッションで回す |
| 複数サブエージェントの結果を統合する判断の質 | `/local-mode` の「同時 1 体」規則（`policy.md`） |

### 使い方の切り替え方

1 モデル運用では、 **サブエージェントを「賢さの振り分け」ではなく
「コンテキスト隔離」のために呼ぶ** 。

- **積極的に委譲する**: 長い出力を出す作業 —— `test-runner` /
  `log-analyzer` / `file-finder` / `build-executor`
- **親に残す**: 設計判断のような重い思考。あるいは基盤モデルに戻して行い、
  決まった結果だけをローカル LLM に実行させる

## ブリッジの対応範囲と限界

自作アダプタなので、対応しているのは実装した分だけです。

| できること | 備考 |
|---|---|
| `/v1/messages`（非ストリーム / ストリーム） | SSE は chunked 転送で返す |
| system・複数ターン | 文字列とブロック配列の両方 |
| tools / tool_use / tool_result の往復 | `tool_use_id` からツール名を復元して Ollama の `tool` メッセージへ戻す |
| max_tokens・temperature・top_p・stop_sequences | Ollama の `options` に写す |
| `/v1/messages/count_tokens` | 文字数からの概算（Ollama に事前カウント API が無いため） |
| モデル名の読み替え | Claude 内蔵名が来たら既定 / 軽量モデルへ振る |

| できないこと | 挙動 |
|---|---|
| 画像・PDF などの入力 | `[unsupported block: image]` というテキストに置換 |
| 拡張思考（thinking ブロック）の返却 | 既定で捨てる（`--reasoning text` で本文として流す） |
| prompt caching（`cache_control`） | 無視する |

Claude Code は更新のたびに送るフィールドが増えるため、
**将来 400 が出たら `settings.json` の
`CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS=1` が効いているか確認** し、
それでも駄目ならブリッジ側で該当フィールドを捨てる実装を足す。

## 開発コンテナと併用するとき

`.devcontainer/` の送信ファイアウォールは既定拒否です。コンテナ内から使うなら:

1. `ANTHROPIC_BASE_URL` を `http://host.docker.internal:8787` にする
   （ブリッジは開発PC で動かしたまま）
2. または EdgeXpert に直接出す構成にするなら、
   `.devcontainer/allowed-domains.txt` に `192.168.11.17` を足してリビルドする
   （IP をそのまま書ける）
3. コンテナ内で `check_llm_endpoint.py` を実行して届くことを確かめる
