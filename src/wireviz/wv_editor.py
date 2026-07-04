# -*- coding: utf-8 -*-
"""Interactive drag-to-edit harness viewer.

Unlike the read-only viewer (which embeds a static SVG), this renders the
harness from data in the browser so connectors can be dragged. Nodes snap to
the grid, wires re-route live between the moved pins, and the edited layout can
be exported as JSON. It is a single self-contained, offline HTML file.

The Python side (:func:`editor_data`) reuses the grid layout for initial node
positions and adds, for every wire segment, references to its two endpoint
nodes and pin indices so the browser can recompute pin positions after a drag.
"""

import json
from html import escape
from typing import Optional

from wireviz.wv_svg import (
    GridConfig,
    _endpoints,
    _pin_y,
    _wire_hex,
    build_layout,
)


def _pin_index(node: dict, pin_id) -> Optional[int]:
    for i, row in enumerate(node["pins"]):
        if row["id"] == pin_id:
            return i
    if isinstance(pin_id, int) and 1 <= pin_id <= len(node["pins"]):
        return pin_id - 1
    return None


def editor_data(harness, config: Optional[GridConfig] = None) -> dict:
    """Editable layout: nodes with pin offsets + wires with endpoint references."""
    cfg = config or GridConfig()
    layout = build_layout(harness, cfg)

    nodes = {}
    for name, n in layout["nodes"].items():
        nodes[name] = {
            "name": name,
            "kind": n["kind"],
            "x": n["x"],
            "y": n["y"],
            "w": n["w"],
            "h": n["h"],
            "pins": [
                {"id": str(p["id"]), "label": p["label"], "dy": p["y"] - n["y"]}
                for p in n["pins"]
            ],
        }

    wires = []

    def add(a_name, a_pin, b_name, b_pin, meta):
        a, b = layout["nodes"].get(a_name), layout["nodes"].get(b_name)
        if not a or not b:
            return
        ai, bi = _pin_index(a, a_pin), _pin_index(b, b_pin)
        if ai is None or bi is None:
            return
        wires.append(
            {
                "cable": meta["cable"],
                "wire": str(meta["wire"]),
                "color": meta["color"],
                "a": {"node": a_name, "pin": ai},
                "b": {"node": b_name, "pin": bi},
            }
        )

    for fname, fpin, cname, vport, tname, tpin in _endpoints(harness):
        cable_node = layout["nodes"].get(cname)
        if cable_node is None or _pin_y(cable_node, vport) is None:
            continue
        color = _wire_hex(harness.cables[cname], vport)
        meta = {"cable": cname, "wire": vport, "color": color}
        add(fname, fpin, cname, vport, meta)
        add(cname, vport, tname, tpin, meta)

    return {
        "pitch": cfg.pitch,
        "header": cfg.header,
        "nodes": nodes,
        "wires": wires,
        "width": layout["width"],
        "height": layout["height"],
    }


_STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif; background: #fafafa;
       color: #111; overflow: hidden; }
