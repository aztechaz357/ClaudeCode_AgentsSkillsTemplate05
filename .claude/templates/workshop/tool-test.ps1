# Smoke test for {{NAME}}.
#
# Workshop-lane tools are still test-first: this file starts as a Red check
# and is replaced by real assertions once the tool does something.
#
# ASCII-only (see tool-main.ps1 for the PowerShell 5.1 reason).
#
# Exit code: 0 = all checks passed / 1 = a check failed
$ErrorActionPreference = "Continue"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$entry = Join-Path $here "{{ENTRY}}"

$failed = 0

# Red: the tool is expected to fail until it is implemented.
& powershell -NoProfile -File $entry *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Output "NG: {{NAME}} succeeded but is not implemented yet"
    $failed = 1
} else {
    Write-Output "OK: {{NAME}} fails as expected (not implemented)"
}

exit $failed
