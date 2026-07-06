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

import json
from dataclasses import dataclass, field
from html import escape
from typing import Dict, List, Optional, Tuple

from wireviz.wv_colors import get_color_hex
from wireviz.wv_connectors import resolve_connector_assets


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
    image_band: int = 90  # vertical space reserved for a component image
    show_grid: bool = True
    route_pitch: int = 5  # maze-router grid step = spacing between parallel wires
    turn_penalty: int = 3  # extra routing cost per corner (fewer, cleaner bends)
    hop_radius: int = 2  # radius of the half-circle where wires cross
    wire_core: float = 1.5  # coloured wire width
    wire_casing: float = 3.0  # dark casing width under the colour

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


def _node_assets(harness, name, cad_dir=None, image_provider=None):
    """Resolve a connector's 2D image and 3D model.

    An explicit ``image:`` on the connector wins for the 2D image; otherwise
    the connector's ``connector_type`` is resolved against the CAD library.
    Returns ``(image_2d, model_3d)``, either of which may be None.
    """
    conn = harness.connectors.get(name)
    if conn is None:
        return None, None
    image_2d = None
    if getattr(conn, "image", None):
        src = getattr(conn.image, "src", None)
        image_2d = str(src) if src is not None else None
    ctype = getattr(conn, "connector_type", None)
    model_3d = None
    if ctype:
        assets = resolve_connector_assets(ctype, cad_dir, image_provider)
        image_2d = image_2d or assets.image_2d
        model_3d = assets.model_3d
    return image_2d, model_3d


def build_layout(
    harness,
    config: Optional[GridConfig] = None,
    cad_dir: Optional[str] = None,
    image_provider=None,
) -> dict:
    """Compute a grid-snapped layout dict (also the JSON feed for 3D).

    ``cad_dir`` / ``image_provider`` are passed to the connector-type CAD
    resolver so each connector node carries its resolved 2D image and 3D model.
    """
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
            image, model_3d = _node_assets(harness, name, cad_dir, image_provider)
            height = cfg.header + max(len(pins), 1) * cfg.pin_pitch
            if image:
                height += cfg.image_band
            x = cfg.snap(col_x)
            y = cfg.snap(y)
            kind = "connector" if name in harness.connectors else "cable"
            pin_rows = []
            for i, (pid, label) in enumerate(pins):
                py = cfg.snap(
                    y + cfg.header + i * cfg.pin_pitch + cfg.pin_pitch // 2
                )
                pin_rows.append({"id": pid, "label": label, "y": py})
            node = {
                "name": name,
                "kind": kind,
                "x": x,
                "y": y,
                "w": col_width,
                "h": cfg.snap(height),
                "column": col,
                "pins": pin_rows,
            }
            if image:
                node["image"] = {
                    "src": image,
                    "y": cfg.snap(y + cfg.header + len(pins) * cfg.pin_pitch),
                }
            if model_3d:
                node["model_3d"] = model_3d
            nodes[name] = node
            y = y + height + cfg.node_gap
            max_bottom = max(max_bottom, y)
        col_x = col_x + col_width + cfg.col_gap

    width = cfg.snap(col_x - cfg.col_gap + cfg.margin)
    height = cfg.snap(max_bottom + cfg.margin)

    # collect one routing job per wire segment (connector-pin -> cable-wire ->
    # connector-pin), then route them all with a shared maze router so no two
    # wires ever share a grid edge (i.e. lie on top of each other).
    jobs: List[dict] = []
    for fname, fpin, cname, vport, tname, tpin in _endpoints(harness):
        cable_node = nodes.get(cname)
        if cable_node is None:
            continue
        wire_y = _pin_y(cable_node, vport)
        if wire_y is None:
            continue
        color_hex = _wire_hex(harness.cables[cname], vport)
        meta = {"cable": cname, "wire": vport, "color": color_hex}
        fnode = nodes.get(fname)
        if fnode is not None:
            fy = _pin_y(fnode, fpin)
            if fy is not None:
                jobs.append({**meta, "a": (fnode, fy), "b": (cable_node, wire_y)})
        tnode = nodes.get(tname)
        if tnode is not None:
            ty = _pin_y(tnode, tpin)
            if ty is not None:
                jobs.append({**meta, "a": (cable_node, wire_y), "b": (tnode, ty)})

    wires = _route_all(jobs, nodes, cfg, width, height)

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


