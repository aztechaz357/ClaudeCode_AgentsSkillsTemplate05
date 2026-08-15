# Authoring .drawio XML

A `.drawio` file is native mxGraphModel XML. On builds without Mermaid support
this is the only authoring route, so the coordinates are yours to compute.

## Structure

```xml
<mxGraphModel adaptiveColors="auto">
  <root>
    <mxCell id="0"/>
    <mxCell id="1" parent="0"/>
  </root>
</mxGraphModel>
```

- `id="0"` is the root layer, `id="1"` the default parent layer.
- Every diagram element takes `parent="1"` unless it belongs to another layer.

A vertex and an edge between two vertices:

```xml
<mxCell id="a" value="入力" style="rounded=0;whiteSpace=wrap;html=1;" vertex="1" parent="1">
  <mxGeometry x="40" y="40" width="160" height="40" as="geometry"/>
</mxCell>
<mxCell id="b" value="出力" style="rounded=0;whiteSpace=wrap;html=1;" vertex="1" parent="1">
  <mxGeometry x="40" y="160" width="160" height="40" as="geometry"/>
</mxCell>
<mxCell id="e1" value="結果" edge="1" parent="1" source="a" target="b">
  <mxGeometry relative="1" as="geometry"/>
</mxCell>
```

Edges must not be self-closing — an `mxCell` with `edge="1"` and no
`<mxGeometry relative="1" as="geometry"/>` child renders nothing.

## Laying out by hand

Without `--layout` (see `mermaid-and-layout.md`), pick coordinates yourself:

- Keep a constant column x and a constant row pitch (e.g. 120 px) so edges stay
  straight and the diagram reads as a grid.
- Standard vertex size is 120×60; widen rather than wrap long Japanese labels.
- For a top-to-bottom flow, increase `y` monotonically; branches get symmetric
  `x` offsets around the parent's centre.
- Add `edgeStyle=orthogonalEdgeStyle;rounded=0;` to an edge's style when a
  connector needs to turn corners instead of cutting across the canvas.

## Full reference

For the complete draw.io XML reference — common styles, edge routing,
containers, layers, tags, metadata, dark-mode colors, and well-formedness rules
— fetch and follow:

https://raw.githubusercontent.com/jgraph/drawio-mcp/main/shared/xml-reference.md

## Well-formedness (hard rules)

- **Never emit XML comments (`<!-- -->`).** They waste tokens, can break the
  parser, and carry no diagram meaning.
- Escape `&amp;`, `&lt;`, `&gt;`, `&quot;` in attribute values — unescaped `&`
  in a label is the most common cause of a corrupt export.
- Every `mxCell` needs a unique `id`.
- Validate the file parses before exporting; an invalid `.drawio` produces an
  empty or corrupt output with a message that does not name the real cause.
