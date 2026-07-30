# check_diagrams.ps1 - extract every diagram block from Markdown and validate
# each one with its native toolchain.
#
# Supersedes check_mermaid.ps1 (which only handled mermaid). Handles:
#   ```mermaid              -> mermaid-cli   (npx @mermaid-js/mermaid-cli)
#   ```plantuml|puml|uml    -> plantuml -checkonly
#   ```dot|graphviz         -> dot -Tsvg
#
# Blocks are written to a temp dir as UTF-8 without BOM so that Japanese
# labels survive; plantuml is invoked with -charset UTF-8 for the same reason.
#
# NOTE: This script is ASCII-only on purpose. PowerShell 5.1 parses a
# BOM-less UTF-8 .ps1 as ANSI, and multi-byte characters in comments can
# swallow the following newline and corrupt the next statement.
# (Lesson recorded in .claude/skills/tool-authoring/SKILL.md)
#
# Usage:     powershell -File .claude/tools/check_diagrams.ps1 -Path <file.md|dir>
# Exit code: 0 = all blocks OK (also when no diagram exists)
#            1 = at least one block NG
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

$stamp = Get-Date -Format "yyyyMMddHHmmss"
$workDir = Join-Path $env:TEMP ("check-diagrams-" + $stamp)
New-Item -ItemType Directory -Force $workDir | Out-Null

$utf8NoBom = New-Object System.Text.UTF8Encoding $false

function Write-Block {
    # Persist a block as UTF-8 without BOM and return the path.
    param([string]$Content, [string]$Extension, [int]$Index)

    $path = Join-Path $workDir ("block-" + $Index + $Extension)
    [System.IO.File]::WriteAllText($path, $Content, $utf8NoBom)
    return $path
}

$script:OnWindows = ($env:OS -eq "Windows_NT")

function Invoke-Quiet {
    # Run a toolchain command, discard its output, return the exit code.
    # On Windows the call goes through cmd: redirecting a native command's
    # stderr directly in PS 5.1 raises NativeCommandError records.
    # On Linux / macOS (dev container) there is no cmd, so the command is
    # invoked directly with the same arguments.
    param([string]$WindowsLine, [string]$File, [string[]]$Arguments)

    if ($script:OnWindows) {
        cmd /c $WindowsLine
        return $LASTEXITCODE
    }

    $null = & $File @Arguments 2>&1
    return $LASTEXITCODE
}

function Test-Block {
    # Validate one block. Returns $true when the toolchain accepts it.
    param([string]$Language, [string]$Content, [int]$Index)

    switch ($Language) {
        "mermaid" {
            $src = Write-Block -Content $Content -Extension ".mmd" -Index $Index
            $out = Join-Path $workDir ("block-" + $Index + ".svg")
            $code = Invoke-Quiet `
                -WindowsLine "npx -y @mermaid-js/mermaid-cli -i `"$src`" -o `"$out`" >nul 2>nul" `
                -File "npx" -Arguments @("-y", "@mermaid-js/mermaid-cli", "-i", $src, "-o", $out)
            return ($code -eq 0 -and (Test-Path $out))
        }
        "plantuml" {
            $body = $Content
            if ($body -notmatch '@start') { $body = "@startuml`n" + $body + "`n@enduml" }
            $src = Write-Block -Content $body -Extension ".puml" -Index $Index
            $code = Invoke-Quiet `
                -WindowsLine "plantuml -charset UTF-8 -checkonly `"$src`" >nul 2>nul" `
                -File "plantuml" -Arguments @("-charset", "UTF-8", "-checkonly", $src)
            return ($code -eq 0)
        }
        "dot" {
            $src = Write-Block -Content $Content -Extension ".dot" -Index $Index
            $out = Join-Path $workDir ("block-" + $Index + ".svg")
            $code = Invoke-Quiet `
                -WindowsLine "dot -Tsvg `"$src`" -o `"$out`" >nul 2>nul" `
                -File "dot" -Arguments @("-Tsvg", $src, "-o", $out)
            return ($code -eq 0 -and (Test-Path $out))
        }
    }
    return $false
}

# Fence tag -> canonical language name.
$langMap = @{
    "mermaid"  = "mermaid"
    "plantuml" = "plantuml"
    "puml"     = "plantuml"
    "uml"      = "plantuml"
    "dot"      = "dot"
    "graphviz" = "dot"
}

$pattern = '(?s)```(mermaid|plantuml|puml|uml|dot|graphviz)\r?\n(.*?)```'

$failedFiles = @()
$totalBlocks = 0
$index = 0

foreach ($file in $files) {
    $text = [System.IO.File]::ReadAllText($file.FullName, [System.Text.Encoding]::UTF8)
    $blocks = [regex]::Matches($text, $pattern)

    $rel = Resolve-Path -LiteralPath $file.FullName -Relative
    if ($rel -like "..*") { $rel = $file.FullName }

    if ($blocks.Count -eq 0) {
        if (-not $scanDir) { Write-Output ("NO-BLOCK: " + $rel) }
        continue
    }

    $ng = @()
    $seen = @()
    foreach ($block in $blocks) {
        $index++
        $totalBlocks++
        $tag = $block.Groups[1].Value.ToLower()
        $lang = $langMap[$tag]
        $seen += $lang
        if (-not (Test-Block -Language $lang -Content $block.Groups[2].Value -Index $index)) {
            $ng += ("block " + ($seen.Count) + " (" + $lang + ")")
        }
    }

    $summary = ($seen | Group-Object | ForEach-Object { $_.Name + " " + $_.Count }) -join ", "
    if ($ng.Count -eq 0) {
        Write-Output ("OK: " + $rel + " (" + $summary + ")")
    } else {
        Write-Output ("NG: " + $rel + " (" + $summary + ")")
        foreach ($n in $ng) { Write-Output ("    " + $n) }
        Write-Output ("    sources kept in: " + $workDir)
        $failedFiles += $rel
    }
}

if ($failedFiles.Count -gt 0) {
    Write-Output (
        "RESULT: " + $failedFiles.Count + " of " + $files.Count + " files NG: " + ($failedFiles -join ", ")
    )
    exit 1
}
Write-Output ("RESULT: all " + $files.Count + " files OK (" + $totalBlocks + " diagram blocks)")
exit 0
