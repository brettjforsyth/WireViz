# Rendering roadmap: grid-snapped wires + 2D/3D components

Status: **proposal, awaiting approval** (no feature code written yet).
Author: architecture audit, 2026-07-03.

Goal: add (a) **grid-snapped orthogonal wire routing** and (b) **2D — and later
3D — renderings of real components** (connector footprints/photos with wires
terminating at true pin positions), on top of today's Graphviz-based pipeline.

## Why this needs a new rendering path

Today the entire visual is produced by Graphviz (`Harness.create_graph()` in
`src/wireviz/Harness.py`), which owns node placement, wire routing (splines),
and the striped-wire look. There are **no coordinates anywhere in the data
model**. Consequences established by the audit:

- **Grid snapping is not achievable inside Graphviz.** `splines=ortho` ignores
  the HTML-label port anchors WireViz relies on, so wires stop hitting the
  correct pins, and it breaks multi-color edges and edge labels. Grid routing
  requires either post-processing Graphviz's output geometry or replacing the
  layout stage.
- **2D/3D component views require a geometry-aware model.** The current `Image`
  dataclass (`DataClasses.py`) is decorative — one `<img>` cell — with no
  concept of where a pin sits on the image, so wires cannot anchor to it.

Two facts make this tractable:

1. Parsing **enforces strict connector → cable → connector alternation**
   (`wireviz.py`), so layout is a rank-structured column problem, far simpler
   than general graph layout.
2. `wireviz.parse(inp, return_types="harness")` returns the **fully populated
   data model before any Graphviz call** — a clean seam for a parallel renderer.
   Raw YAML attribs are forwarded into `Connector(**attribs)`, so new fields
   (e.g. `footprint:`) need **zero parser changes**.

## Phases

### Phase 0 — Safety net + model serialization  *(partially done)*

- [x] Golden-master regression tests over all 27 example/tutorial `.gv` outputs
      (`tests/test_examples_golden.py`). This is the guardrail for everything below.
- [ ] Add a JSON serializer for the `Harness` model (`asdict`-based; the
      dataclasses are already `asdict`-friendly and `wv_bom.py` uses `asdict`).
      Emit connectors, cables, `Connection` records, mates, options, and the BOM
      (`harness.bom()`). This is the single feed for both the grid router and the
      2D/3D renderers, and is independently useful (machine-readable harness export).
- [ ] Extract the model-iteration in `create_graph()` from its string-emission so
      a renderer interface exists and Graphviz becomes one backend among several.

### Phase 1 — Grid-snapped orthogonal wires  *(weeks; keeps upstream compat)*

Approach: **post-process the geometry**, don't replace Graphviz yet.

- Render with Graphviz to get node/pin positions: `graph.pipe(format="json")`
  gives node + port coordinates; or parse the SVG (every wire is a
  `<g class="edge">` path with stable endpoints).
- Replace each spline with a **Manhattan polyline snapped to a configurable grid
  pitch**, preserving the pin endpoints. Because the graph is rank-structured
  (columns of connectors/cables), a simple **channel router** between adjacent
  ranks avoids overlaps — assign each wire a vertical channel, snap x/y to the grid.
- Hook in exactly where `svgembed.embed_svg_images()` already post-processes the
  finished SVG (`Harness.output()` / the `svg` property).
- New `options.grid` (pitch, on/off) — additive, defaults preserve current output
  so the golden tests stay green unless grid mode is enabled.

Deliverable: orthogonal, grid-aligned wires with pins still accurate. Does **not**
by itself deliver 2D/3D — that's Phase 2.

Risk: naive endpoint-preserving reroutes overlap without the channel router;
budget most of the phase for the router. `pyavoid`/libavoid is a fallback if the
hand-rolled router struggles.

### Phase 2 — 2D component footprints  *(the model-driven renderer)*

- Extend `Connector` (and optionally `Cable`) with a `footprint:` field carrying
  per-pin anchor coordinates + an asset (SVG symbol or photo). Free via the kwargs
  pass-through seam — no parser change.
- Build a renderer fed by the Phase 0 JSON that: places connector footprints as
  real 2D graphics, positions pins at their true anchor coordinates, and routes
  wires (reusing the Phase 1 grid router) to terminate at those anchors.
- Ship behind the Phase 0 renderer interface so Graphviz remains the default/legacy
  backend and existing diagrams are unaffected.
- Reuse `harness.bom()` in the same order so `#N` BOM cross-references stay valid.

### Phase 3 — 3D viewer  *(optional, later)*

- A three.js/HTML viewer served the Phase 0 JSON (extend the HTML template, which
  today only receives a baked SVG). Connectors become 3D component models; wires
  become tubes between pin anchors. Purely additive interactive output.

## Recommended sequencing

Do Phase 0 fully first (safety net + JSON feed + renderer seam), ship Phase 1 as a
quick, upstream-compatible win, then grow Phases 2–3 behind the same interface.
Approaches that skip the model work (Graphviz `splines=ortho`) are dead ends and do
not reach 2D/3D under any circumstances.

## Open decisions for the owner

- Track/scope: phased (recommended) vs. full custom renderer up front vs. grid-wires-only.
- 3D: commit to it now (informs the JSON schema) or defer.
- Footprint asset format: SVG symbols (crisp, themeable) vs. photos (realistic) vs. both.
