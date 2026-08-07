# lib-hook.ps1 - shared helpers for the hooks in this directory.
#
# Dot-source it right after the param() block of a hook:
#   . (Join-Path $PSScriptRoot "lib-hook.ps1")
#
# Why this file exists: reading the payload correctly on Windows takes more
# than [Console]::In.ReadToEnd(), and the same wrong three lines were copied
# into every hook - so every hook failed at once. One definition, one fix.
#
# NOTE: This script is ASCII-only on purpose (PowerShell 5.1 / BOM-less UTF-8).

function Read-HookPayload {
    # Claude Code writes the payload to stdin as UTF-8, but [Console]::In
    # decodes with [Console]::InputEncoding - the OEM code page (cp932 on a
    # Japanese Windows). Decoding UTF-8 as cp932 consumes bytes in pairs, and
    # a lead byte can swallow the following ASCII byte: after an odd-length
    # run of Japanese text, "\\Users" becomes "\Users" and ConvertFrom-Json
    # fails with "Unrecognized escape sequence". Read the raw stream instead,
    # so the console code page never applies.
    #
    # Returns the parsed payload, or $null when stdin was empty.
    $stream = [Console]::OpenStandardInput()
    $reader = New-Object System.IO.StreamReader(
        $stream, (New-Object System.Text.UTF8Encoding($false)), $true)
    try { $raw = $reader.ReadToEnd() } finally { $reader.Dispose() }
    if (-not $raw) { return $null }
    return ($raw | ConvertFrom-Json)
}

function Set-HookOutputUtf8 {
    # Claude Code reads hook stdout as UTF-8, and child processes emit UTF-8
    # too. Without this, non-ASCII in what we print (paths, findings, commit
    # subjects) is encoded with the console code page and arrives mangled.
    try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
}
