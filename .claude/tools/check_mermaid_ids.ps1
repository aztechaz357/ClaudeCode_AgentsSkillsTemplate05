# check_mermaid_ids.ps1 - fast, toolchain-free check of mermaid flowchart ids.
#
# WHY THIS EXISTS
#   The full syntax check (check_diagrams.ps1 -> mmdc) is correct but costs
#   about 5 seconds per file and needs a node toolchain, so it is not run on
#   every edit. A template shipped with `presentation.{name}["..."]` in a node
#   id and stayed broken until a human opened it: mermaid reads `{` as another
#   shape and fails to parse. This check catches that class of breakage in
#   milliseconds so the PostToolUse hook can run it on every Markdown write.
#
#   It checks the shape of ids only. Full grammar validation stays in
#   check_diagrams.ps1 (run it when writing a design document, and before L3).
#
# WHAT IT REJECTS (flowchart / graph blocks only)
#   1. `{` or `}` in a node id  - placeholders belong inside the quoted label
#   2. non-ASCII node id        - ids must be module paths so that the design
#                                 diagram can be compared with the generated
#                                 one (see skills/architecture-drift)
#   3. unbalanced brackets on a line
#
# NOTE: This script is ASCII-only on purpose (PowerShell 5.1 / BOM-less UTF-8).
#
# Usage:
#   powershell -File .claude/tools/check_mermaid_ids.ps1 -Path <file.md|dir>
# Exit code: 0 = no findings (also when there is no mermaid block)
#            1 = findings
#            2 = the path does not exist / no Markdown file under it
param(
    [Parameter(Mandatory = $true)][string]$Path
)

$ErrorActionPreference = "Stop"

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

# Lines that declare style or structure, not nodes.
$skipPrefixes = @("classDef", "class ", "style ", "linkStyle", "subgraph", "end", "%%", "click ", "direction ")

function Test-Ascii([string]$value) {
    foreach ($char in $value.ToCharArray()) {
        if ([int]$char -gt 127) { return $false }
    }
    return $true
}

function Get-Findings([string]$text) {
    $findings = @()
    $lines = $text -split "`r?`n"
    $inBlock = $false
    $isFlowchart = $false
    $number = 0

    foreach ($line in $lines) {
        $number++
        $trimmed = $line.Trim()

        if (-not $inBlock) {
            if ($trimmed -match '^```\s*mermaid\s*$') {
                $inBlock = $true
                $isFlowchart = $false
            }
            continue
        }
        if ($trimmed -match '^```') {
            $inBlock = $false
            continue
        }
        if ($trimmed -eq "") { continue }

        # The diagram kind is declared on the first content line of the block.
        if (-not $isFlowchart) {
            if ($trimmed -match '^(flowchart|graph)\b') { $isFlowchart = $true }
            continue
        }

        $skip = $false
        foreach ($prefix in $skipPrefixes) {
            if ($trimmed.StartsWith($prefix)) { $skip = $true }
        }
        if ($skip) { continue }

        # Labels are free text (Japanese, braces, parentheses are all fine
        # inside them), so remove quoted spans before looking at ids.
        $bare = [regex]::Replace($trimmed, '"[^"]*"', '')

        # 1. a brace that does not directly follow an id character is a
        #    placeholder written into the id itself.
        foreach ($match in [regex]::Matches($bare, '\{')) {
            $before = ""
            if ($match.Index -gt 0) { $before = $bare.Substring($match.Index - 1, 1) }
            if ($before -notmatch '^[A-Za-z0-9_]$') {
                $findings += "    L${number}: brace in node id (put {placeholders} inside the quoted label): " + $trimmed
                break
            }
        }

        # 2. the token in front of a shape opener is a node id; it must be ASCII.
        foreach ($match in [regex]::Matches($bare, '([^\s\[\]\(\)\{\}\|<>=-]+)\s*[\[\(]')) {
            $id = $match.Groups[1].Value
            if (-not (Test-Ascii $id)) {
                $findings += "    L${number}: non-ASCII node id '" + $id + "' (write the Japanese in the label): " + $trimmed
                break
            }
        }

        # 3. brackets must balance on a single line.
        $pairs = @(@('[', ']'), @('(', ')'), @('{', '}'))
        foreach ($pair in $pairs) {
            $open = ([regex]::Matches($bare, [regex]::Escape($pair[0]))).Count
            $close = ([regex]::Matches($bare, [regex]::Escape($pair[1]))).Count
            if ($open -ne $close) {
                $findings += "    L${number}: unbalanced '" + $pair[0] + $pair[1] + "': " + $trimmed
                break
            }
        }
    }
    return $findings
}

try {
    if (-not (Test-Path -LiteralPath $Path)) {
        [Console]::Error.WriteLine("check_mermaid_ids: path not found: " + $Path)
        exit 2
    }

    $targets = @()
    if (Test-Path -LiteralPath $Path -PathType Container) {
        # -Include is unreliable with -LiteralPath + -Recurse (it let a .pyc
        # through in practice), so filter on the extension explicitly.
        $targets = Get-ChildItem -LiteralPath $Path -Recurse -File |
            Where-Object { $_.Extension -eq ".md" -or $_.Extension -eq ".markdown" } |
            Where-Object { $_.FullName -notmatch '\\(node_modules|\.git|\.venv|__pycache__)\\' }
    } else {
        $targets = @(Get-Item -LiteralPath $Path)
    }

    if ($targets.Count -eq 0) {
        [Console]::Error.WriteLine("check_mermaid_ids: no Markdown file under: " + $Path)
        exit 2
    }

    $bad = 0
    foreach ($target in $targets) {
        $text = [System.IO.File]::ReadAllText($target.FullName, [System.Text.Encoding]::UTF8)
        $findings = Get-Findings $text
        if ($findings.Count -gt 0) {
            $bad++
            [Console]::Out.WriteLine("NG: " + $target.FullName + " (" + $findings.Count + ")")
            foreach ($finding in $findings) { [Console]::Out.WriteLine($finding) }
        }
    }

    if ($bad -gt 0) {
        [Console]::Out.WriteLine("RESULT: " + $bad + " of " + $targets.Count + " files NG")
        exit 1
    }
    [Console]::Out.WriteLine("RESULT: all " + $targets.Count + " files OK")
    exit 0
} catch {
    [Console]::Error.WriteLine("check_mermaid_ids: " + $_.Exception.Message)
    exit 2
}
