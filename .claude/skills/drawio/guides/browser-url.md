# Browser URL output

When the user asks for `url` format, build a draw.io URL that opens the diagram
directly in the browser editor at `app.diagrams.net`. Viewing needs no desktop
app — only Node.js, for the compression step.

## How it works

1. The `.drawio` file is written to disk as usual (a persistent local copy the
   user can re-edit).
2. The XML is compressed with Node.js's built-in `zlib` and base64-encoded.
3. The result is embedded in a `https://app.diagrams.net/#create=...` URL.
4. The URL is opened in the default browser.

Only Node.js built-ins (`zlib`, `child_process`) are used — no dependencies.

## Generating the URL

Run this `node -e` one-liner to read the `.drawio` and print the URL (replace
`DIAGRAM.drawio` with the real filename):

```bash
URL=$(node -e '
const fs = require("fs");
const zlib = require("zlib");
const xml = fs.readFileSync(process.argv[1], "utf8");
const compressed = zlib.deflateRawSync(encodeURIComponent(xml)).toString("base64");
const payload = encodeURIComponent(JSON.stringify({ type: "xml", compressed: true, data: compressed }));
console.log("https://app.diagrams.net/?grid=0&pv=0&border=10&edit=_blank#create=" + payload);
' "DIAGRAM.drawio")
```

The URL format matches the MCP Tool Server. `zlib.deflateRawSync` and
`pako.deflateRaw` both implement RFC 1951 and produce identical output, so URLs
from either source are interchangeable.

## Opening the URL

| Environment | Command |
|-------------|---------|
| macOS | `open "$URL"` |
| Linux (native) | `xdg-open "$URL"` |
| Windows (native) | Write a temp `.url` file, open via `start` (below) |
| WSL2 | Write a temp `.url` file, open via `cmd.exe` (below) |

**Why the `.url` workaround on Windows/WSL2?** `cmd.exe`'s `start` treats `&`
as a command separator and strips everything after `#` in URLs. The diagram
payload lives in the `#create=...` fragment, so passing the URL directly loses
it silently. A `.url` shortcut file preserves the URL intact.

### macOS / Linux

```bash
open "$URL"      # macOS
xdg-open "$URL"  # Linux
```

### WSL2

```bash
TMPFILE=$(mktemp --suffix=.url)
printf '[InternetShortcut]\r\nURL=%s\r\n' "$URL" > "$TMPFILE"
cmd.exe /c start "" "$(wslpath -w "$TMPFILE")"
```

### Windows (native)

Do **not** build the `.url` file with `echo URL=%URL%`. The URL contains `&`
characters (`?grid=0&pv=0&...`) that `cmd.exe` treats as command separators, so
the shortcut is written truncated and the payload is lost — the exact failure
the `.url` file exists to prevent. Let Node write the file (it already holds
the URL string) and open only the resulting path, which never contains `&`:

```bash
TMPFILE=$(node -e '
const fs = require("fs");
const os = require("os");
const path = require("path");
const p = path.join(os.tmpdir(), "drawio.url");
fs.writeFileSync(p, "[InternetShortcut]\r\nURL=" + process.argv[1] + "\r\n");
process.stdout.write(p);
' "$URL")
cmd.exe /c start "" "$TMPFILE"
```

In PowerShell the same two steps are:

```powershell
$tmp = Join-Path $env:TEMP "drawio.url"
Set-Content -LiteralPath $tmp -Encoding utf8 -Value "[InternetShortcut]`r`nURL=$url"
Invoke-Item $tmp
```

Opening a browser is an outward-facing action; the `.drawio` itself is not
uploaded — the whole diagram travels inside the URL fragment, which browsers do
not send to the server.

## After opening

Print the URL so the user can copy or share it, and confirm the local path:

```
Opened in browser: <URL>
Local file: DIAGRAM.drawio
```

The `.drawio` stays on disk so the diagram can be re-edited, attached
elsewhere, or exported to an image later.

## URL length

The URL embeds the whole compressed diagram in its hash fragment. Very large
diagrams may hit browser URL length limits (~32K–2MB depending on the browser).
When a diagram exceeds it, fall back to writing the `.drawio` and opening it
locally.
