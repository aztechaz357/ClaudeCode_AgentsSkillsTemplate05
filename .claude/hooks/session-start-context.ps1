# session-start-context.ps1 - SessionStart hook: inject the deterministic
# facts of the working tree into the session as context.
#
# Treating the environment as the source of truth (CLAUDE.md absolute rule 1)
# is cheaper when it is read once at the start instead of guessed.
# This hook reports:
#   - current branch and number of uncommitted entries
#   - the last commit
#   - whether CLAUDE.md still contains {} placeholders (profile not filled in)
#   - the most recent .steering/ working directory
#
# NOTE: This script is ASCII-only on purpose (PowerShell 5.1 / BOM-less UTF-8).
#
# Usage (settings.json):
#   powershell -NoProfile -File .claude/hooks/session-start-context.ps1
# Exit code: 0 always (1 only if the hook itself fails)
param(
    [string]$SteeringDir = ".steering"
)

$ErrorActionPreference = "Stop"

# Native commands (git) emit UTF-8; PowerShell 5.1 would otherwise decode them
# with the console code page and mangle non-ASCII commit subjects.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

try {
    $null = [Console]::In.ReadToEnd()

    $lines = @()

    $branch = & git rev-parse --abbrev-ref HEAD 2>$null
    if ($LASTEXITCODE -eq 0 -and $branch) {
        $lines += "branch: " + $branch.Trim()

        $status = & git status --porcelain 2>$null
        $count = 0
        foreach ($line in ($status -split "`r?`n")) {
            if ($line.Trim() -ne "") { $count++ }
        }
        $lines += "uncommitted entries: " + $count

        $head = & git log -1 --oneline 2>$null
        if ($head) { $lines += "HEAD: " + ($head | Select-Object -First 1) }
    }

    if (Test-Path -LiteralPath "CLAUDE.md") {
        $claude = [System.IO.File]::ReadAllText("CLAUDE.md", [System.Text.Encoding]::UTF8)
        if ($claude.Contains("{")) {
            $lines += "WARNING: CLAUDE.md still contains {} placeholders - the project profile is not filled in. Run /setup-project before development."
        }
    } else {
        $lines += "WARNING: CLAUDE.md not found - agents have no project profile to read."
    }

    if (Test-Path -LiteralPath $SteeringDir) {
        $latest = Get-ChildItem -LiteralPath $SteeringDir -Directory -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending | Select-Object -First 1
        if ($latest) { $lines += "latest steering dir: " + (Join-Path $SteeringDir $latest.Name) }
    }

    # local mode (driving Claude Code with a local open-weight model) changes
    # how every agent works, so it must survive a lost conversation.
    $localMode = Join-Path $SteeringDir "local-mode.md"
    if (Test-Path -LiteralPath $localMode) {
        $lines += "LOCAL MODE IS ON: follow .claude/local-llm/policy.md (one task per turn, stop and report, no unattended loops). Turn it off with /local-mode off."
    }

    if ($lines.Count -eq 0) { exit 0 }

    $payload = @{
        hookSpecificOutput = @{
            hookEventName = "SessionStart"
            additionalContext = ("Working tree facts at session start (read from the environment, not from memory):`n- " +
                ($lines -join "`n- "))
        }
    }
    [Console]::Out.WriteLine(($payload | ConvertTo-Json -Depth 5 -Compress))
    exit 0
} catch {
    [Console]::Error.WriteLine("session-start-context: " + $_.Exception.Message)
    exit 1
}
