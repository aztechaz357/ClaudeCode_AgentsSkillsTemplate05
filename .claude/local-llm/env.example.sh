# ローカル LLM（EdgeXpert の Ollama）に切り替える環境変数（bash / zsh）
#
# 前提: 別シェルでブリッジを起動しておくこと。
#   python .claude/local-llm/ollama_bridge.py
#
# 使い方:
#   1. このファイルをコピーして値を調整する（資格情報を足すなら git 管理外へ）
#   2. そのシェルで読み込む:  source ./my-local-llm.sh
#   3. 同じシェルから起動:    claude --settings .claude/local-llm/settings.json

# --- 接続先（ブリッジ） ---------------------------------------------------
# Claude Code -> ブリッジ(127.0.0.1:8787) -> Ollama(192.168.11.17:11434)
export ANTHROPIC_BASE_URL="http://127.0.0.1:8787"

# 開発コンテナの中から使う場合は、ホスト側のブリッジを指す:
# export ANTHROPIC_BASE_URL="http://host.docker.internal:8787"

# ブリッジは資格情報を検証しないが、Claude Code は「何かある」ことを要求する。
export ANTHROPIC_AUTH_TOKEN="local"

# --- モデル（EdgeXpert 上の Ollama タグ） ---------------------------------
# 実測: gemma4:26b / gemma4:e4b は messages・system・tools・streaming の
# 4 項目すべて通過（.claude/tools/check_llm_endpoint.py）。
export ANTHROPIC_MODEL="gemma4:26b"

# エージェント定義の frontmatter（model: haiku|sonnet|opus）の解決先。
export ANTHROPIC_DEFAULT_OPUS_MODEL="gemma4:26b"    # orchestrator / unit-tester / coder / integration-tester
export ANTHROPIC_DEFAULT_SONNET_MODEL="gemma4:26b"  # レビュー・検証・文書系
export ANTHROPIC_DEFAULT_HAIKU_MODEL="gemma4:e4b"   # file-finder / test-runner / build-executor と背景処理

# 全サブエージェントを 1 モデルに固定したいとき（メモリが厳しい場合など）。
# export CLAUDE_CODE_SUBAGENT_MODEL="gemma4:e4b"

# --- 基盤モデルへ戻す -----------------------------------------------------
# unset ANTHROPIC_BASE_URL ANTHROPIC_AUTH_TOKEN ANTHROPIC_MODEL \
#   ANTHROPIC_DEFAULT_OPUS_MODEL ANTHROPIC_DEFAULT_SONNET_MODEL ANTHROPIC_DEFAULT_HAIKU_MODEL
