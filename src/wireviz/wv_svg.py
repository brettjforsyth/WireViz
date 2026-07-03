# -*- coding: utf-8 -*-
"""Native grid-snapped SVG renderer for WireViz harnesses.

WireViz normally delegates all layout and wire routing to Graphviz, which
produces spline wires that cannot be snapped to a grid and cannot anchor to
2D component footprints. This renderer instead lays the harness out itself,
directly from the parsed :class:`Harness` model:

- connectors and cables are placed in layered columns (left-to-right), the
  layering derived from the connection graph;
- every coordinate is snapped to a configurable grid pitch;
- wires are routed as orthogonal (Manhattan) polylines whose segments are all
  horizontal or vertical and land on grid lines.

It has no dependency on the ``dot`` binary, so it runs anywhere the Python
package does, and its output is plain text so it is straightforward to test.

The intermediate :func:`build_layout` result is a plain dict, which doubles as
the JSON feed for the 3D/interactive viewer.
"""

from dataclasses import dataclass, field
from html import escape
from typing import Dict, List, Optional, Tuple

from wireviz.wv_colors import get_color_hex


@dataclass
class GridConfig:
    """Geometry, all lengths in SVG user units and multiples of `pitch`."""

    pitch: int = 10  # the snap grid
    pin_pitch: int = 30  # vertical spacing between pins/wires in a node
    header: int = 30  # node title bar height
    node_width: int = 120
    col_gap: int = 120  # horizontal gap between columns
    node_gap: int = 40  # vertical gap between stacked nodes in a column
    margin: int = 40
    show_grid: bool = True

    def snap(self, v: float) -> int:
        return int(round(v / self.pitch) * self.pitch)


def _endpoints(harness):
    """Yield (from_name, from_pin, cable_name, via_port, to_name, to_pin)."""
    for cable_name, cable in harness.cables.items():
        for c in cable.connections:
            yield (c.from_name, c.from_pin, cable_name, c.via_port, c.to_name, c.to_pin)


def _assign_layers(harness) -> Dict[str, int]:
    """Longest-path layering of connectors+cables from the connection graph.

    Edges go connector(from) -> cable -> connector(to). Robust against cycles
    (loops/mates) via bounded relaxation.
    """
    nodes = list(harness.connectors.keys()) + list(harness.cables.keys())
    succ: Dict[str, set] = {n: set() for n in nodes}
    indeg: Dict[str, int] = {n: 0 for n in nodes}
    for fname, _fp, cname, _vp, tname, _tp in _endpoints(harness):
        for a, b in ((fname, cname), (cname, tname)):
            if a in succ and b in succ and b not in succ[a]:
                succ[a].add(b)
                indeg[b] += 1
    layer = {n: 0 for n in nodes}
    # bounded relaxation: |nodes| passes is enough for any DAG; caps cycles
    for _ in range(len(nodes) + 1):
        changed = False
        for a in nodes:
            for b in succ[a]:
                if layer[b] < layer[a] + 1:
                    layer[b] = layer[a] + 1
                    changed = True
        if not changed:
            break
    return layer


def _node_pins(harness, name) -> List[Tuple[object, str]]:
    """Return [(pin_id, label)] rows for a connector, or wire rows for a cable."""
    if name in harness.connectors:
        conn = harness.connectors[name]
        labels = conn.pinlabels or []
        rows = []
        for i, p in enumerate(conn.pins):
            label = labels[i] if i < len(labels) and labels[i] else ""
            rows.append((p, label))
        return rows
    cable = harness.cables[name]
    rows = []
    for w in range(1, (cable.wirecount or 0) + 1):
        color = ""
        if w - 1 < len(cable.colors):
            color = cable.colors[w - 1] or ""
        rows.append((w, color))
    if cable.shield:
        rows.append(("s", "shield"))
    return rows


