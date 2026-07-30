# new_note.ps1 - scaffold a workshop-lane note.
#
# Creates workshop/notes/<yyyy-MM-dd>-<slug>.md from
# .claude/templates/workshop/note.md, with YAML front matter that
# index_workshop.ps1 turns into workshop/notes/INDEX.md.
#
# NOTE: This script is ASCII-only on purpose (PowerShell 5.1 parses a
# BOM-less UTF-8 .ps1 as ANSI and multi-byte comment characters can corrupt
# the next statement). Japanese text lives in the template, read as UTF-8.
#
# Usage:
#   powershell -File .claude/tools/new_note.ps1 -Title <title>
#                    [-Slug <kebab-slug>] [-Tags "a,b"] [-Root workshop]
#
# -Slug is optional for ASCII titles (it is derived from the title). For a
# Japanese title there is nothing to derive from, so -Slug is required and
# its absence is an argument error rather than a silently odd file name.
#
# Exit code: 0 = created
#            1 = refused (a note with that date and slug already exists)
#            2 = argument / environment error
param(
    [Parameter(Mandatory = $true)][string]$Title,
    [string]$Slug = "",
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

if ([string]::IsNullOrWhiteSpace($Title)) {
    Write-Output "ERROR: -Title must not be empty"
    exit 2
}

if ([string]::IsNullOrWhiteSpace($Slug)) {
    $derived = $Title.ToLowerInvariant()
    $derived = [System.Text.RegularExpressions.Regex]::Replace($derived, '[^a-z0-9]+', '-')
    $derived = $derived.Trim('-')
    if ($derived.Length -lt 2) {
        Write-Output "ERROR: cannot derive a slug from the title; pass -Slug explicitly"
        Write-Output "HINT: -Slug is a short ASCII kebab-case name, e.g. -Slug ps51-encoding"
        exit 2
    }
    $Slug = $derived
}

if ($Slug -notmatch '^[a-z0-9]+(-[a-z0-9]+)*$') {
    Write-Output "ERROR: -Slug must be lower-case kebab-case (got: $Slug)"
    exit 2
}

$templatePath = Join-Path $PSScriptRoot "..\templates\workshop\note.md"
if (-not (Test-Path $templatePath)) {
    Write-Output "ERROR: template not found: $templatePath"
    exit 2
}

$date = Get-Date -Format "yyyy-MM-dd"
$notesDir = Join-Path $Root "notes"
$notePath = Join-Path $notesDir "$date-$Slug.md"

if (Test-Path $notePath) {
    Write-Output "REFUSED: already exists: $notePath"
    Write-Output "HINT: append to the existing note, or pass a different -Slug."
    exit 1
}

$tagList = ($Tags -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }) -join ", "

$text = Read-Utf8 $templatePath
$text = $text.Replace("{{TITLE}}", $Title)
$text = $text.Replace("{{DATE}}", $date)
$text = $text.Replace("{{TAGS}}", $tagList)

New-Item -ItemType Directory -Path $notesDir -Force | Out-Null
Write-Utf8 $notePath $text

Write-Output "CREATED: $notePath"
Write-Output "RESULT: note '$Title' scaffolded"
Write-Output "NEXT: fill in the note, then run index_workshop.ps1 to refresh INDEX.md."
exit 0
