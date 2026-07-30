# new_tool.ps1 - scaffold a workshop-lane tool.
#
# Creates workshop/tools/<name>/ from the templates in
# .claude/templates/workshop/:
#   README.md      the tool's manual (with YAML front matter for the catalog)
#   <entry>        the implementation stub
#   test_<name>.*  the test stub (Red: the stub is expected to fail)
#
# The workshop lane is still test-first, so the test file is always created.
#
# NOTE: This script is ASCII-only on purpose. PowerShell 5.1 parses a
# BOM-less UTF-8 .ps1 as ANSI, and multi-byte characters in comments can
# swallow the following newline and corrupt the next statement. All Japanese
# text lives in the templates, which are read as UTF-8 data.
# (Lesson recorded in .claude/skills/tool-authoring/SKILL.md)
#
# Usage:
#   powershell -File .claude/tools/new_tool.ps1 -Name <kebab-name>
#                    -Summary <one line> [-Lang py|ps1|sh] [-Tags "a,b"]
#                    [-Root workshop]
#
# Exit code: 0 = created
#            1 = refused (the tool directory already exists)
#            2 = argument / environment error
param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$Summary,
    [ValidateSet("py", "ps1", "sh")][string]$Lang = "py",
    [string]$Tags = "",
    [string]$Root = "workshop"
)

$ErrorActionPreference = "Stop"

function Read-Utf8([string]$p) {
    return [System.IO.File]::ReadAllText($p, [System.Text.UTF8Encoding]::new($false))
}

function Write-Utf8([string]$p, [string]$text) {
    [System.IO.File]::WriteAllText($p, $text, [System.Text.UTF8Encoding]::new($false))
}

if ($Name -notmatch '^[a-z0-9]+(-[a-z0-9]+)*$') {
    Write-Output "ERROR: -Name must be lower-case kebab-case (got: $Name)"
    exit 2
}

if ([string]::IsNullOrWhiteSpace($Summary)) {
    Write-Output "ERROR: -Summary must not be empty"
    exit 2
}

$templateDir = Join-Path $PSScriptRoot "..\templates\workshop"
if (-not (Test-Path $templateDir)) {
    Write-Output "ERROR: template directory not found: $templateDir"
    exit 2
}

$entryName = "main.$Lang"
$testName = "test_main.$Lang"
if ($Lang -eq "py") { $testName = "test_main.py" }

$mainTemplate = Join-Path $templateDir "tool-main.$Lang"
$testTemplate = Join-Path $templateDir "tool-test.$Lang"
$readmeTemplate = Join-Path $templateDir "tool-README.md"
foreach ($t in @($mainTemplate, $testTemplate, $readmeTemplate)) {
    if (-not (Test-Path $t)) {
        Write-Output "ERROR: template not found: $t"
        exit 2
    }
}

$toolDir = Join-Path (Join-Path $Root "tools") $Name
if (Test-Path $toolDir) {
    Write-Output "REFUSED: already exists: $toolDir"
    Write-Output "HINT: pick another name, or edit the existing tool directly."
    exit 1
}

$date = Get-Date -Format "yyyy-MM-dd"
$tagList = ($Tags -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }) -join ", "

function Expand-Template([string]$path) {
    $text = Read-Utf8 $path
    $text = $text.Replace("{{NAME}}", $Name)
    $text = $text.Replace("{{SUMMARY}}", $Summary)
    $text = $text.Replace("{{DATE}}", $date)
    $text = $text.Replace("{{TAGS}}", $tagList)
    $text = $text.Replace("{{LANG}}", $Lang)
    $text = $text.Replace("{{ENTRY}}", $entryName)
    return $text
}

New-Item -ItemType Directory -Path $toolDir -Force | Out-Null

$created = @()
try {
    $p = Join-Path $toolDir "README.md"
    Write-Utf8 $p (Expand-Template $readmeTemplate); $created += $p

    $p = Join-Path $toolDir $entryName
    Write-Utf8 $p (Expand-Template $mainTemplate); $created += $p

    $p = Join-Path $toolDir $testName
    Write-Utf8 $p (Expand-Template $testTemplate); $created += $p
} catch {
    # Roll back so a half-written tool directory never survives a failure.
    Remove-Item -LiteralPath $toolDir -Recurse -Force -ErrorAction SilentlyContinue
    Write-Output "ERROR: failed to write files, rolled back: $($_.Exception.Message)"
    exit 2
}

foreach ($c in $created) { Write-Output "CREATED: $c" }
Write-Output "RESULT: scaffolded '$Name' ($Lang, 3 files)"
Write-Output "NEXT: write the real test first, confirm Red, then implement."
exit 0