def build_layout(harness, config: Optional[GridConfig] = None) -> dict:
    """Compute a grid-snapped layout dict (also the JSON feed for 3D)."""
    cfg = config or GridConfig()
    layer = _assign_layers(harness)
    order = list(harness.connectors.keys()) + list(harness.cables.keys())

    # group nodes by column (layer), preserving first-seen order within a column
    columns: Dict[int, List[str]] = {}
    for name in order:
        columns.setdefault(layer[name], []).append(name)

    nodes: Dict[str, dict] = {}
    col_x = cfg.margin
    max_bottom = cfg.margin
    for col in sorted(columns):
        y = cfg.margin
        col_width = cfg.node_width
        for name in columns[col]:
            pins = _node_pins(harness, name)
            height = cfg.header + max(len(pins), 1) * cfg.pin_pitch
            x = cfg.snap(col_x)
            y = cfg.snap(y)
            kind = "connector" if name in harness.connectors else "cable"
            pin_rows = []
            for i, (pid, label) in enumerate(pins):
                py = cfg.snap(y + cfg.header + i * cfg.pin_pitch + cfg.pin_pitch // 2)
                pin_rows.append({"id": pid, "label": label, "y": py})
            nodes[name] = {
                "name": name,
                "kind": kind,
                "x": x,
                "y": y,
                "w": col_width,
                "h": cfg.snap(height),
                "column": col,
                "pins": pin_rows,
            }
            y = y + height + cfg.node_gap
            max_bottom = max(max_bottom, y)
        col_x = col_x + col_width + cfg.col_gap

    # route wires: connector-pin -> cable-wire -> connector-pin, orthogonally
    wires: List[dict] = []
    for fname, fpin, cname, vport, tname, tpin in _endpoints(harness):
        cable_node = nodes.get(cname)
        if cable_node is None:
            continue
        wire_y = _pin_y(cable_node, vport)
        color_hex = _wire_hex(harness.cables[cname], vport)
        # from-connector segment
        if fname in nodes and wire_y is not None:
            seg = _route(nodes[fname], fpin, cable_node, wire_y, cfg)
            if seg:
                wires.append({"cable": cname, "wire": vport, "color": color_hex, "points": seg})
        # to-connector segment
        if tname in nodes and wire_y is not None:
            seg = _route(cable_node, wire_y, nodes[tname], tpin, cfg, from_wire=True)
            if seg:
                wires.append({"cable": cname, "wire": vport, "color": color_hex, "points": seg})

    width = cfg.snap(col_x - cfg.col_gap + cfg.margin)
    height = cfg.snap(max_bottom + cfg.margin)
    return {"config": cfg.__dict__, "nodes": nodes, "wires": wires, "width": width, "height": height}


def _pin_y(node: dict, pin_id) -> Optional[int]:
    for row in node["pins"]:
        if row["id"] == pin_id:
            return row["y"]
    # pin_id may be a 1-based index into the rows
    if isinstance(pin_id, int) and 1 <= pin_id <= len(node["pins"]):
        return node["pins"][pin_id - 1]["y"]
    return None


def _wire_hex(cable, via_port) -> str:
    if isinstance(via_port, str) and via_port.lower() == "s":
        return "#888888"
    colors = cable.colors or []
    if isinstance(via_port, int) and 1 <= via_port <= len(colors):
        code = colors[via_port - 1]
        if code:
            hexes = get_color_hex(code, pad=False)
            return hexes[0] if hexes else "#000000"
    return "#000000"


def _route(a: dict, a_pin, b: dict, b_pin, cfg: GridConfig, from_wire=False):
    """Orthogonal grid-snapped route from node a to node b.

    The cable end is always passed as an already-resolved y coordinate; the
    connector end is passed as a pin id and looked up. `from_wire` says which
    side is the cable: True means a is the cable (a_pin is that y), False means
    b is the cable (b_pin is that y).
    """
    if from_wire:
        ay = a_pin  # explicit cable-wire y
        by = _pin_y(b, b_pin)  # connector pin id
    else:
        ay = _pin_y(a, a_pin)  # connector pin id
        by = b_pin  # explicit cable-wire y
    if ay is None or by is None:
        return None
    # exit a on the side facing b, enter b on the side facing a
    if a["x"] <= b["x"]:
        ax = a["x"] + a["w"]
        bx = b["x"]
    else:
        ax = a["x"]
        bx = b["x"] + b["w"]
    ax, bx = cfg.snap(ax), cfg.snap(bx)
    ay, by = cfg.snap(ay), cfg.snap(by)
    midx = cfg.snap((ax + bx) / 2)
    # Manhattan: horizontal to channel, vertical, horizontal into target
    return [(ax, ay), (midx, ay), (midx, by), (bx, by)]


# --- SVG emission ----------------------------------------------------------


def _svg_grid(width, height, cfg: GridConfig) -> str:
    if not cfg.show_grid:
        return ""
    return (
        f'<defs><pattern id="grid" width="{cfg.pitch}" height="{cfg.pitch}" '
        f'patternUnits="userSpaceOnUse">'
        f'<path d="M {cfg.pitch} 0 L 0 0 0 {cfg.pitch}" fill="none" '
        f'stroke="#e8e8e8" stroke-width="0.5"/></pattern></defs>'
        f'<rect width="{width}" height="{height}" fill="url(#grid)"/>'
    )


def _node_svg(node: dict, cfg: GridConfig) -> str:
    x, y, w, h = node["x"], node["y"], node["w"], node["h"]
    fill = "#eef4ff" if node["kind"] == "connector" else "#f3f3f3"
    parts = [
        f'<g class="node {node["kind"]}">',
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="4" '
        f'fill="{fill}" stroke="#333" stroke-width="1"/>',
        f'<rect x="{x}" y="{y}" width="{w}" height="{cfg.header}" rx="4" '
        f'fill="#333"/>',
        f'<text x="{x + w / 2:.0f}" y="{y + cfg.header - 9}" fill="#fff" '
        f'font-size="13" font-family="sans-serif" text-anchor="middle">'
        f"{escape(str(node['name']))}</text>",
    ]
    for row in node["pins"]:
        py = row["y"]
        label = f"{row['id']}"
        if row["label"]:
            label += f" {row['label']}"
        parts.append(
            f'<text x="{x + 6}" y="{py + 4:.0f}" font-size="11" '
            f'font-family="sans-serif" fill="#111">{escape(str(label))}</text>'
        )
        # pin stubs on both sides
        parts.append(
            f'<circle cx="{x}" cy="{py}" r="2" fill="#333"/>'
            f'<circle cx="{x + w}" cy="{py}" r="2" fill="#333"/>'
        )
    parts.append("</g>")
    return "".join(parts)


def _wire_svg(wire: dict) -> str:
    pts = " ".join(f"{px},{py}" for px, py in wire["points"])
    color = wire["color"] or "#000000"
    # dark casing underneath so light-coloured wires stay visible on any bg
    return (
        f'<polyline points="{pts}" fill="none" stroke="#222" stroke-width="3.5" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<polyline points="{pts}" fill="none" stroke="{color}" '
        f'stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
    )


def render_svg(harness, config: Optional[GridConfig] = None) -> str:
    """Render `harness` to a standalone SVG string with grid-snapped wires."""
    cfg = config or GridConfig()
    layout = build_layout(harness, cfg)
    w, h = layout["width"], layout["height"]
    body = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}">',
        _svg_grid(w, h, cfg),
        '<g class="wires">',
        *[_wire_svg(wire) for wire in layout["wires"]],
        "</g>",
        '<g class="nodes">',
        *[_node_svg(node, cfg) for node in layout["nodes"].values()],
        "</g>",
        "</svg>",
    ]
    return "\n".join(body) + "\n"
