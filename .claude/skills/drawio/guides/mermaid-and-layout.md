# Mermaid authoring and ELK layout (newer desktop builds only)

> **Probe before reading further.** Everything on this page needs a desktop
> build whose CLI advertises `--layout`:
>
> ```bash
> "$DRAWIO" --help | grep -c -- "--layout"
> ```
>
> `0` — as measured on draw.io Desktop 29.7.9 here — means neither Mermaid
> conversion nor ELK layout exists on this machine. Author as XML with explicit
> coordinates and ignore this page. Do not "try anyway": a `.mmd` input fails
> with `Error: Export failed: <file>.mmd`, and an unknown `--layout` flag is
> swallowed as an input filename (`Error: input file/directory not found`).

## Mermaid → .drawio

On a supporting build, the CLI converts Mermaid to a native `.drawio` and lays
it out automatically, which is more reliable than hand-positioning cells.

1. Write the Mermaid to a `.mmd` file.
2. Convert:

   ```bash
   "$DRAWIO" -x -f xml -o diagram.drawio diagram.mmd
   ```

3. Delete the `.mmd` — the `.drawio` is the artifact.

No `--layout` is needed afterward: draw.io's Mermaid parser has already laid
the diagram out.

**Always convert first, then export.** Direct `.mmd` → PNG with `-e` is broken
in current draw.io Desktop (the embedded-XML step crashes). The two-step path
(convert to `.drawio`, then export that) is reliable and produces an editable
embed.

`--mermaid-image 1` converts Mermaid to a single static SVG image cell (the
Mermaid source stays on the cell for re-editing) instead of an editable
diagram. Use it only when the user explicitly asks for a non-editable image
cell.

### Mermaid syntax reference

Fetch and follow the shared reference (all supported diagram types plus
flowchart styling — `style`, `classDef`, `linkStyle`):

https://raw.githubusercontent.com/jgraph/drawio-mcp/main/shared/mermaid-reference.md

Match the language of the diagram labels to the user's language. In this
project that means Japanese labels (see SKILL.md).

## ELK layout for XML

XML-authored diagrams can be auto-positioned by the CLI's `--layout` pass — the
same ELK layouts as the editor's *Arrange ▸ Layout* menu. Generate the cells
with approximate (or `0,0`) positions and let ELK place them; only the graph
*structure* — nodes and edges — has to be right.

Lay out in place (reading and overwriting the same path is supported):

```bash
"$DRAWIO" -x -f xml --layout verticalFlow -o diagram.drawio diagram.drawio
```

Or combine layout and export in one call:

```bash
"$DRAWIO" -x -f png -e -b 10 --layout verticalFlow -o diagram.drawio.png diagram.drawio
```

### Layout presets

| Name | Layout |
|------|--------|
| `verticalFlow` | Layered, top-to-bottom — flowcharts, pipelines |
| `horizontalFlow` | Layered, left-to-right |
| `verticalTree` | Tree, top-down — hierarchies, org charts |
| `horizontalTree` | Tree, left-to-right |
| `radialTree` | Radial tree |
| `organic` | Force-directed — networks, mind-map-like graphs |

### Custom layout JSON

For finer control, pass a JSON **array** (starting with `[`) instead of a
preset name — the same format as the editor's custom-layout dialog:

```bash
"$DRAWIO" -x -f xml --layout '[{"layout":"elkLayered","config":{"elk.direction":"RIGHT"}}]' -o diagram.drawio diagram.drawio
```

Each entry is `{"layout": <algorithm>, "config": { … }}`:

- **Algorithms**: `elkLayered`, `elkTree`, `elkRadial`, `elkOrganic`,
  `elkStress`, `elkBox`.
- **`config`**: keys starting with `elk.` are ELK options — e.g.
  `elk.direction` (`UP` / `DOWN` / `LEFT` / `RIGHT`), `elk.spacing.nodeNode`,
  `elk.layered.spacing.nodeNodeBetweenLayers`. The keys `edgeStyle` (e.g.
  `orthogonal`) and `corners` (e.g. `rounded`) control connector rendering.

### Orthogonal edge routing

`--layout libavoid` routes the **edges** orthogonally around the shapes (the
editor's *Arrange ▸ Layout ▸ Orthogonal Routing*) without moving any vertex —
the complement of the node layouts above. Use it as an in-place pass on
hand-positioned XML whose connectors cross shapes:

```bash
"$DRAWIO" -x -f xml --layout libavoid -o diagram.drawio diagram.drawio
```

Skip it after a flow/tree preset — those already route their edges. Mermaid-
authored diagrams are already laid out; never add `--layout` to them.
