# check_mermaid.ps1 - extract all ```mermaid blocks from a Markdown file
# and validate each with mermaid-cli.
#
# NOTE: This script is ASCII-only on purpose. PowerShell 5.1 parses a
# BOM-less UTF-8 .ps1 as ANSI, and multi-byte characters in comments can
# swallow the following newline and corrupt the next statement.
# (Lesson recorded in .claude/skills/tool-authoring/SKILL.md)
#
# Usage:     powershell -File .claude/tools/check_mermaid.ps1 -Path <file.md>
# Exit code: 0 = all blocks OK (also when no block exists)
#            1 = at least one block NG
#            2 = argument / environment error
param(
    [Parameter(Mandatory = $true)][string]$Path
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Path)) {
    Write-Output "ERROR: file not found: $Path"
    exit 2
}
$resolved = (Resolve-Path $Path).Path

# Read the Markdown as UTF-8 (Get-Content defaults to ANSI on PS 5.1).
$text = [System.IO.File]::ReadAllText($resolved, [System.Text.Encoding]::UTF8)
$blocks = [regex]::Matches($text, '(?s)```mermaid\r?\n(.*?)```')

if ($blocks.Count -eq 0) {
    Write-Output "NO-BLOCK: $Path"
    exit 0
}

$stamp = Get-Date -Format "yyyyMMddHHmmss"
$workDir = Join-Path $env:TEMP ("check-mermaid-" + $stamp)
New-Item -ItemType Directory -Force $workDir | Out-Null

$failed = @()
$index = 0
foreach ($block in $blocks) {
    $index++
    $mmd = Join-Path $workDir ("block-" + $index + ".mmd")
    $svg = Join-Path $workDir ("block-" + $index + ".svg")
    [System.IO.File]::WriteAllText(
        $mmd, $block.Groups[1].Value, (New-Object System.Text.UTF8Encoding $false)
    )
    # Run via cmd: redirecting a native command's stderr directly in PS 5.1
    # raises NativeCommandError records.
    cmd /c "npx -y @mermaid-js/mermaid-cli -i `"$mmd`" -o `"$svg`" >nul 2>nul"
    if ($LASTEXITCODE -eq 0 -and (Test-Path $svg)) {
        Write-Output ("OK: block " + $index)
    } else {
        Write-Output ("NG: block " + $index + " (" + $mmd + ")")
        $failed += $index
    }
}

if ($failed.Count -gt 0) {
    Write-Output ("RESULT: " + $failed.Count + " of " + $blocks.Count + " blocks NG: " + ($failed -join ", "))
    exit 1
}
Write-Output ("RESULT: all " + $blocks.Count + " blocks OK: " + $Path)
exit 0