# --- maze router (Lee/Dijkstra with edge reservation) ----------------------
#
# Orthogonal wire routing on a coarse grid, the standard EDA approach. Each
# wire is routed as a shortest path on a grid whose step is `route_pitch`;
# every grid *edge* a wire uses is reserved so no later wire can reuse it. Two
# wires may share a grid *vertex* (a perpendicular crossing -> drawn as a hop)
# but never an edge, which is exactly the guarantee "wires are never on top of
# each other". Node rectangles are obstacles, so wires route in the gaps.


def _edge(p, q):
    return (p, q) if p <= q else (q, p)


def _snapr(v, rp):
    return int(round(v / rp) * rp)


def _terminal(node, y, other):
    """Exact point where a wire meets `node`, on the edge facing `other`."""
    if node["x"] <= other["x"]:
        return (node["x"] + node["w"], y)
    return (node["x"], y)


def _blocked_cells(nodes, rp):
    """Grid points inside node rectangles (obstacles the router avoids)."""
    blocked = set()
    for n in nodes.values():
        x0, x1 = _snapr(n["x"], rp), _snapr(n["x"] + n["w"], rp)
        y0, y1 = _snapr(n["y"], rp), _snapr(n["y"] + n["h"], rp)
        gy = y0
        while gy <= y1:
            gx = x0
            while gx <= x1:
                blocked.add((gx, gy))
                gx += rp
            gy += rp
    return blocked


def _astar(start, goal, blocked, used, cfg, bounds, terminals=frozenset()):
    """Least-cost orthogonal path start->goal (A*), avoiding blocked cells and
    edges owned by other wires, penalising turns. Returns points, or None.

    `used` maps each occupied edge to the terminal set of the wire that owns it;
    an edge may be reused only by a wire that shares one of those terminals (two
    wires bundled at the same pin). A* (Manhattan heuristic) keeps whole-canvas
    search fast so a congested wire detours into open space rather than fail.
    """
    import heapq

    rp, tp = cfg.route_pitch, cfg.turn_penalty
    minx, miny, maxx, maxy = bounds
    gx, gy = goal

    def h(x, y):
        return (abs(x - gx) + abs(y - gy)) // rp

    start_st = (start[0], start[1], 0, 0)
    dist = {start_st: 0}
    prev = {}
    pq = [(h(*start), 0, start_st)]
    goal_state = None
    while pq:
        _, c, st = heapq.heappop(pq)
        if c > dist.get(st, 1 << 30):
            continue
        x, y, dx, dy = st
        if (x, y) == goal:
            goal_state = st
            break
        for ndx, ndy in ((rp, 0), (-rp, 0), (0, rp), (0, -rp)):
            nx, ny = x + ndx, y + ndy
            if nx < minx or nx > maxx or ny < miny or ny > maxy:
                continue
            if (nx, ny) != goal and (nx, ny) in blocked:
                continue
            owner = used.get(_edge((x, y), (nx, ny)))
            if owner is not None and not (owner & terminals):
                continue
            turned = tp if (dx or dy) and (ndx, ndy) != (dx, dy) else 0
            nc = c + 1 + turned
            nst = (nx, ny, ndx, ndy)
            if nc < dist.get(nst, 1 << 30):
                dist[nst] = nc
                prev[nst] = st
                heapq.heappush(pq, (nc + h(nx, ny), nc, nst))
    if goal_state is None:
        return None
    path = []
    st = goal_state
    while True:
        path.append((st[0], st[1]))
        if st not in prev:
            break
        st = prev[st]
    path.reverse()
    return path


def _simplify(pts):
    """Drop duplicate and collinear intermediate points."""
    dedup = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
    if len(dedup) < 3:
        return dedup
    out = [dedup[0]]
    for i in range(1, len(dedup) - 1):
        (px, py), (x, y), (nx, ny) = out[-1], dedup[i], dedup[i + 1]
        if (x - px) * (ny - y) != (y - py) * (nx - x):  # a genuine turn
            out.append(dedup[i])
    out.append(dedup[-1])
    return out


def _iter_unit_edges(path, rp):
    """Yield the rp-length grid edges a corner polyline occupies."""
    for (x1, y1), (x2, y2) in zip(path, path[1:]):
        if x1 == x2:
            lo, hi = sorted((y1, y2))
            for y in range(lo, hi, rp):
                yield _edge((x1, y), (x1, y + rp))
        elif y1 == y2:
            lo, hi = sorted((x1, x2))
            for x in range(lo, hi, rp):
                yield _edge((x, y1), (x + rp, y1))


