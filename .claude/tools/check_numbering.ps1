# check_numbering.ps1 - verify equation / figure / table numbering in Markdown.
#
# Enforces CLAUDE.md "8. Notation rules" mechanically:
#   - duplicate numbers          (same number defined twice)
#   - gaps                       (numbering is not 1..N contiguous)
#   - unreferenced items         (defined but never cited in the body)
#   - dangling references        (cited but never defined)
#
# What counts as a definition:
#   equation : \tag{n} inside a $$ ... $$ block
#   figure   : a line starting with U+56F3 n ":"  (caption below the figure)
#   table    : a line starting with U+8868 n ":"  (caption above the table)
#
# What counts as a reference:
#   equation : U+5F0F (n)
#   figure   : U+56F3 n   (not followed by ":")
#   table    : U+8868 n   (not followed by ":")
# Ranges written with a wave dash (e.g. "(1) - (6)") expand to every number
# in between, so citing a span counts as citing each member.
#
# Fenced code blocks are ignored, so examples inside ``` ``` never register
# as definitions. Inline code spans are ignored for the same reason.
#
# NOTE: This script is ASCII-only on purpose. PowerShell 5.1 parses a
# BOM-less UTF-8 .ps1 as ANSI, and multi-byte characters in comments can
# swallow the following newline and corrupt the next statement.
# Japanese characters are therefore built from [char]0xNNNN code points.
# (Lesson recorded in .claude/skills/tool-authoring/SKILL.md)
#
# Usage:     powershell -File .claude/tools/check_numbering.ps1 -Path <file.md|dir>
# Exit code: 0 = all files OK (also when nothing is numbered)
#            1 = at least one file NG
#            2 = argument / environment error
param(
    [Parameter(Mandatory = $true)][string]$Path
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Path)) {
    Write-Output "ERROR: path not found: $Path"
    exit 2
}

$item = Get-Item -LiteralPath $Path
$scanDir = $item.PSIsContainer
if ($scanDir) {
    $skip = '\\(\.venv|\.git|node_modules|dist|build|\.pytest_cache|\.ruff_cache|\.mypy_cache|\.steering)\\'
    $files = @(
        Get-ChildItem -LiteralPath $item.FullName -Recurse -Filter *.md -File |
            Where-Object { $_.FullName -notmatch $skip }
    )
} else {
    $files = @($item)
}

if ($files.Count -eq 0) {
    Write-Output "NO-FILE: $Path"
    exit 0
}

# Japanese characters used by the notation rules, built from code points so
# that this file stays ASCII-only (see the NOTE in the header).
$EQ = [string][char]0x5F0F                          # equation marker
$FIG = [string][char]0x56F3                         # figure marker
$TBL = [string][char]0x8868                         # table marker
$COLON = ":" + [string][char]0xFF1A                 # ASCII + fullwidth colon
$LP = "\(" + [string][char]0xFF08                   # ASCII + fullwidth open paren
$RP = "\)" + [string][char]0xFF09                   # ASCII + fullwidth close paren
# wave dash, fullwidth tilde, ASCII hyphen (hyphen last so it stays literal)
$WAVE = [string][char]0x301C + [string][char]0xFF5E + "-"

# Per-kind patterns: definition, single reference, range reference.
$kinds = @(
    @{
        Name  = "equation"
        Def   = "\\tag\{\s*(\d+)\s*\}"
        Ref   = $EQ + "\s*[" + $LP + "]\s*(\d+)\s*[" + $RP + "]"
        Range = $EQ + "\s*[" + $LP + "]\s*(\d+)\s*[" + $RP + "]\s*[" + $WAVE + "]\s*(?:" +
                $EQ + "\s*)?[" + $LP + "]\s*(\d+)\s*[" + $RP + "]"
    },
    @{
        Name  = "figure"
        Def   = "^\s*(?:\*\*)?" + $FIG + "\s*(\d+)\s*[" + $COLON + "]"
        Ref   = $FIG + "\s*(\d+)(?!\s*[" + $COLON + "])"
        Range = $FIG + "\s*(\d+)\s*[" + $WAVE + "]\s*(?:" + $FIG + "\s*)?(\d+)"
    },
    @{
        Name  = "table"
        Def   = "^\s*(?:\*\*)?" + $TBL + "\s*(\d+)\s*[" + $COLON + "]"
        Ref   = $TBL + "\s*(\d+)(?!\s*[" + $COLON + "])"
        Range = $TBL + "\s*(\d+)\s*[" + $WAVE + "]\s*(?:" + $TBL + "\s*)?(\d+)"
    }
)

function Get-ScannableLines {
    # Return the file's lines with fenced code blocks blanked out and inline
    # code spans replaced by spaces. Line count is preserved so that reported
    # line numbers still match the original file.
    param([string]$FilePath)

    $text = [System.IO.File]::ReadAllText($FilePath, [System.Text.Encoding]::UTF8)
    $lines = $text -split "\r?\n"
    $inFence = $false
    $out = New-Object System.Collections.ArrayList

    foreach ($line in $lines) {
        if ($line -match '^\s*(```|~~~)') {
            $inFence = -not $inFence
            [void]$out.Add("")
            continue
        }
        if ($inFence) {
            [void]$out.Add("")
            continue
        }
        [void]$out.Add(($line -replace '`[^`]*`', ' '))
    }
    return $out
}

