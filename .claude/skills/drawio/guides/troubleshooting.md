# Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| `Error: Export failed: <file>.mmd` | The installed build does not accept Mermaid input (measured on 29.7.9 here) | Author the same diagram as XML with explicit coordinates (`xml.md`). Probe with `--help \| grep -c -- "--layout"` before choosing the Mermaid route |
| `Error: input file/directory not found` on a `--layout` call | The flag does not exist on this build, so its value was taken as the input filename | Drop `--layout` and position cells yourself; updating draw.io Desktop is what enables layouts |
| draw.io CLI not found | Desktop app not installed or not on PATH | Author as XML and deliver a `.drawio` or a `url` (conversion, layout, and image export all need the desktop app). Tell the user installing draw.io Desktop enables the rest |
| Command prints `Error: ...` but exits 0 | The CLI does not always set a failure exit code | Check that the output file exists (and is non-empty) before reporting success |
| Mermaid → PNG export crashes | Direct `.mmd` → PNG with `-e` is broken in current draw.io Desktop (embedded-XML step) | Two-step path: convert to `.drawio` (`-f xml`), then export the `.drawio` |
| Blank diagram from Mermaid | Misspelled type keyword, or a syntax error (bad node ID, unquoted label) | Check the Mermaid reference in `mermaid-and-layout.md`; the first non-directive line's keyword selects the diagram type |
| Export produces empty/corrupt file | Invalid XML (double hyphens in comments, unescaped `&`) | Validate well-formedness before writing; see `xml.md` |
| Diagram opens but looks blank | Missing root cells `id="0"` and `id="1"` | Complete the basic mxGraphModel structure |
| Edges not rendering | The edge `mxCell` is self-closing (no child `mxGeometry`) | Give every edge `<mxGeometry relative="1" as="geometry" />` |
| File won't open after export | Wrong path or missing file association | Print the absolute path so the user can open it manually |
| Browser opens an empty diagram in `url` mode | `cmd.exe` stripped the `#create=...` fragment | Use the `.url` temp-file workaround (`browser-url.md`); never pass the URL straight to `cmd.exe /c start` |
| URL too long for the browser | Large diagram exceeds the URL length limit | Write the `.drawio` and open it locally instead |
| The diagram belongs in a design document | The 4 required figures are inline Mermaid, not `.drawio` | Stop and write a ` ```mermaid ` fence in the document (`writing-conventions/guides/diagrams.md`) |