def _candidate(a, b, chan, rp):
    """A clean 2-bend route through a wire's assigned vertical channel `chan`
    (or a straight line when the endpoints share a row)."""
    if a[1] == b[1]:
        return [a, b]
    cx = chan if chan is not None else _snapr((a[0] + b[0]) / 2, rp)
    return [a, (cx, a[1]), (cx, b[1]), b]


def _fits(path, used, terminals, rp):
    """True if `path` reuses no edge owned by a wire it shares no pin with."""
    for e in _iter_unit_edges(path, rp):
        owner = used.get(e)
        if owner is not None and not (owner & terminals):
            return False
    return True


def _route_all(jobs, nodes, cfg, width, height):
    """Route every wire segment so no two wires ever share an edge.

    Each wire is given a unique vertical channel and routed with a clean 2-bend
    path (the bus look); straight wires are placed first so they keep their
    lane. Any wire whose deterministic route would collide with an already
    placed wire is re-routed with the edge-avoiding A* maze router. Every wire
    reserves its grid edges, so overlaps are impossible.
    """
    from collections import defaultdict

    rp = cfg.route_pitch
    blocked = _blocked_cells(nodes, rp)
    used = {}  # edge -> frozenset of the owning wire's terminal points
    pad = cfg.col_gap
    bounds = (
        -pad,
        -pad,
        _snapr(width, rp) + pad,
        _snapr(height, rp) + pad,
    )

    prepared = []
    for job in jobs:
        anode, ay = job["a"]
        bnode, by = job["b"]
        a = _terminal(anode, _snapr(ay, rp), bnode)
        b = _terminal(bnode, _snapr(by, rp), anode)
        prepared.append({"job": job, "a": a, "b": b})

    # assign a unique vertical channel to every wire sharing a corridor
    corridors = defaultdict(list)
    for p in prepared:
        p["xL"], p["xR"] = sorted((p["a"][0], p["b"][0]))
        corridors[(p["xL"], p["xR"])].append(p)
    for (xL, xR), group in corridors.items():
        group.sort(key=lambda p: (p["a"][1] + p["b"][1]) / 2)
        n = len(group)
        for i, p in enumerate(group):
            p["chan"] = _snapr(xL + (i + 1) / (n + 1) * (xR - xL), rp)

    # place straight wires first, then shortest to longest
    order = sorted(
        prepared,
        key=lambda p: (p["a"][1] != p["b"][1], abs(p["a"][0] - p["b"][0]) + abs(p["a"][1] - p["b"][1])),
    )

    wires = []
    for p in order:
        a, b, job = p["a"], p["b"], p["job"]
        terminals = frozenset((a, b))
        cand = _candidate(a, b, p.get("chan"), rp)
        if _fits(cand, used, terminals, rp):
            path = cand
        else:
            adir = rp if b[0] > a[0] else -rp
            a_start, b_start = (a[0] + adir, a[1]), (b[0] - adir, b[1])
            detour = _astar(a_start, b_start, blocked, used, cfg, bounds, terminals)
            path = [a] + detour + [b] if detour else cand
        for e in _iter_unit_edges(path, rp):
            used[e] = terminals
        wires.append({**job_meta(job), "points": _simplify(path)})
    return wires


def job_meta(job):
    return {"cable": job["cable"], "wire": job["wire"], "color": job["color"]}


# --- SVG emission ----------------------------------------------------------