function Get-Hits {
    # Collect every number matched by $Pattern, with its line number.
    param([object[]]$Lines, [string]$Pattern)

    $hits = New-Object System.Collections.ArrayList
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        foreach ($m in [regex]::Matches($Lines[$i], $Pattern)) {
            [void]$hits.Add([pscustomobject]@{
                Num  = [int]$m.Groups[1].Value
                Line = $i + 1
            })
        }
    }
    return $hits
}

function Get-RangeNumbers {
    # Expand "a - b" spans into every number they cover.
    param([object[]]$Lines, [string]$Pattern)

    $nums = New-Object System.Collections.ArrayList
    foreach ($line in $Lines) {
        foreach ($m in [regex]::Matches($line, $Pattern)) {
            $from = [int]$m.Groups[1].Value
            $to = [int]$m.Groups[2].Value
            if ($from -le $to) {
                for ($n = $from; $n -le $to; $n++) { [void]$nums.Add($n) }
            }
        }
    }
    return $nums
}

$failedFiles = @()
$totalItems = 0

foreach ($file in $files) {
    # @(...) is required: PowerShell unrolls a single-element result, and a
    # lone PSCustomObject has no .Count on 5.1.
    $lines = @(Get-ScannableLines -FilePath $file.FullName)
    $issues = New-Object System.Collections.ArrayList
    $counts = @()

    foreach ($kind in $kinds) {
        $defs = @(Get-Hits -Lines $lines -Pattern $kind.Def)
        $refs = @(Get-Hits -Lines $lines -Pattern $kind.Ref)
        $rangeNums = @(Get-RangeNumbers -Lines $lines -Pattern $kind.Range)

        if ($defs.Count -eq 0 -and $refs.Count -eq 0) { continue }

        $counts += ($kind.Name + " " + $defs.Count)
        $totalItems += $defs.Count

        $defNums = @($defs | ForEach-Object { $_.Num })
        $refNums = @($refs | ForEach-Object { $_.Num }) + @($rangeNums)

        # 1. duplicate definitions
        foreach ($g in ($defs | Group-Object Num | Where-Object { $_.Count -gt 1 })) {
            $where = ($g.Group | ForEach-Object { "L" + $_.Line }) -join ", "
            [void]$issues.Add(
                "DUP   " + $kind.Name + " " + $g.Name + " defined " + $g.Count + " times (" + $where + ")"
            )
        }

        # 2. gaps in the sequence
        if ($defNums.Count -gt 0) {
            $max = ($defNums | Measure-Object -Maximum).Maximum
            $missing = @(1..$max | Where-Object { $defNums -notcontains $_ })
            if ($missing.Count -gt 0) {
                [void]$issues.Add(
                    "GAP   " + $kind.Name + " numbering is not 1.." + $max +
                    " contiguous; missing: " + ($missing -join ", ")
                )
            }
        }

        # 3. defined but never referenced
        foreach ($d in ($defs | Sort-Object Num -Unique)) {
            if ($refNums -notcontains $d.Num) {
                [void]$issues.Add(
                    "UNREF " + $kind.Name + " " + $d.Num + " (L" + $d.Line + ") is never cited in the body"
                )
            }
        }

        # 4. referenced but never defined
        foreach ($r in ($refs | Sort-Object Num -Unique)) {
            if ($defNums -notcontains $r.Num) {
                [void]$issues.Add(
                    "DANGL " + $kind.Name + " " + $r.Num + " (L" + $r.Line + ") is cited but not defined"
                )
            }
        }
    }

    # Prefer a repo-relative path, but fall back to the absolute one when the
    # file sits outside the current directory (avoids "..\..\..\.." noise).
    $rel = Resolve-Path -LiteralPath $file.FullName -Relative
    if ($rel -like "..*") { $rel = $file.FullName }
    if ($counts.Count -eq 0) {
        # In directory mode most files are prose with nothing numbered;
        # listing them all would bury the real findings.
        if (-not $scanDir) { Write-Output ("NO-ITEM: " + $rel) }
        continue
    }
    if ($issues.Count -eq 0) {
        Write-Output ("OK: " + $rel + " (" + ($counts -join ", ") + ")")
    } else {
        Write-Output ("NG: " + $rel + " (" + ($counts -join ", ") + ")")
        foreach ($issue in $issues) { Write-Output ("    " + $issue) }
        $failedFiles += $rel
    }
}

if ($failedFiles.Count -gt 0) {
    Write-Output (
        "RESULT: " + $failedFiles.Count + " of " + $files.Count + " files NG: " + ($failedFiles -join ", ")
    )
    exit 1
}
Write-Output ("RESULT: all " + $files.Count + " files OK (" + $totalItems + " numbered items)")
exit 0
