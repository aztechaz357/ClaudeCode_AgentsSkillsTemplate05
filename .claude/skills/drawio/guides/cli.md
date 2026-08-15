# draw.io CLI: locating, flags, exporting, opening

The draw.io desktop app ships a command-line interface. It is required for
**exporting** to PNG/SVG/PDF, and (on builds that support them) for **Mermaid
conversion** and **ELK layouts** — see `mermaid-and-layout.md`.

## Which shell

This project's primary shell is PowerShell, but every command below is written
for **bash** (the Bash tool runs Git Bash on this machine). Run them there.
Where PowerShell differs in a way that silently breaks the command, the
PowerShell form is given alongside — do not translate by hand:

- PowerShell has no `$(cmd)`-into-argument quirk, but it **does** treat
  `node -e '...'` single quotes as literal strings that never expand, and it
  splits `--%`-style native arguments differently. Use the given form.
- `2>&1` on a native exe in Windows PowerShell 5.1 wraps stderr lines in
  ErrorRecords and flips `$?` even on exit 0. Do not add it.

## Locating the CLI

Detect the environment first, then use the matching path.

### Windows (native) — this machine

```bash
DRAWIO="/c/Program Files/draw.io/draw.io.exe"          # Git Bash
```

```powershell
$drawio = "C:\Program Files\draw.io\draw.io.exe"        # PowerShell
```

Per-user install, if the above does not exist:
`C:\Users\<user>\AppData\Local\Programs\draw.io\draw.io.exe`

### WSL2

WSL2 is detected when `/proc/version` contains `microsoft` or `WSL`:

```bash
grep -qi microsoft /proc/version 2>/dev/null && echo "WSL2"
```

Use the Windows executable through `/mnt/c/...`:

```bash
DRAWIO="/mnt/c/Program Files/draw.io/draw.io.exe"
```

Double-quote the path so the space in `Program Files` stays part of the path.
Do **not** wrap it in backticks — in bash those are command substitution, which
would execute the binary at locate-time instead of storing its path.

### macOS

```bash
/Applications/draw.io.app/Contents/MacOS/draw.io
```

### Linux (native)

```bash
drawio   # typically on PATH via snap/apt/flatpak
```

Check `which drawio` (bash) or `(Get-Command draw.io).Source` (PowerShell)
before falling back to a platform-specific path.

## Capability probe

Builds differ in what the CLI accepts. Probe before choosing an authoring
route (see the SKILL.md table for what was measured here):

```bash
"$DRAWIO" --help | grep -c -- "--layout"
```

`0` means no ELK layout and no Mermaid input — author as XML with explicit
coordinates.

## Export

```bash
"$DRAWIO" -x -f <format> -e -b 10 -o "<output>" "<input.drawio>"
```

Windows (native) example, verified on 29.7.9:

```bash
"/c/Program Files/draw.io/draw.io.exe" -x -f png -e -b 10 -o "diagram.drawio.png" "diagram.drawio"
```

```powershell
& "C:\Program Files\draw.io\draw.io.exe" -x -f png -e -b 10 -o "diagram.drawio.png" "diagram.drawio"
```

A successful run prints `input -> output` and exits 0. Confirm the output file
exists before reporting success — the CLI prints `Error: ...` and still exits 0
in some failure modes.

Key flags:

- `-x` / `--export`: export mode (also used for layout passes and, on
  supporting builds, Mermaid conversion)
- `-f` / `--format`: `xml`, `png`, `svg`, `pdf`, `jpg`, `html`. Ignored if the
  output filename already carries the extension. Use `xml` to write a
  `.drawio`
- `-e` / `--embed-diagram`: embed the diagram XML in the output (PNG, SVG, PDF
  only) — this is what keeps the export editable
- `-o` / `--output`: output file path
- `-b` / `--border`: border width around the diagram (default 0)
- `-t` / `--transparent`: transparent background (PNG only)
- `-s` / `--scale`: scale the diagram size
- `--width` / `--height`: fit into the given dimension, preserving aspect ratio
- `-a` / `--all-pages`: export all pages (PDF, HTML)
- `-p` / `--page-index`: select a page (1-based)
- `-u` / `--uncompressed`: uncompressed XML output (XML and SVG only) — useful
  when the `.drawio` should stay diff-readable in git
- `-k` / `--check`: do not overwrite existing files
- `--crop`: crop the PDF to the diagram size

Flags that exist only on newer builds (`--layout`, `--mermaid-image`) are
covered in `mermaid-and-layout.md`. Passing an unknown flag does not error
cleanly: its value is taken as the input filename, producing
`Error: input file/directory not found`.

## Opening the result

| Environment | Command |
|-------------|---------|
| Windows (native) | `start "" "<file>"` (cmd) / `Invoke-Item <file>` (PowerShell) |
| macOS | `open <file>` |
| Linux (native) | `xdg-open <file>` |
| WSL2 | `cmd.exe /c start "" "$(wslpath -w <file>)"` |

WSL2 notes:

- `wslpath -w <file>` converts `/home/user/diagram.drawio` to a Windows path.
  `cmd.exe` cannot resolve `/mnt/c/...` style paths.
- The empty `""` after `start` prevents `start` from reading the filename as a
  window title.

If the open command fails, print the absolute path so the user can open it
manually. Never report a diagram as delivered without either opening it or
printing its path.
