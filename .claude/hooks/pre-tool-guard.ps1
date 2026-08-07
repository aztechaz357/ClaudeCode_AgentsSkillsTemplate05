# pre-tool-guard.ps1 - PreToolUse hook: deny edits to protected paths and
# deny destructive shell commands.
#
# Reads the hook payload (JSON) from stdin. Two pattern lists drive it:
#   .claude/hooks/protected_paths.txt   - file paths that must never be edited
#   .claude/hooks/denied_commands.txt   - shell command patterns to refuse
# Both are project specific; the tool itself is a template.
#
# Patterns are glob-like: everything is literal except '*' (any run of chars).
# Path patterns are anchored at the start of the repo-relative path.
# Command patterns match anywhere in the command line.
#
# NOTE: This script is ASCII-only on purpose. PowerShell 5.1 parses a
# BOM-less UTF-8 .ps1 as ANSI, and multi-byte characters in comments can
# swallow the following newline and corrupt the next statement.
# (Lesson recorded in .claude/skills/tool-authoring/SKILL.md)
#
# Usage (settings.json):
#   powershell -NoProfile -File .claude/hooks/pre-tool-guard.ps1
# Exit code: 0 = decided (allow silently, or deny via JSON on stdout)
#            1 = hook itself failed (non-blocking; message shown to the user)
param(
    [string]$ProtectedList = ".claude/hooks/protected_paths.txt",
    [string]$DeniedList = ".claude/hooks/denied_commands.txt"
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "lib-hook.ps1")
Set-HookOutputUtf8

function Read-Patterns([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) { return @() }
    $text = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
    $result = @()
    foreach ($line in ($text -split "`r?`n")) {
        $trimmed = $line.Trim()
        if ($trimmed -ne "" -and -not $trimmed.StartsWith("#")) {
            $result += $trimmed
        }
    }
    return $result
}

function ConvertTo-PatternRegex([string]$pattern, [bool]$anchored) {
    $escaped = [regex]::Escape($pattern)
    $escaped = $escaped -replace '\\\*', '.*'
    if ($anchored) { return "^" + $escaped }
    return $escaped
}

function Deny([string]$reason) {
    $payload = @{
        hookSpecificOutput = @{
            hookEventName = "PreToolUse"
            permissionDecision = "deny"
            permissionDecisionReason = $reason
        }
    }
    [Console]::Out.WriteLine(($payload | ConvertTo-Json -Depth 5 -Compress))
    exit 0
}

try {
    $input_json = Read-HookPayload
    if (-not $input_json) { exit 0 }

    $tool = [string]$input_json.tool_name
    $root = [string]$input_json.cwd
    if (-not $root) { $root = (Get-Location).Path }

    $protectedPath = Join-Path $root $ProtectedList
    $deniedPath = Join-Path $root $DeniedList

    if ($tool -eq "Bash" -or $tool -eq "PowerShell") {
        $command = [string]$input_json.tool_input.command
        if (-not $command) { exit 0 }
        foreach ($pattern in (Read-Patterns $deniedPath)) {
            if ($command -match (ConvertTo-PatternRegex $pattern $false)) {
                Deny ("Blocked by pre-tool-guard: the command matches the denied pattern '" +
                      $pattern + "' in " + $DeniedList + ". " +
                      "Destructive operations need explicit human confirmation " +
                      "(CLAUDE.md absolute rule 4). Ask the user to run it, or " +
                      "propose a non-destructive alternative.")
            }
        }
        exit 0
    }

    $file = [string]$input_json.tool_input.file_path
    if (-not $file) { exit 0 }

    $normalized = $file -replace '\\', '/'
    $rootNorm = ($root -replace '\\', '/').TrimEnd('/')
    if ($rootNorm -ne "" -and $normalized.ToLower().StartsWith($rootNorm.ToLower() + "/")) {
        $normalized = $normalized.Substring($rootNorm.Length + 1)
    }

    foreach ($pattern in (Read-Patterns $protectedPath)) {
        $normalizedPattern = $pattern -replace '\\', '/'
        if ($normalized -match (ConvertTo-PatternRegex $normalizedPattern $true)) {
            Deny ("Blocked by pre-tool-guard: '" + $normalized +
                  "' is a protected path (pattern '" + $normalizedPattern +
                  "' in " + $ProtectedList + "). Frozen documents and " +
                  "generated files must never be edited (CLAUDE.md rule 3). " +
                  "Report the needed change to the user instead.")
        }
    }

    exit 0
} catch {
    [Console]::Error.WriteLine("pre-tool-guard: " + $_.Exception.Message)
    exit 1
}
