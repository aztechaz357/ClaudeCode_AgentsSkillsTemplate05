# post-edit-lint.ps1 - PostToolUse hook: run the project formatter / linter on
# the file that was just edited.
#
# The command itself is project specific, so it is passed in from
# settings.json (the command table in the CLAUDE.md profile is the source
# of truth):
#
#   powershell -NoProfile -File .claude/hooks/post-edit-lint.ps1
#       -Command "uv run ruff format" -Extensions "py"
#
# The edited file path is appended to -Command as a quoted argument.
# Advisory by default; pass -Blocking to fail the tool call when the command
# returns non-zero (exit 2 feeds stderr back to Claude).
#
# NOTE: This script is ASCII-only on purpose (PowerShell 5.1 / BOM-less UTF-8).
#
# Exit code: 0 = ran (or skipped), 2 = command failed with -Blocking,
#            1 = hook itself failed (non-blocking)
param(
    [Parameter(Mandatory = $true)][string]$Command,
    [string]$Extensions = "py|ts|tsx|js|jsx|go|rs|java|cs",
    [switch]$Blocking
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "lib-hook.ps1")
Set-HookOutputUtf8

try {
    $input_json = Read-HookPayload
    if (-not $input_json) { exit 0 }

    $file = [string]$input_json.tool_response.filePath
    if (-not $file) { $file = [string]$input_json.tool_input.file_path }
    if (-not $file) { exit 0 }
    if ($file -notmatch ("\.(" + $Extensions + ")$")) { exit 0 }
    if (-not (Test-Path -LiteralPath $file)) { exit 0 }

    $line = $Command + ' "' + $file + '"'
    $output = Invoke-Expression $line 2>&1
    if ($LASTEXITCODE -eq 0) { exit 0 }

    $detail = ($output | Out-String).Trim()

    if ($Blocking) {
        [Console]::Error.WriteLine($Command + " failed for " + $file + "`n" + $detail)
        exit 2
    }

    $payload = @{
        systemMessage = $Command + " reported problems in " + $file
        hookSpecificOutput = @{
            hookEventName = "PostToolUse"
            additionalContext = ($Command + " on " + $file + " returned a non-zero exit code. " +
                "Fix it before finishing the task.`n" + $detail)
        }
    }
    [Console]::Out.WriteLine(($payload | ConvertTo-Json -Depth 5 -Compress))
    exit 0
} catch {
    [Console]::Error.WriteLine("post-edit-lint: " + $_.Exception.Message)
    exit 1
}
