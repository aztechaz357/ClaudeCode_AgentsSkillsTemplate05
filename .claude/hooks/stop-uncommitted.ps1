# stop-uncommitted.ps1 - Stop hook: warn when the turn ends with uncommitted
# changes.
#
# CLAUDE.md rule 5 says every unit of work ends in a commit. This hook makes
# the omission visible instead of relying on memory.
#
# It never blocks: a Stop hook that returns decision "block" can loop the
# agent. If you want the stricter behaviour, see .claude/hooks/README.md.
#
# NOTE: This script is ASCII-only on purpose (PowerShell 5.1 / BOM-less UTF-8).
#
# Usage (settings.json):
#   powershell -NoProfile -File .claude/hooks/stop-uncommitted.ps1
# Exit code: 0 always (1 only if the hook itself fails)
param(
    [int]$Limit = 5
)

$ErrorActionPreference = "Stop"

# Native commands (git) emit UTF-8; PowerShell 5.1 would otherwise decode them
# with the console code page and mangle non-ASCII paths.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

try {
    $null = [Console]::In.ReadToEnd()

    $status = & git status --porcelain 2>$null
    if ($LASTEXITCODE -ne 0) { exit 0 }

    $lines = @()
    foreach ($line in ($status -split "`r?`n")) {
        if ($line.Trim() -ne "") { $lines += $line.Trim() }
    }
    if ($lines.Count -eq 0) { exit 0 }

    $shown = $lines | Select-Object -First $Limit
    $summary = ($shown -join "; ")
    if ($lines.Count -gt $Limit) {
        $summary = $summary + "; ... (" + ($lines.Count - $Limit) + " more)"
    }

    $payload = @{
        systemMessage = ("Uncommitted changes remain (" + $lines.Count +
            " entries): " + $summary + " - CLAUDE.md rule 5 asks for a commit per unit of work.")
    }
    [Console]::Out.WriteLine(($payload | ConvertTo-Json -Depth 5 -Compress))
    exit 0
} catch {
    [Console]::Error.WriteLine("stop-uncommitted: " + $_.Exception.Message)
    exit 1
}
