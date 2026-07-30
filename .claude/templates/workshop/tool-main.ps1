# {{NAME}} - {{SUMMARY}}
#
# Workshop-lane tool. README.md in this directory is the manual.
#
# NOTE: ASCII-only on purpose. PowerShell 5.1 parses a BOM-less UTF-8 .ps1
# as ANSI, and multi-byte characters in comments can swallow the following
# newline and corrupt the next statement. Write the Japanese explanation in
# README.md, not here.
#
# Exit code: 0 = success / 1 = expected failure / 2 = argument error
param(
)

$ErrorActionPreference = "Stop"

throw "{{NAME}} is not implemented yet"
