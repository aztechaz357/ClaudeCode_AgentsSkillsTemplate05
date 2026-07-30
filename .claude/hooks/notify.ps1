# notify.ps1 - Notification hook: make "Claude is waiting for you" audible.
#
# Claude Code raises a notification when it needs input (permission prompt,
# question) or has been idle. In a long autonomous run the terminal is usually
# not in focus, so a sound is the cheapest way to notice.
#
# Optionally appends the notification to a log file (-LogPath). The log is for
# reviewing how often a run stopped for input; keep it out of git.
#
# NOTE: This script is ASCII-only on purpose (PowerShell 5.1 / BOM-less UTF-8).
#
# Usage (settings.json):
#   powershell -NoProfile -File .claude/hooks/notify.ps1
#   powershell -NoProfile -File .claude/hooks/notify.ps1 -LogPath .steering/notifications.log
# Exit code: 0 always (1 only if the hook itself fails)
param(
    [int]$Frequency = 880,
    [int]$Duration = 200,
    [string]$LogPath = ""
)

$ErrorActionPreference = "Stop"

try {
    $raw = [Console]::In.ReadToEnd()
    $message = ""
    if ($raw) {
        $input_json = $raw | ConvertFrom-Json
        $message = [string]$input_json.message
    }

    try { [Console]::Beep($Frequency, $Duration) } catch { }

    if ($LogPath -ne "") {
        $stamp = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        $dir = Split-Path -Parent $LogPath
        if ($dir -ne "" -and -not (Test-Path -LiteralPath $dir)) {
            New-Item -ItemType Directory -Path $dir -Force | Out-Null
        }
        Add-Content -LiteralPath $LogPath -Value ($stamp + "  " + $message) -Encoding UTF8
    }

    exit 0
} catch {
    [Console]::Error.WriteLine("notify: " + $_.Exception.Message)
    exit 1
}
