# check_py_names.ps1 - refuse non-ASCII Python function names.
#
# Python accepts non-ASCII identifiers, but a Japanese function name is
# unreadable the moment the output leaves UTF-8. Measured case: unittest
# reported a failure as "test_???{???..." on a cp932 console, so the one
# thing a failing test must tell you - which test failed - was lost.
#
# The rule: identifiers are ASCII, explanations go in the docstring
# (unittest -v prints the first line of the docstring next to the name).
#
# What counts as a definition:
#   a line matching  ^\s*(async\s+)?def\s+<name>
# Lines inside triple-quoted blocks are skipped, so a "def" shown as an
# example inside a docstring never registers.
#
# NOTE: This script is ASCII-only on purpose. PowerShell 5.1 parses a
# BOM-less UTF-8 .ps1 as ANSI, and multi-byte characters in comments can
# swallow the following newline and corrupt the next statement.
# (Lesson recorded in .claude/skills/tool-authoring/SKILL.md)
#
# Usage:     powershell -File .claude/tools/check_py_names.ps1 -Path <file.py|dir>
# Exit code: 0 = all files OK (also when no .py file is found)
#            1 = at least one file NG
#            2 = argument / environment error
param(
    [Parameter(Mandatory = $true)][string]$Path
)

$ErrorActionPreference = "Stop"

# Findings carry the offending name, which is non-ASCII by definition.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

function Write-Line([string]$text) { [Console]::Out.WriteLine($text) }

if (-not (Test-Path $Path)) {
    Write-Line "ERROR: path not found: $Path"
    exit 2
}

$item = Get-Item -LiteralPath $Path
if ($item.PSIsContainer) {
    $skip = '\\(\.venv|\.git|node_modules|dist|build|__pycache__|' +
            '\.pytest_cache|\.ruff_cache|\.mypy_cache|\.steering)\\'
    $files = @(
        Get-ChildItem -LiteralPath $item.FullName -Recurse -Filter *.py -File |
            Where-Object { $_.FullName -notmatch $skip }
    )
} else {
    $files = @($item)
}

if ($files.Count -eq 0) {
    Write-Line "NO-FILE: $Path"
    exit 0
}

$DEF = '^\s*(?:async\s+)?def\s+([^\s(:]+)'
$NON_ASCII = '[^\x00-\x7F]'
$DELIMS = @('"""', "'''")

$ngFiles = @()
$defCount = 0

foreach ($file in $files) {
    $text = [System.IO.File]::ReadAllText($file.FullName, [System.Text.Encoding]::UTF8)
    $lines = $text -split "`r?`n"

    $findings = @()
    $inBlock = $false
    $delim = ""

    for ($i = 0; $i -lt $lines.Count; $i++) {
        $line = $lines[$i]

        if ($inBlock) {
            # The closing delimiter ends the block; be conservative and do not
            # look for a definition on the closing line itself.
            if ($line.Contains($delim)) { $inBlock = $false; $delim = "" }
            continue
        }

        if ($line -match $DEF) {
            $name = $matches[1]
            $defCount++
            if ($name -match $NON_ASCII) {
                $findings += ("    L" + ($i + 1) + ": def " + $name)
            }
        }

        # An odd number of delimiters on a line opens a block that the
        # following lines continue (a matched pair opens and closes here).
        foreach ($d in $DELIMS) {
            $hits = ([regex]::Matches($line, [regex]::Escape($d))).Count
            if ($hits % 2 -eq 1) { $inBlock = $true; $delim = $d; break }
        }
    }

    if ($findings.Count -gt 0) {
        Write-Line ("NG: " + $file.FullName + " (" + $findings.Count + ")")
        foreach ($f in $findings) { Write-Line $f }
        $ngFiles += $file.FullName
    }
}

if ($ngFiles.Count -gt 0) {
    Write-Line ("RESULT: " + $ngFiles.Count + " of " + $files.Count +
                " files NG: " + ($ngFiles -join ", "))
    Write-Line ("HINT: rename the identifier to ASCII and put the Japanese " +
                "explanation in the docstring (unittest -v shows its first line).")
    exit 1
}

Write-Line ("RESULT: all " + $files.Count + " files OK (" + $defCount + " definitions)")
exit 0
