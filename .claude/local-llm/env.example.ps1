# Environment for driving Claude Code with the EdgeXpert Ollama box.
#
# NOTE: This file is ASCII-only on purpose. PowerShell 5.1 parses a BOM-less
# UTF-8 .ps1 as ANSI, and multi-byte characters in comments can swallow the
# following newline and corrupt the next statement. The Japanese explanation
# lives in .claude/local-llm/README.md.
#
# Prerequisite: start the bridge in ANOTHER shell first
#   powershell -NoProfile -File .claude\local-llm\start-bridge.ps1
#
# Usage:
#   1. copy this file, adjust the values (keep any real credential out of git)
#   2. dot-source it:   . .\my-local-llm.ps1
#   3. launch from the same shell:
#        claude --settings .claude\local-llm\settings.json

# --- endpoint (the bridge) -------------------------------------------------
# Claude Code -> bridge(127.0.0.1:8787) -> Ollama(192.168.11.17:11434)
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:8787"

# The bridge does not verify credentials, but Claude Code needs one to exist.
$env:ANTHROPIC_AUTH_TOKEN = "local"

# --- models (Ollama tags on the EdgeXpert) ---------------------------------
# Measured with .claude/tools/check_llm_endpoint.py through the bridge:
# gemma4:26b and gemma4:e4b pass all four checks
# (messages / system / tools / streaming).
$env:ANTHROPIC_MODEL = "gemma4:26b"

# Resolution targets for the agent frontmatter (model: haiku|sonnet|opus).
# opus   -> orchestrator / unit-tester / coder / integration-tester
# sonnet -> review, validation and documentation agents
# haiku  -> file-finder / test-runner / build-executor and background work
$env:ANTHROPIC_DEFAULT_OPUS_MODEL = "gemma4:26b"
$env:ANTHROPIC_DEFAULT_SONNET_MODEL = "gemma4:26b"
$env:ANTHROPIC_DEFAULT_HAIKU_MODEL = "gemma4:e4b"

# Pin every subagent to one model instead (useful when memory is tight):
# $env:CLAUDE_CODE_SUBAGENT_MODEL = "gemma4:e4b"

# --- back to the Claude models ---------------------------------------------
# Remove-Item Env:ANTHROPIC_BASE_URL, Env:ANTHROPIC_AUTH_TOKEN, Env:ANTHROPIC_MODEL, `
#   Env:ANTHROPIC_DEFAULT_OPUS_MODEL, Env:ANTHROPIC_DEFAULT_SONNET_MODEL, `
#   Env:ANTHROPIC_DEFAULT_HAIKU_MODEL