@media (prefers-color-scheme: dark) {
  body { background: #1e1e1e; color: #eee; }
  .toolbar { background: #2a2a2a; border-color: #444; }
  button { background: #333; color: #eee; border-color: #555; }
}
.toolbar { position: fixed; top: 0; left: 0; right: 0; height: 44px;
  display: flex; gap: 8px; align-items: center; padding: 0 12px;
  background: #fff; border-bottom: 1px solid #ddd; z-index: 10; }
.toolbar .title { font-weight: 600; margin-right: auto; }
button { border: 1px solid #ccc; border-radius: 6px; padding: 5px 10px;
  background: #f4f4f4; cursor: pointer; font-size: 13px; }
#stage { position: absolute; top: 44px; left: 0; right: 0; bottom: 0; }
#stage svg { width: 100%; height: 100%; touch-action: none; background: transparent; }
.node { cursor: grab; }
.node.dragging { cursor: grabbing; }
.node rect.body { fill: #eef4ff; stroke: #333; stroke-width: 1; }
.node.cable rect.body { fill: #f3f3f3; }
.node rect.hdr { fill: #333; }
.node text.name { fill: #fff; font-size: 13px; text-anchor: middle; }
.node text.pin { font-size: 11px; fill: #111; }
@media (prefers-color-scheme: dark){ .node text.pin{ fill:#ddd; } }
.hint { position: fixed; bottom: 8px; right: 12px; font-size: 12px; opacity: 0.6; }
""".strip()


# The editor runtime. DATA is injected before this script.
_SCRIPT = r"""
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const stage = document.getElementById('stage');
  const svg = document.createElementNS(NS, 'svg');
  const vb = { x: -20, y: -20, w: DATA.width + 40, h: DATA.height + 40 };
  const home = { ...vb };
  svg.setAttribute('viewBox', `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
  stage.appendChild(svg);

  const gridRect = document.createElementNS(NS, 'rect');
  const defs = document.createElementNS(NS, 'defs');
  defs.innerHTML = `<pattern id="grid" width="${DATA.pitch}" height="${DATA.pitch}"
    patternUnits="userSpaceOnUse"><path d="M ${DATA.pitch} 0 L 0 0 0 ${DATA.pitch}"
    fill="none" stroke="#dcdcdc" stroke-width="0.5"/></pattern>`;
  svg.appendChild(defs);
  gridRect.setAttribute('x', vb.x); gridRect.setAttribute('y', vb.y);
  gridRect.setAttribute('width', vb.w); gridRect.setAttribute('height', vb.h);
  gridRect.setAttribute('fill', 'url(#grid)');
  svg.appendChild(gridRect);

  const wireLayer = document.createElementNS(NS, 'g');
  const nodeLayer = document.createElementNS(NS, 'g');
  svg.appendChild(wireLayer); svg.appendChild(nodeLayer);

  const snap = v => Math.round(v / DATA.pitch) * DATA.pitch;

  function pinAbs(node, i) {
    const p = node.pins[i];
    return { left: node.x, right: node.x + node.w, y: node.y + p.dy };
  }
  function routePath(w) {
    const na = DATA.nodes[w.a.node], nb = DATA.nodes[w.b.node];
    const pa = pinAbs(na, w.a.pin), pb = pinAbs(nb, w.b.pin);
    let ax, bx;
    if (na.x + na.w / 2 <= nb.x + nb.w / 2) { ax = pa.right; bx = nb.x; }
    else { ax = pa.left; bx = nb.x + nb.w; }
    const mx = snap((ax + bx) / 2);
    return `M ${ax} ${pa.y} L ${mx} ${pa.y} L ${mx} ${pb.y} L ${bx} ${pb.y}`;
  }

  // build wire elements
  const wireEls = DATA.wires.map(w => {
    const casing = document.createElementNS(NS, 'path');
    const core = document.createElementNS(NS, 'path');
    for (const el of [casing, core]) { el.setAttribute('fill', 'none');
      el.setAttribute('stroke-linejoin', 'round'); el.setAttribute('stroke-linecap', 'round'); }
    casing.setAttribute('stroke', '#222'); casing.setAttribute('stroke-width', 3.2);
    core.setAttribute('stroke', w.color || '#000'); core.setAttribute('stroke-width', 1.6);
    wireLayer.appendChild(casing); wireLayer.appendChild(core);
    return { w, casing, core };
  });
  function redrawWiresFor(nodeName) {
    for (const we of wireEls) {
      if (!nodeName || we.w.a.node === nodeName || we.w.b.node === nodeName) {
        const d = routePath(we.w);
        we.casing.setAttribute('d', d); we.core.setAttribute('d', d);
      }
    }
  }

  // build node elements
  const nodeEls = {};
  for (const name in DATA.nodes) {
    const n = DATA.nodes[name];
    const g = document.createElementNS(NS, 'g');
    g.setAttribute('class', 'node ' + n.kind);
    g.innerHTML =
      `<rect class="body" width="${n.w}" height="${n.h}" rx="4"/>` +
      `<rect class="hdr" width="${n.w}" height="${DATA.header}" rx="4"/>` +
      `<text class="name" x="${n.w / 2}" y="${DATA.header - 9}">${name}</text>` +
      n.pins.map(p =>
        `<circle cx="0" cy="${p.dy}" r="2" fill="#333"/>` +
        `<circle cx="${n.w}" cy="${p.dy}" r="2" fill="#333"/>` +
        `<text class="pin" x="6" y="${p.dy + 4}">${p.id}${p.label ? ' ' + p.label : ''}</text>`
      ).join('');
    nodeLayer.appendChild(g);
    nodeEls[name] = g;
    place(name);
    attachDrag(name);
  }
  function place(name) {
    const n = DATA.nodes[name];
    nodeEls[name].setAttribute('transform', `translate(${n.x},${n.y})`);
  }

  // dragging
  let drag = null;
  function attachDrag(name) {
    const g = nodeEls[name];
    g.addEventListener('pointerdown', (e) => {
      e.stopPropagation();
      const r = svg.getBoundingClientRect();
      const sx = vb.x + (e.clientX - r.left) / r.width * vb.w;
      const sy = vb.y + (e.clientY - r.top) / r.height * vb.h;
      drag = { name, ox: sx - DATA.nodes[name].x, oy: sy - DATA.nodes[name].y };
      g.classList.add('dragging'); g.setPointerCapture(e.pointerId);
    });
    g.addEventListener('pointermove', (e) => {
      if (!drag || drag.name !== name) return;
      const r = svg.getBoundingClientRect();
      const sx = vb.x + (e.clientX - r.left) / r.width * vb.w;
      const sy = vb.y + (e.clientY - r.top) / r.height * vb.h;
      const n = DATA.nodes[name];
      n.x = snap(sx - drag.ox); n.y = snap(sy - drag.oy);
      place(name); redrawWiresFor(name);
    });
    const end = (e) => { if (drag && drag.name === name) { g.classList.remove('dragging'); drag = null; } };
    g.addEventListener('pointerup', end);
    g.addEventListener('pointercancel', end);
  }

  // pan (background) + zoom
  let pan = null;
  stage.addEventListener('pointerdown', (e) => { if (drag) return; pan = { x: e.clientX, y: e.clientY }; });
  stage.addEventListener('pointermove', (e) => {
    if (!pan || drag) return;
    const r = svg.getBoundingClientRect();
    vb.x -= (e.clientX - pan.x) / r.width * vb.w;
    vb.y -= (e.clientY - pan.y) / r.height * vb.h;
    pan = { x: e.clientX, y: e.clientY }; apply();
  });
  window.addEventListener('pointerup', () => { pan = null; });
  stage.addEventListener('wheel', (e) => {
    e.preventDefault();
    const r = svg.getBoundingClientRect();
    const mx = vb.x + (e.clientX - r.left) / r.width * vb.w;
    const my = vb.y + (e.clientY - r.top) / r.height * vb.h;
    const k = e.deltaY > 0 ? 1.1 : 0.9;
    vb.w *= k; vb.h *= k;
    vb.x = mx - (e.clientX - r.left) / r.width * vb.w;
    vb.y = my - (e.clientY - r.top) / r.height * vb.h;
    apply();
  }, { passive: false });
  function apply() { svg.setAttribute('viewBox', `${vb.x} ${vb.y} ${vb.w} ${vb.h}`); }

  document.getElementById('fit').addEventListener('click', () => { Object.assign(vb, home); apply(); });
  document.getElementById('grid').addEventListener('click', () => {
    gridRect.style.display = gridRect.style.display === 'none' ? '' : 'none';
  });
  document.getElementById('export').addEventListener('click', () => {
    const out = { nodes: {} };
    for (const n in DATA.nodes) out.nodes[n] = { x: DATA.nodes[n].x, y: DATA.nodes[n].y };
    const blob = new Blob([JSON.stringify(out, null, 2)], { type: 'application/json' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = 'harness-layout.json'; a.click();
  });

  redrawWiresFor(null);
})();
""".strip()


def render_editor(
    harness, config: Optional[GridConfig] = None, title: Optional[str] = None
) -> str:
    """Return a self-contained interactive drag-to-edit HTML viewer."""
    cfg = config or GridConfig()
    data = editor_data(harness, cfg)
    if title is None:
        title = (harness.metadata.get("title") if harness.metadata else None) or "Harness"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} — editor</title>
<style>{_STYLE}</style>
</head>
<body>
<div class="toolbar">
  <span class="title">{escape(title)} — drag to edit</span>
  <button id="fit">Fit</button>
  <button id="grid">Grid</button>
  <button id="export">Export layout</button>
</div>
<div id="stage"></div>
<div class="hint">drag a connector to move it &middot; drag background to pan &middot; scroll to zoom</div>
<script>const DATA = {json.dumps(data)};</script>
<script>{_SCRIPT}</script>
</body>
</html>
"""
