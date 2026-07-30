# Tests for port-check.
#
# Workshop-lane tools are test-first: this file was written before main.ps1
# did anything, and the Red run is recorded in README.md.
#
# ASCII-only (see main.ps1 for the PowerShell 5.1 reason).
#
# Exit code: 0 = all checks passed / 1 = a check failed
$ErrorActionPreference = "Continue"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$entry = Join-Path $here "main.ps1"

$failed = 0

function Check([string]$name, [bool]$ok, [string]$detail) {
    if ($ok) {
        Write-Output "OK: $name"
    } else {
        Write-Output "NG: $name -- $detail"
        $script:failed = 1
    }
}

# Bind port 0 to let the OS hand out a free port, then keep listening.
function New-Listener {
    $l = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::Loopback, 0)
    $l.Start()
    return $l
}

# --- 1. open port -> exit 0 and reports OPEN ---
$listener = New-Listener
$openPort = $listener.LocalEndpoint.Port
try {
    $out = & powershell -NoProfile -File $entry -Target 127.0.0.1 -Port $openPort 2>&1
    $code = $LASTEXITCODE
} finally {
    $listener.Stop()
}
Check "open port exits 0" ($code -eq 0) "exit=$code out=$out"
Check "open port reports OPEN" ("$out" -match "OPEN") "out=$out"

# --- 2. closed port -> exit 1 and reports CLOSED ---
# Reuse the port we just released: nothing is listening on it any more.
$closedPort = $openPort
$out = & powershell -NoProfile -File $entry -Target 127.0.0.1 -Port $closedPort -TimeoutMs 300 2>&1
$code = $LASTEXITCODE
Check "closed port exits 1" ($code -eq 1) "exit=$code out=$out"
Check "closed port reports CLOSED" ("$out" -match "CLOSED") "out=$out"

# --- 3. port out of range -> exit 2 (argument error) ---
$out = & powershell -NoProfile -File $entry -Target 127.0.0.1 -Port 0 2>&1
$code = $LASTEXITCODE
Check "port 0 is an argument error" ($code -eq 2) "exit=$code out=$out"

# --- 4. non-positive timeout -> exit 2 (argument error) ---
$out = & powershell -NoProfile -File $entry -Target 127.0.0.1 -Port 80 -TimeoutMs 0 2>&1
$code = $LASTEXITCODE
Check "timeout 0 is an argument error" ($code -eq 2) "exit=$code out=$out"

if ($failed -eq 0) {
    Write-Output "RESULT: all checks passed"
} else {
    Write-Output "RESULT: failures found"
}
exit $failed
