# post-edit-markdown.ps1 - PostToolUse hook: verify a Markdown file right
# after Claude writes it.
#
# Runs the numbering checker (and optionally the diagram checker) on the file
# that was just edited, so CLAUDE.md rules 7 and 8 are enforced by the harness
# instead of by remembering to run the tools.
#
# Default is advisory: findings are injected back to the model as context and
# shown to the user, but the turn is not blocked. Pass -Blocking to fail the
# tool call instead (exit code 2 feeds stderr back to Claude and forces a fix).
#
# NOTE: This script is ASCII-only on purpose (PowerShell 5.1 / BOM-less UTF-8).
#
# Usage (settings.json):
#   powershell -NoProfile -File .claude/hooks/post-edit-markdown.ps1
#   powershell -NoProfile -File .claude/hooks/post-edit-markdown.ps1 -Diagrams -Blocking
# Exit code: 0 = checked (findings, if any, reported as JSON on stdout)
#            2 = findings, with -Blocking (stderr is fed back to Claude)
#            1 = hook itself failed (non-blocking)
param(
    [switch]$Diagrams,
    [switch]$Blocking,
    [string]$NumberingTool = ".claude/tools/check_numbering.ps1",
    [string]$DiagramTool = ".claude/tools/check_diagrams.ps1"
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "lib-hook.ps1")
Set-HookOutputUtf8

function Invoke-Checker([string]$tool, [string]$target) {
    if (-not (Test-Path -LiteralPath $tool)) { return $null }
    $output = & powershell -NoProfile -File $tool -Path $target 2>&1
    if ($LASTEXITCODE -eq 0) { return $null }
    return (($output | Out-String).Trim())
}

try {
    $input_json = Read-HookPayload
    if (-not $input_json) { exit 0 }

    $file = [string]$input_json.tool_response.filePath
    if (-not $file) { $file = [string]$input_json.tool_input.file_path }
    if (-not $file) { exit 0 }
    if ($file -notmatch '\.(md|markdown)$') { exit 0 }
    if (-not (Test-Path -LiteralPath $file)) { exit 0 }

    $root = [string]$input_json.cwd
    if (-not $root) { $root = (Get-Location).Path }

    $findings = @()

    $numbering = Invoke-Checker (Join-Path $root $NumberingTool) $file
    if ($numbering) { $findings += "check_numbering NG:`n" + $numbering }

    if ($Diagrams) {
        $diagram = Invoke-Checker (Join-Path $root $DiagramTool) $file
        if ($diagram) { $findings += "check_diagrams NG:`n" + $diagram }
    }

    if ($findings.Count -eq 0) { exit 0 }

    $detail = ($findings -join "`n`n")

    if ($Blocking) {
        [Console]::Error.WriteLine("Markdown verification failed for " + $file + "`n" + $detail)
        exit 2
    }

    $payload = @{
        systemMessage = "Markdown verification reported findings in " + $file
        hookSpecificOutput = @{
            hookEventName = "PostToolUse"
            additionalContext = ("Verification of " + $file + " reported findings. " +
                "Fix them before finishing the task (CLAUDE.md rules 7 and 8).`n" + $detail)
        }
    }
    [Console]::Out.WriteLine(($payload | ConvertTo-Json -Depth 5 -Compress))
    exit 0
} catch {
    [Console]::Error.WriteLine("post-edit-markdown: " + $_.Exception.Message)
    exit 1
}
