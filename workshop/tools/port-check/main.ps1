# port-check - report whether a TCP port accepts a connection.
#
# Workshop-lane tool. README.md in this directory is the manual.
#
# NOTE: ASCII-only on purpose. PowerShell 5.1 parses a BOM-less UTF-8 .ps1
# as ANSI, and multi-byte characters in comments can swallow the following
# newline and corrupt the next statement. Write the Japanese explanation in
# README.md, not here.
#
# Exit code: 0 = open / 1 = closed or timed out / 2 = argument error
param(
    [string]$Target = "127.0.0.1",
    [int]$Port = 0,
    [int]$TimeoutMs = 1000
)

$ErrorActionPreference = "Stop"

# Fail closed on structurally wrong input, before touching the network.
if ([string]::IsNullOrWhiteSpace($Target)) {
    Write-Output "ERROR: -Target must not be empty"
    exit 2
}
if ($Port -lt 1 -or $Port -gt 65535) {
    Write-Output "ERROR: -Port must be 1-65535 (got $Port)"
    exit 2
}
if ($TimeoutMs -lt 1) {
    Write-Output "ERROR: -TimeoutMs must be 1 or more (got $TimeoutMs)"
    exit 2
}

$client = New-Object System.Net.Sockets.TcpClient
try {
    # TcpClient.Connect has no timeout, so wait on the async handle instead.
    $async = $client.BeginConnect($Target, $Port, $null, $null)
    if ($async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
        $client.EndConnect($async)
        Write-Output "OPEN: ${Target}:${Port}"
        exit 0
    }
    Write-Output "CLOSED: ${Target}:${Port} (timed out after ${TimeoutMs} ms)"
    exit 1
} catch {
    # Refused connection and name resolution failure both land here.
    Write-Output "CLOSED: ${Target}:${Port} ($($_.Exception.Message))"
    exit 1
} finally {
    $client.Close()
}
