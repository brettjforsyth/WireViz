# WireViz extended features

This fork adds harness-engineering, manufacturing, sourcing, and rendering
capabilities on top of upstream WireViz. Everything below runs from the parsed
harness model and, except the standard Graphviz outputs, needs no `dot` binary.

All features are exposed on the `wireviz` CLI and are also importable.

## CLI quick reference

```
wireviz harness.yml [options]

  -f, --format TEXT       Graphviz outputs: g gv, h html, p png, s svg, t tsv
      --drc / --no-drc    Run design-rule checks and print a report (default on)
      --strict            Exit non-zero if DRC finds errors
      --grid              Write a native grid-snapped SVG   (<name>.grid.svg)
      --viewer            Write an interactive HTML viewer   (<name>.viewer.html)
      --json              Write the harness layout as JSON    (<name>.layout.json)
      --cutsheet FMT      Write a wire cut sheet, FMT = tsv|csv|html
      --source DIST       Enrich the BOM via a distributor, DIST = digikey|mouser
```

Example — no Graphviz needed:

```
wireviz harness.yml -f "" --grid --viewer --cutsheet csv --json
```

## Design-rule checking (`wv_drc`)

Runs a registry of rules over the harness and prints severity-ranked findings.
`--strict` makes errors fail the build (useful in CI). Structural rules:
`E-CONN-UNKNOWN`, `E-PIN-UNKNOWN`, `E-WIRE-RANGE` (catches the silent wire-0
wrap), `E-SHIELD-ABSENT`, `W-WIRE-UNUSED`, `W-WIRE-OPEN-END`,
`W-PIN-UNCONNECTED`, `W-LABEL-COUNT`, `W-NO-GAUGE`, `W-ZERO-LENGTH`, `I-NO-MPN`.

### Electrical checks (`wv_electrical`)

Active when a cable declares a `current` (amps). Neither ezwire.app nor
harness.design does current-based checking.

- `E-AMPACITY` — current exceeds the gauge's ampacity (conservative chassis
  table; resistance computed from AWG geometry).
- `W-AMPACITY-MARGIN` — within 90% of ampacity.
- `W-VDROP` — voltage drop > 5% of the circuit voltage (needs `voltage` too).

```yaml
cables:
  W1:
    gauge: 18 AWG
    length: 5
    current: 10      # amps  -> ampacity + drop checks
    voltage: 12      # volts -> % voltage drop
```

## Wire cut sheets (`wv_cutsheet`)

Per-wire cut list: wire id, from/to endpoints (with pin labels), color, gauge,
cut length, unit, label; plus bulk length totals per gauge. Cut length uses
real manufacturing allowances: `cable length + insertion allowance per
terminated end + slack`, scaled by an optional twist factor, floored to a
minimum, and rounded to a stock increment (up/down/nearest). Outputs TSV/CSV/HTML.

## BOM sourcing (`wv_sourcing`)

Enriches BOM part numbers with live distributor data — unit price, price
breaks, stock, datasheet/product links, lifecycle — from **DigiKey** (Product
Information API v4) or **Mouser** (Search API v1). Picks the right price break
for each quantity and totals the extended cost. Results are cached to
`<name>.sourcing-cache.json`. Without credentials it writes an un-priced BOM.

```
export DIGIKEY_CLIENT_ID=...   DIGIKEY_CLIENT_SECRET=...
export MOUSER_API_KEY=...
wireviz harness.yml -f "" --source digikey
```

## Native grid renderer (`wv_svg`)

Lays connectors and cables out in layered left-to-right columns, snaps every
coordinate to a configurable grid (`GridConfig.pitch`), and routes wires as
orthogonal grid-aligned polylines. Renders a connector's `image` (real
footprint/photo) in its node. No `dot` dependency. `build_layout()` /
`export_json()` produce the machine-readable layout that feeds the viewer.

## Interactive viewer (`wv_viewer`)

A single self-contained HTML file (no CDN, fonts, or external fetches — works
offline) with pan, zoom, a snap-grid toggle, fit-to-view, and wire hover
highlighting. The layout JSON is embedded, so the file is also a portable data
carrier. `--viewer3d` additionally writes a three.js 3D view (orbit/zoom;
needs internet for the CDN).

## 1:1 formboard (`wv_formboard`)

`--formboard A4|A3|A2|A1|A0|letter|tabloid` writes a **life-size** formboard SVG
(`<name>.formboard.svg`): connectors placed at physical positions (columns
spaced by cable length), each cable drawn as an orthogonal bundle run labelled
with its exact length, connector mounting pegs, and a dashed page grid showing
how the board tiles across sheets of the chosen size. The SVG's `width`/`height`
carry a `mm` suffix, so printing at 100% gives a true 1:1 template you can tape
to a board and build the harness on top of. Geometry is exact for the common
linear/tree harness; bundles that can't span a forced gap are flagged `⚠ SHORT`.

## Device library (`wv_devices`)

Reusable multi-connector device templates (a generic ECU, ISO relay, 3-wire
sensor, power-distribution block) expand into connectors with pin labels
pre-filled — the biggest time-saver from the commercial tools. Reference them
in a `devices:` section:

```yaml
devices:
  ECU1: generic_ecu_26     # -> connectors ECU1_A, ECU1_B
  S1: sensor_3             # -> connector S1
connections:
  -
    - ECU1_B: [TPS]
    - W1: [1]
    - S1: [SIG]
```

`wireviz --list-devices` prints the library; `register_device()` adds your own.
Only generic pinouts ship (no proprietary manufacturer cavity maps).

## Connector types + CAD renderings (`wv_connectors`)

A connector can declare a `connector_type`, which is used two ways: it
back-fills metadata (manufacturer, pin count, gender) from a generic library,
and it is the key used to pull the connector's **2D image and 3D CAD model**
into the renderers.

```yaml
options:
  connector_type: deutsch_dt_4   # optional global default
connectors:
  X1:
    connector_type: deutsch_dt_4  # -> 4 pins, TE, socket, + CAD assets
```

Asset resolution order (first hit wins per asset):

1. a local file you provide, named `<connector_type><ext>` in `--cad-dir`
   (2D: `.png/.jpg/.svg/.webp`; 3D: `.glb/.gltf/.step/.stl`);
2. an asset reference stored on the library entry;
3. an `image_provider` callback (e.g. a distributor product photo).

The grid SVG (`--grid`) draws the resolved image; the 3D viewer (`--viewer3d`)
loads the resolved glTF model, falling back to a block. `wireviz
--list-connectors` prints the library; `register_connector()` adds your own.

Only generic metadata ships — **no proprietary manufacturer CAD or images are
bundled.** You supply the actual assets via `--cad-dir` or a provider; the
library only knows how to find and describe them.

## Engineering & manufacturing suite

A block of calculators and exporters (each importable and, where it produces a
file, on the CLI):

- **Nets & netlist** (`wv_nets`, `--netlist`) — electrical nets through cables,
  splices, and mates; export as text, CSV, or a KiCad-style netlist; flags
  floating (single-pin) nodes.
- **Bundle diameter & fill** (`wv_bundle`) — wire OD → bundle OD → conduit/sleeve
  fill %, with a NEC-style limit and a smallest-sleeve recommendation.
- **Gauge recommender** (`wv_electrical.recommend_gauge`) — thinnest AWG that
  meets both ampacity and a voltage-drop budget for a given current and length.
- **Weight & length** (`wv_weight`) — copper + insulation mass and total
  conductor length per cable and for the whole harness.
- **Cost / quote** (`wv_quote`) — wire-by-length + connector materials + labour
  (crimp/connector counts) + markup, from a caller-supplied price book.
- **Mate DRC** (`wv_drc`) — mated connectors must have equal pin counts
  (`E-MATE-PINCOUNT`) and opposing genders (`W-MATE-GENDER`).
- **Wire markers** (`wv_markers`, `--markers`) — per-end labels (which wire,
  where it goes) as label-software CSV and a printable SVG label sheet.
- **Assembly traveler** (`wv_assembly`, `--traveler`) — ordered build steps:
  cut/strip → populate cavities → sleeve → mate.
- **Revision diff** (`wv_diff`, `--diff other.yml`) — added/removed/changed
  connectors, cables, and wires between two revisions.
- **DXF export** (`wv_dxf`, `--dxf`) — the formboard as a layered R12 DXF for CAD
  and cutting machines.

`--report` prints a quick engineering summary (weight, net count, per-cable
bundle diameter + recommended sleeve) to the console.

- **Accessories & coverings** (`wv_accessories`, `--accessories`) — connectors
  and cables declare contacts, seals, locks, boots, backshells, dust covers, and
  coverings (braided sleeve, spiral wrap, tubing, corrugated tube, heatshrink,
  tape). Quantities are stated or derived per pin / per connector / per length,
  then rolled into an accessory BOM grouped by type + MPN.
- **Importers** (`wv_import`, `--import wirelist|kicad`) — bootstrap a harness
  from a from/to wire-list CSV (with header aliases; one cable per connector
  pair) or a KiCad netlist (components → connectors, nets → wires).
- **Harness dossier** (`wv_dossier`, `--dossier`) — one self-contained HTML build
  package: diagram, cut sheet (with ident bands), engineering summary,
  bundle/sleeve table, accessory BOM, and assembly traveler.
- **Wire-processing machine export** (`wv_machine`, `--cutmachine`) — a cut/strip
  machine job CSV (article, cut length in mm, strip lengths, seals, marker).
- **Twisted pairs** (`twisting:` on a cable) — a Twist column on the cut sheet
  and the twist length factor applied only to the twisted wires.
- **Bundle derating** (`wv_electrical.bundle_derating`, DRC `W-BUNDLE-DERATE`) —
  ampacity derated by conductor count for wires bundled together.
- **Pinout cards** (`wv_pinout`, `--pinout`) — a printable HTML card per
  connector: every pin with its label, wire, and destination.
- **Drag-to-edit viewer** (`wv_editor`, `--editor`) — a browser editor that
  renders the harness from data so you can drag connectors: nodes snap to the
  grid, wires re-route live between the moved pins, and the edited layout
  exports as JSON. Self-contained and offline.

## Still to come

True three.js 3D view; a channel router guaranteeing zero wire overlap on dense
harnesses; per-pin footprint anchor coordinates; a device/ECU pin-map library;
and security hardening of the HTML/template path (see the security audit notes).