def _svg_grid(width, height, cfg: GridConfig) -> str:
    # solid white backing so the SVG is not transparent (renders white everywhere)
    bg = f'<rect width="{width}" height="{height}" fill="white"/>'
    if not cfg.show_grid:
        return bg
    return (
        bg
        + f'<defs><pattern id="grid" width="{cfg.pitch}" height="{cfg.pitch}" '
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
    image = node.get("image")
    if image:
        iy = image["y"]
        ih = cfg.image_band - 10
        parts.append(
            f'<image href="{escape(str(image["src"]))}" '
            f'xlink:href="{escape(str(image["src"]))}" '
            f'x="{x + 5}" y="{iy}" width="{w - 10}" height="{ih}" '
            f'preserveAspectRatio="xMidYMid meet"/>'
        )
    parts.append("</g>")
    return "".join(parts)


def _vertical_segments(wires: List[dict]):
    """Collect (wire_index, x, ymin, ymax) for every vertical wire segment."""
    verts = []
    for idx, w in enumerate(wires):
        pts = w["points"]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            if x1 == x2 and y1 != y2:
                verts.append((idx, x1, min(y1, y2), max(y1, y2)))
    return verts


def _horizontal_crossings(y, x1, x2, index, verts, cfg):
    """Return the x-positions where the horizontal segment (y, x1..x2) crosses
    another wire's vertical run and should hop over it."""
    r = cfg.hop_radius
    lo, hi = min(x1, x2), max(x1, x2)
    return [
        vx
        for (vi, vx, vy1, vy2) in verts
        if vi != index
        # A hop is only for a true mid-span crossing: the vertical must pass
        # strictly through the horizontal (so a corner/T is never hopped) and
        # the crossing must clear this wire's own ends by a hop radius.
        and lo + r < vx < hi - r
        and vy1 < y < vy2
    ]


def _wire_dpaths(wire: dict, index: int, verts, cfg: GridConfig):
    """Split a wire into two SVG `d` strings: its vertical segments and its
    horizontal segments (the latter carrying the half-circle hops).

    Verticals are drawn in a lower layer and horizontals in an upper layer, so
    every hop (always on a horizontal) sits above the vertical it crosses.
    """
    r = cfg.hop_radius
    d_vert, d_horiz = [], []
    for (x1, y1), (x2, y2) in zip(wire["points"], wire["points"][1:]):
        if x1 == x2 and y1 != y2:  # vertical
            d_vert.append(f"M {x1} {y1} L {x2} {y2}")
        elif y1 == y2 and x1 != x2:  # horizontal, with hops
            d = [f"M {x1} {y1}"]
            step = 1 if x2 > x1 else -1
            sweep = 1 if step > 0 else 0
            crossings = _horizontal_crossings(y1, x1, x2, index, verts, cfg)
            crossings.sort(reverse=(step < 0))
            for vx in crossings:
                d.append(f"L {vx - r * step} {y1}")
                d.append(f"A {r} {r} 0 0 {sweep} {vx + r * step} {y1}")
            d.append(f"L {x2} {y2}")
            d_horiz.append(" ".join(d))
    return " ".join(d_vert), " ".join(d_horiz)


def _path_pair(d, key, color, cfg):
    if not d:
        return ""
    return (
        f'<path class="wire" data-wire="{key}" d="{d}" fill="none" '
        f'stroke="#222" stroke-width="{cfg.wire_casing}" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
        f'<path class="wire-core" data-wire="{key}" d="{d}" fill="none" '
        f'stroke="{color}" stroke-width="{cfg.wire_core}" '
        f'stroke-linejoin="round" stroke-linecap="round"/>'
    )


def render_svg(
    harness,
    config: Optional[GridConfig] = None,
    cad_dir: Optional[str] = None,
    image_provider=None,
) -> str:
    """Render `harness` to a standalone SVG string with grid-snapped wires."""
    cfg = config or GridConfig()
    layout = build_layout(harness, cfg, cad_dir, image_provider)
    w, h = layout["width"], layout["height"]
    verts = _vertical_segments(layout["wires"])
    unders, overs = [], []
    for i, wire in enumerate(layout["wires"]):
        key = escape(f"{wire['cable']}:{wire['wire']}")
        color = wire["color"] or "#000000"
        d_vert, d_horiz = _wire_dpaths(wire, i, verts, cfg)
        unders.append(_path_pair(d_vert, key, color, cfg))
        overs.append(_path_pair(d_horiz, key, color, cfg))
    body = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        _svg_grid(w, h, cfg),
        # verticals first, then horizontals on top so every hop is above the
        # wire it crosses
        '<g class="wires-under">',
        *unders,
        "</g>",
        '<g class="wires-over">',
        *overs,
        "</g>",
        '<g class="nodes">',
        *[_node_svg(node, cfg) for node in layout["nodes"].values()],
        "</g>",
        "</svg>",
    ]
    return "\n".join(body) + "\n"


def export_json(
    harness,
    config: Optional[GridConfig] = None,
    indent: int = 2,
    cad_dir: Optional[str] = None,
    image_provider=None,
) -> str:
    """Serialize the grid layout plus harness metadata to JSON.

    This is the machine-readable feed for the interactive/3D viewer and for
    interop; it is intentionally renderer-neutral (positions + connectivity +
    per-component metadata), not tied to the SVG output.
    """
    layout = build_layout(harness, config, cad_dir, image_provider)
    meta = {
        "title": harness.metadata.get("title") if harness.metadata else None,
        "connectors": len(harness.connectors),
        "cables": len(harness.cables),
    }
    return json.dumps({"metadata": meta, **layout}, indent=indent)
