# start-bridge.ps1 - start the Anthropic -> Ollama bridge for the EdgeXpert box.
#
# Runs in the foreground; Ctrl-C stops it. Start Claude Code from a SECOND
# shell after sourcing your env file (see env.example.ps1).
#
# NOTE: This script is ASCII-only on purpose (PowerShell 5.1 / BOM-less UTF-8).
#
# Usage:
#   powershell -NoProfile -File .claude\local-llm\start-bridge.ps1
#   powershell -NoProfile -File .claude\local-llm\start-bridge.ps1 -Python "uv run python"
param(
    [string]$Python = "python",
    [string]$Ollama = "http://192.168.11.17:11434",
    [string]$Listen = "127.0.0.1:8787",
    [string]$DefaultModel = "gemma4:26b",
    [string]$SmallModel = "gemma4:e4b"
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

$script = Join-Path $PSScriptRoot "ollama_bridge.py"
if (-not (Test-Path -LiteralPath $script)) {
    Write-Error "bridge script not found: $script"
    exit 2
}

Write-Output "checking Ollama at $Ollama ..."
try {
    $tags = Invoke-RestMethod -Uri "$Ollama/api/tags" -TimeoutSec 8
    Write-Output ("available models: " + (($tags.models | ForEach-Object { $_.name }) -join ", "))
} catch {
    Write-Error "cannot reach Ollama at $Ollama : $($_.Exception.Message)"
    exit 1
}

$parts = $Python.Split(" ")
$exe = $parts[0]
$prefix = @()
if ($parts.Length -gt 1) { $prefix = $parts[1..($parts.Length - 1)] }

& $exe @prefix $script --ollama $Ollama --listen $Listen `
    --default-model $DefaultModel --small-model $SmallModel
