# post-edit-python.ps1 - PostToolUse hook: verify a Python file right after
# Claude writes it.
#
# Runs the identifier checker on the file that was just edited, so the rule
# "identifiers are ASCII, explanations go in the docstring" is enforced by the
# harness instead of by remembering to run the tool.
#
# Why the rule exists: a Japanese function name is unreadable the moment the
# output leaves UTF-8. Measured case: unittest reported a failure as
# "test_???{???..." on a cp932 console, so the one thing a failing test must
# tell you - which test failed - was lost.
#
# Default is advisory: findings are injected back to the model as context and
# shown to the user, but the turn is not blocked. Pass -Blocking to fail the
# tool call instead (exit code 2 feeds stderr back to Claude and forces a fix).
#
# NOTE: This script is ASCII-only on purpose (PowerShell 5.1 / BOM-less UTF-8).
#
# Usage (settings.json):
#   powershell -NoProfile -File .claude/hooks/post-edit-python.ps1
#   powershell -NoProfile -File .claude/hooks/post-edit-python.ps1 -Blocking
# Exit code: 0 = checked (findings, if any, reported as JSON on stdout)
#            2 = findings, with -Blocking (stderr is fed back to Claude)
#            1 = hook itself failed (non-blocking)
param(
    [switch]$Blocking,
    [string]$NameTool = ".claude/tools/check_py_names.ps1"
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
    if ($file -notmatch '\.pyi?$') { exit 0 }
    if (-not (Test-Path -LiteralPath $file)) { exit 0 }

    $root = [string]$input_json.cwd
    if (-not $root) { $root = (Get-Location).Path }

    $names = Invoke-HookChecker (Join-Path $root $NameTool) $file
    if (-not $names) { exit 0 }

    $detail = "check_py_names NG:`n" + $names

    if ($Blocking) {
        [Console]::Error.WriteLine("Python verification failed for " + $file + "`n" + $detail)
        exit 2
    }

    $payload = @{
        systemMessage = "check_py_names reported findings in " + $file
        hookSpecificOutput = @{
            hookEventName = "PostToolUse"
            additionalContext = ("Verification of " + $file + " reported findings. " +
                "Rename the identifiers to ASCII and put the Japanese explanation " +
                "in the docstring, then continue.`n" + $detail)
        }
    }
    [Console]::Out.WriteLine(($payload | ConvertTo-Json -Depth 5 -Compress))
    exit 0
} catch {
    [Console]::Error.WriteLine("post-edit-python: " + $_.Exception.Message)
    exit 1
}
