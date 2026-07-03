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
carrier.

## Still to come

True three.js 3D view; a channel router guaranteeing zero wire overlap on dense
harnesses; per-pin footprint anchor coordinates; a device/ECU pin-map library;
and security hardening of the HTML/template path (see the security audit notes).
