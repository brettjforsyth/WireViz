"""Vehicle view: the harness laid out on a calibrated picture of the vehicle.

A layout file (YAML) says where things sit in the vehicle, in millimetres::

    backdrop:                    # optional picture, calibrated to millimetres
      image: car_plan.png        # path relative to the layout file
      origin_px: [74.75, 451.75] # picture pixel that sits at vehicle (0, 0)
      mm_per_px: 1.9568
    nodes:                       # connector designator -> [x, y] in mm
      X1: [220, 640]
    runs:                        # trunk routes as polylines, in mm
      - name: NOSE LOOM
        path: [[220, 640], [300, 300], [1060, 300]]
    insets:                      # optional zoom boxes for crowded areas
      - name: Dash
        box: [900, -700, 1500, 700]

``nose_px`` / ``center_py`` are accepted in place of ``origin_px`` (x and y).

Trunks are drawn black, as thick as the estimated bundle of the wires that use
them. Every wire is routed automatically: from its connector to the nearest
point on a trunk, along the shortest path through the trunk network, and out to
the connector at its other end, so only the trunks have to be drawn. Clicking a
connector lights up its wires in their real colours along those routes and
shows the connector face with each cavity filled in its wire colour.

The page is one self-contained HTML file (picture embedded), so it opens from
disk or on a phone.
"""

import base64
import copy
import fnmatch
import heapq
import json
import math
import re
from html import escape
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from wireviz.wv_bundle import DEFAULT_WALL_MM, bundle_diameter, wire_outer_diameter
from wireviz.wv_colors import get_color_hex
from wireviz.wv_faces import face_for

Point = Tuple[float, float]

SNAP_MM = 1.0  # waypoints closer than this are the same trunk junction
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".svg": "image/svg+xml"}


# --------------------------------------------------------------------- layout
def _layout_source(text: str, raw: dict) -> dict:
    """What the page needs to write an edited layout back faithfully: the
    file's header comment, its other top-level sections as written, and the
    comments on and between the node and run lines."""
    lines = text.splitlines()
    header = []
    for ln in lines:
        if ln.startswith("#") or not ln.strip():
            header.append(ln)
        else:
            break
    while header and not header[-1].strip():
        header.pop()

    def block(key):
        out, inside = [], False
        for ln in lines:
            if re.match(rf"^{re.escape(key)}\s*:", ln):
                inside = True
                continue
            if inside:
                if ln and not ln[0].isspace() and not ln.startswith("#"):
                    break
                out.append(ln)
        return out

    nodes, pre = [], []
    for ln in block("nodes"):
        m = re.match(r"^\s+([^\s:#]+)\s*:\s*\[[^\]]*\]\s*(?:#\s?(.*))?$", ln)
        if m:
            nodes.append({"name": m.group(1), "note": (m.group(2) or "").rstrip(), "pre": pre})
            pre = []
        elif ln.strip().startswith("#"):
            pre.append(ln.strip())
    runs_pre, pre, i = {}, [], 0
    for ln in block("runs"):
        if ln.strip().startswith("#"):
            pre.append(ln.strip())
        elif ln.strip().startswith("- "):
            if pre:
                runs_pre[i] = pre
            pre, i = [], i + 1
    top = {k: v for k, v in raw.items() if k not in ("nodes", "runs", "insets")}
    return {"header": header, "order": list(raw.keys()), "top": top,
            "insets": raw.get("insets") or [], "nodes": nodes, "runs_pre": runs_pre,
            "runs": raw.get("runs") or [], "pos": raw.get("nodes") or {}}


def load_layout(path) -> dict:
    """Read a layout file and normalise it (backdrop origin, image path)."""
    path = Path(path)
    text = path.read_text()
    lay = yaml.safe_load(text) or {}
    lay["_source"] = _layout_source(text, copy.deepcopy(lay))
    lay["_source"]["file"] = path.name
    bd = lay.get("backdrop")
    if bd:
        if "origin_px" not in bd:
            bd["origin_px"] = [bd.get("nose_px", 0), bd.get("center_py", 0)]
        img = Path(bd["image"])
        if not img.is_absolute():
            img = (path.parent / img).resolve()
            if not img.exists():  # layouts kept in a subfolder of the project
                alt = (path.parent.parent / bd["image"]).resolve()
                img = alt if alt.exists() else img
        bd["image_path"] = str(img)
    lay["nodes"] = {str(k): [float(v[0]), float(v[1])]
                    for k, v in (lay.get("nodes") or {}).items()}
    lay["runs"] = [r for r in (lay.get("runs") or []) if len(r.get("path") or []) >= 2]
    return lay


# ---------------------------------------------------------------- trunk graph
def _dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _foot(p: Point, a: Point, b: Point) -> Tuple[Point, float]:
    """Closest point to p on segment ab, and its parameter t in [0, 1]."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = dx * dx + dy * dy
    if ll == 0:
        return a, 0.0
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ll))
    return (a[0] + t * dx, a[1] + t * dy), t


class TrunkNet:
    """Trunk polylines as a weighted graph: shared waypoints become junctions,
    and a waypoint lying on another run's segment splits that segment."""

    def __init__(self, runs: List[dict], snap: float = SNAP_MM):
        self.snap = snap
        self.pts: List[Point] = []
        self.edges = set()  # (a, b) with a < b
        for run in runs:
            ids = [self.vertex(tuple(map(float, p))) for p in run["path"]]
            for a, b in zip(ids, ids[1:]):
                if a != b:
                    self.edges.add((min(a, b), max(a, b)))
        self._split_t_junctions()
        self.trunk_edges = set(self.edges)

    def vertex(self, p: Point) -> int:
        for i, q in enumerate(self.pts):
            if _dist(p, q) <= self.snap:
                return i
        self.pts.append(p)
        return len(self.pts) - 1

    def _split_t_junctions(self):
        changed = True
        while changed:
            changed = False
            for v, p in enumerate(self.pts):
                for a, b in list(self.edges):
                    if v in (a, b):
                        continue
                    f, t = _foot(p, self.pts[a], self.pts[b])
                    if 0 < t < 1 and _dist(f, p) <= self.snap:
                        self.edges.discard((a, b))
                        self.edges.add((min(a, v), max(a, v)))
                        self.edges.add((min(v, b), max(v, b)))
                        changed = True

    def attach(self, p: Point) -> Optional[int]:
        """Join point p to the nearest trunk; return the junction vertex id."""
        if not self.edges:
            return None
        best = None
        for a, b in self.edges:
            f, t = _foot(p, self.pts[a], self.pts[b])
            d = _dist(f, p)
            if best is None or d < best[0]:
                best = (d, a, b, f, t)
        _, a, b, f, t = best
        if _dist(f, self.pts[a]) <= self.snap:
            return a
        if _dist(f, self.pts[b]) <= self.snap:
            return b
        v = self.vertex(f)
        self.edges.discard((a, b))
        self.edges.add((min(a, v), max(a, v)))
        self.edges.add((min(v, b), max(v, b)))
        if (a, b) in self.trunk_edges:
            self.trunk_edges.discard((a, b))
            self.trunk_edges.add((min(a, v), max(a, v)))
            self.trunk_edges.add((min(v, b), max(v, b)))
        return v

    def nearest(self, p: Point) -> Optional[Point]:
        """Closest point on any trunk to p (the graph is not changed)."""
        best = None
        for a, b in self.edges:
            f, _ = _foot(p, self.pts[a], self.pts[b])
            if best is None or _dist(f, p) < _dist(best, p):
                best = f
        return best

    def _dijkstra(self, s: int, t: Optional[int] = None):
        adj: Dict[int, List[Tuple[int, float]]] = {}
        for a, b in self.edges:
            w = _dist(self.pts[a], self.pts[b])
            adj.setdefault(a, []).append((b, w))
            adj.setdefault(b, []).append((a, w))
        dist = {s: 0.0}
        prev: Dict[int, int] = {}
        heap = [(0.0, s)]
        while heap:
            d, u = heapq.heappop(heap)
            if u == t:
                break
            if d > dist.get(u, math.inf):
                continue
            for v, w in adj.get(u, []):
                nd = d + w
                if nd < dist.get(v, math.inf):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(heap, (nd, v))
        return dist, prev

    def distances(self, s: int) -> Dict[int, float]:
        return self._dijkstra(s)[0]

    def shortest(self, s: int, t: int) -> Optional[List[int]]:
        dist, prev = self._dijkstra(s, t)
        if t not in dist:
            return None
        path = [t]
        while path[-1] != s:
            path.append(prev[path[-1]])
        return path[::-1]

    def junction_for(self, targets: List[Tuple[int, int, Optional[float]]],
                     near: Point) -> Optional[int]:
        """Where a splice joining these trunk points sits. ``targets`` holds
        (vertex, wire count, model cut length in mm or None) per neighbour.

        The model's own cut lengths say where the splice is meant to be, so
        when every neighbour has one the splice goes where the routed distances
        best match them (a two-way joint: that fraction of the way along the
        route). Without lengths: halfway for a two-way joint, otherwise the
        vertex with the least total wire to all neighbours. Ties go to the
        vertex closest to ``near``."""
        merged: Dict[int, List] = {}
        for v, w, ln in targets:
            m = merged.setdefault(v, [0, []])
            m[0] += w
            if ln:
                m[1].append(ln)
        vids = sorted(merged)
        lens = {v: (sum(m[1]) / len(m[1]) if m[1] else None) for v, m in merged.items()}
        have_lengths = all(lens[v] for v in vids)
        if len(vids) == 1:
            return vids[0]
        if len(vids) == 2:
            path = self.shortest(vids[0], vids[1])
            if path:
                pts = [self.pts[v] for v in path]
                total = _polyline_len(pts)
                frac = (lens[vids[0]] / (lens[vids[0]] + lens[vids[1]])) if have_lengths else 0.5
                want, run = total * frac, 0.0
                for a, b in zip(pts, pts[1:]):
                    seg = _dist(a, b)
                    if run + seg >= want and seg > 0:
                        t = (want - run) / seg
                        return self.attach((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
                    run += seg
                return path[-1]
        maps = [(self.distances(v), merged[v][0], lens[v]) for v in vids]
        best = None
        for v in range(len(self.pts)):
            if all(v in d for d, _, _ in maps):
                copper = sum(w * d[v] for d, w, _ in maps)
                fit = sum(w * (d[v] - ln) ** 2 for d, w, ln in maps) if have_lengths else 0.0
                key = (round(fit, 1), round(copper, 1), _dist(self.pts[v], near))
                if best is None or key < best[0]:
                    best = (key, v)
        return best[1] if best else None


def _polyline_len(pts: List[Point]) -> float:
    return sum(_dist(a, b) for a, b in zip(pts, pts[1:]))


# ---------------------------------------------------------------------- wires
def _wire_colors(cable, port) -> Tuple[str, List[str]]:
    if port == "s":
        return "SH", ["#9a9a9a"]
    try:
        code = cable.colors[int(port) - 1] if cable.colors else ""
    except (ValueError, IndexError, TypeError):
        code = ""
    code = code or "BK"
    try:
        hexes = get_color_hex(code)
    except Exception:
        hexes = ["#999999"]
    return code, hexes or ["#999999"]


_UNIT_M = {"m": 1.0, "mm": 0.001, "cm": 0.01, "in": 0.0254, "ft": 0.3048, "yd": 0.9144}


def _metres(cable) -> Optional[float]:
    """The cable's model cut length in metres (WireViz defaults to metres)."""
    try:
        ln = float(cable.length or 0)
    except (TypeError, ValueError):
        return None
    return ln * _UNIT_M.get(str(cable.length_unit or "m").strip().lower(), 1.0) or None


def _gauge(cable) -> Tuple[str, Optional[float]]:
    """Display text and insulated diameter (mm); the parser may give a string."""
    try:
        g = float(cable.gauge)
    except (TypeError, ValueError):
        return (str(cable.gauge) if cable.gauge else ""), None
    unit = cable.gauge_unit or "mm²"
    try:
        od = wire_outer_diameter(g, unit)
    except Exception:
        od = None
    return f"{g:g} {unit}", od


def build_carview(harness, layout: dict) -> dict:
    """Everything the page draws, computed in Python so it can be tested."""
    nodes_pos = dict(layout["nodes"])
    net = TrunkNet(layout["runs"])

    # connectors drawn on the page (documentation-only nodes are skipped)
    conns = {n: c for n, c in harness.connectors.items() if c.style != "simple"}

    # every conductor with both ends on a connector
    wires, one_ended = [], []
    for cname, cable in harness.cables.items():
        gauge_txt, od = _gauge(cable)
        for i, conn in enumerate(cable.connections):
            port = conn.via_port
            code, hexes = _wire_colors(cable, port)
            w = {"id": f"{cname}:{port}:{i}", "cable": cname, "core": port,
                 "code": code, "colors": hexes,
                 "gauge": gauge_txt, "od": od,
                 "from": [conn.from_name, conn.from_pin],
                 "to": [conn.to_name, conn.to_pin],
                 "cut_m": _metres(cable)}
            if not conn.from_name or not conn.to_name:
                one_ended.append(w["id"])
                w["route"] = None
            wires.append(w)

    # attach every hand-placed connector that has a wire to the trunk network
    used = ({w["from"][0] for w in wires} | {w["to"][0] for w in wires}) - {None}
    node_vid: Dict[str, int] = {}
    for n in sorted(used):
        if n in nodes_pos:
            j = net.attach(tuple(nodes_pos[n]))
            if j is not None:
                node_vid[n] = j

    # splices, joints and the like sit inside the bundle where their wires part
    # ways: a node matching an ``auto_place`` pattern goes on the trunk network
    # at its junction point (TrunkNet.junction_for), so it needs no position.
    # Chains of them are placed outward from the hand-placed connectors.
    auto = set()
    patterns = [str(p) for p in (layout.get("auto_place") or [])]
    if patterns:
        links: Dict[str, Dict[str, list]] = {}  # node -> neighbour -> [count, lengths]
        for w in wires:
            a, b = w["from"][0], w["to"][0]
            if a and b and a != b:
                for x, y in ((a, b), (b, a)):
                    e = links.setdefault(x, {}).setdefault(y, [0, []])
                    e[0] += 1
                    if w["cut_m"]:
                        e[1].append(w["cut_m"] * 1000)
        cand = sorted(n for n in conns if n not in nodes_pos
                      and any(fnmatch.fnmatchcase(n, p) for p in patterns))
        for _ in range(len(cand) + 1):
            progress = False
            for n in cand:
                if n in nodes_pos:
                    continue
                known = {m: c for m, c in sorted(links.get(n, {}).items()) if m in nodes_pos}
                if not known:
                    continue
                pts = [nodes_pos[m] for m in known]
                c = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
                targets = [(node_vid[m], k[0], (sum(k[1]) / len(k[1])) if k[1] else None)
                           for m, k in known.items() if m in node_vid]
                v = net.junction_for(targets, c) if targets else None
                p = net.pts[v] if v is not None else c
                nodes_pos[n] = [round(p[0], 1), round(p[1], 1)]
                if v is not None:
                    node_vid[n] = v
                auto.add(n)
                progress = True
            if not progress:
                break

    edge_ods: Dict[Tuple[int, int], List[float]] = {}
    cache: Dict[Tuple[str, str], Optional[List[int]]] = {}
    unrouted = []
    for w in wires:
        a, b = w["from"][0], w["to"][0]
        if not a or not b:
            continue
        if a not in nodes_pos or b not in nodes_pos:
            w["route"] = None
            unrouted.append(w["id"])
            continue
        pa, pb = tuple(nodes_pos[a]), tuple(nodes_pos[b])
        if a == b:
            w["route"] = [list(pa), list(pb)]
            w["len_mm"] = 0.0
            continue
        key = (a, b)
        if key not in cache:
            va, vb = node_vid.get(a), node_vid.get(b)
            cache[key] = net.shortest(va, vb) if va is not None and vb is not None else None
        vids = cache[key]
        if vids is None:  # no trunk joins them: draw straight, flag it
            pts = [pa, pb]
            w["trunk"] = False
        else:
            pts = [pa] + [net.pts[v] for v in vids] + [pb]
            w["trunk"] = True
            for u, v in zip(vids, vids[1:]):
                edge_ods.setdefault((min(u, v), max(u, v)), []).append(w["od"] or 1.6)
        clean = [pts[0]]
        for p in pts[1:]:
            if _dist(p, clean[-1]) > 0.01:
                clean.append(p)
        w["route"] = [[round(x, 1), round(y, 1)] for x, y in clean]
        w["len_mm"] = round(_polyline_len(clean), 0)

    trunks = []
    for a, b in sorted(net.trunk_edges):
        ods = edge_ods.get((a, b), [])
        trunks.append({"pts": [list(net.pts[a]), list(net.pts[b])],
                       "n": len(ods),
                       "d": round(bundle_diameter(ods), 1) if ods else 0.0})

    nodes = {}
    for n, c in conns.items():
        pins = list(c.pins or [])
        labels = list(c.pinlabels or [])
        nodes[n] = {
            "x": nodes_pos[n][0] if n in nodes_pos else None,
            "y": nodes_pos[n][1] if n in nodes_pos else None,
            "type": str(c.type or ""), "mpn": str(c.mpn or ""),
            "pins": [[p, str(labels[i]) if i < len(labels) else ""] for i, p in enumerate(pins)],
            "face": face_for(c, (layout.get("faces") or {}).get(n)),
            "auto": n in auto,
        }
    unplaced = sorted(n for n in conns if n not in nodes_pos)
    stale = sorted(n for n in layout["nodes"] if n not in conns)

    backdrop = None
    bd = layout.get("backdrop")
    if bd and Path(bd["image_path"]).exists():
        ip = Path(bd["image_path"])
        try:
            from PIL import Image as _Image
            iw, ih = _Image.open(ip).size
        except Exception:
            iw, ih = bd.get("width_px", 1000), bd.get("height_px", 1000)
        m = float(bd["mm_per_px"])
        ox, oy = bd["origin_px"]
        backdrop = {"href": f"data:{MIME.get(ip.suffix.lower(), 'image/png')};base64,"
                            + base64.b64encode(ip.read_bytes()).decode(),
                    "x": -ox * m, "y": -oy * m, "w": iw * m, "h": ih * m}

    xs, ys = [], []
    if backdrop:
        xs += [backdrop["x"], backdrop["x"] + backdrop["w"]]
        ys += [backdrop["y"], backdrop["y"] + backdrop["h"]]
    for p in list(nodes_pos.values()) + [q for r in layout["runs"] for q in r["path"]]:
        xs.append(p[0]); ys.append(p[1])
    bounds = [min(xs), min(ys), max(xs), max(ys)] if xs else [0, 0, 1000, 1000]

    return {"title": harness.metadata.get("title", "") if hasattr(harness, "metadata") and isinstance(harness.metadata, dict) else "",
            "backdrop": backdrop, "bounds": bounds, "trunks": trunks,
            "nodes": nodes, "wires": wires, "unplaced": unplaced,
            "stale": stale, "unrouted": unrouted, "one_ended": one_ended,
            "insets": [{"name": str(i.get("name", "")), "box": [float(v) for v in i["box"]]}
                       for i in (layout.get("insets") or []) if len(i.get("box") or []) == 4],
            "source": layout.get("_source")}


def carview_summary(view: dict) -> str:
    placed = sum(1 for n in view["nodes"].values() if n["x"] is not None)
    auto = sum(1 for n in view["nodes"].values() if n.get("auto"))
    routed = sum(1 for w in view["wires"] if w.get("route"))
    straight = sum(1 for w in view["wires"] if w.get("route") and w.get("trunk") is False)
    parts = [f"{placed}/{len(view['nodes'])} connectors placed"
             + (f" ({auto} automatically)" if auto else ""),
             f"{routed}/{len(view['wires'])} wires drawn"]
    if straight:
        parts.append(f"{straight} drawn straight (no trunk joins their ends)")
    if view["stale"]:
        parts.append(f"layout names not in the model: {', '.join(view['stale'])}")
    return "; ".join(parts)


# ----------------------------------------------------------------------- page
def render_carview(harness, layout_path, title: Optional[str] = None) -> str:
    view = build_carview(harness, load_layout(layout_path))
    if title:
        view["title"] = title
    data = json.dumps(view, separators=(",", ":")).replace("</", "<\\/")
    return (_PAGE.replace("__TITLE__", escape(view["title"] or "Vehicle view"))
            .replace("__DATA__", data))


_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--bg:#f4f3ef;--panel:#ffffff;--ink:#1d1d1b;--mute:#6b6a65;--line:#d9d7cf;--accent:#c4540f;--sel:#c4540f;--dim:.35}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#171716;--panel:#22221f;--ink:#ecebe6;--mute:#a19f97;--line:#3a3935;--accent:#f08a3e;--sel:#f08a3e}
 :root:not([data-theme="light"]) #bd{filter:invert(.88) hue-rotate(180deg);opacity:.5}}
#bd{opacity:.42}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);font:14px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif}
#app{display:flex;height:100%}
#stage{flex:1;position:relative;overflow:hidden;touch-action:none}
svg#cv{width:100%;height:100%;display:block;cursor:grab}
svg#cv.drag{cursor:grabbing}
#bar{position:absolute;left:12px;top:12px;display:flex;gap:6px;flex-wrap:wrap;align-items:center}
#bar button,#bar input{font:inherit;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:6px;padding:4px 9px}
#bar button:hover{border-color:var(--accent)}
#side{width:min(560px,46vw);border-left:1px solid var(--line);background:var(--panel);overflow:auto;padding:14px 16px}
#side h2{margin:0 0 2px;font-size:18px}#side .sub{color:var(--mute);font-size:12px;margin-bottom:10px}
table{border-collapse:collapse;width:100%;font-size:12.5px}td,th{padding:3px 5px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--mute);font-weight:600}tr.wrow:hover{background:color-mix(in srgb,var(--accent) 12%,transparent);cursor:pointer}
.sw{display:inline-block;width:22px;height:11px;border:1px solid #555;vertical-align:-1px;margin-right:4px}
a.far{color:var(--accent);cursor:pointer;text-decoration:none}a.far:hover{text-decoration:underline}
.badge{display:inline-block;font-size:11px;padding:1px 6px;border-radius:9px;border:1px solid var(--line);color:var(--mute)}
.badge.ok{border-color:#2f8f4e;color:#2f8f4e}.badge.warn{border-color:#b7791f;color:#b7791f}
.node{cursor:pointer}.node .hs{fill:transparent}.node.auto .outline{fill:#fff;stroke:#555;stroke-dasharray:3 2}.node.auto circle:not(.outline){display:none}.node.auto text{font-size:13px;font-weight:500}
.node text{font:600 22px system-ui,sans-serif;fill:#111;paint-order:stroke;stroke:#fff;stroke-width:5px}
.dimmed .node:not(.on):not(.far){opacity:var(--dim)}.dimmed #trunks{opacity:.55}
.node.on .outline{stroke:var(--sel);stroke-width:5}.node.far .outline{stroke:var(--sel);stroke-width:3.5;stroke-dasharray:8 5}
#face svg{width:100%;max-height:260px}
.hint{color:var(--mute);font-size:12px;background:var(--panel);padding:3px 6px;border-radius:5px}
#editbar{display:inline-flex;gap:6px;align-items:center}#editbar[hidden]{display:none}
.vh{cursor:move}
#exp{position:fixed;inset:0;background:rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;z-index:5}#exp[hidden]{display:none}
#exp .box{background:var(--panel);color:var(--ink);width:min(900px,92vw);height:min(80vh,800px);display:flex;flex-direction:column;gap:8px;padding:14px;border-radius:10px}
#exp .row{display:flex;gap:6px;align-items:center}#exp textarea{flex:1;font:12px/1.4 ui-monospace,Menlo,monospace;background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:8px}
#exp button{font:inherit;border:1px solid var(--line);background:var(--panel);color:var(--ink);border-radius:6px;padding:4px 9px}
.note{color:var(--mute);font-size:12px;margin-top:10px}
@media (max-width:760px){#app{flex-direction:column}#side{width:auto;height:46%;border-left:0;border-top:1px solid var(--line)}}
</style></head><body><div id="app">
<div id="stage"><svg id="cv" xmlns="http://www.w3.org/2000/svg">
<g id="world"><g id="bdl"></g><g id="trunks"></g><g id="hl"></g><g id="nodes"></g></g></svg>
<div id="bar"><button id="fit">Fit</button><span id="insets"></span><button id="editbtn">Edit layout</button>
<span id="editbar" hidden><button id="newtrunk">New trunk</button><button id="fintrunk">Finish trunk</button><button id="exportbtn">Export layout</button> <span id="ehint" class="hint"></span></span>
<input id="q" list="names" placeholder="find connector" size="14"><datalist id="names"></datalist></div></div>
<div id="side"><div id="info"></div></div></div>
<div id="exp" hidden><div class="box"><div class="row"><b>Layout file</b><span style="flex:1"></span><button id="expcopy">Copy</button><button id="expdl">Download</button><button id="expclose">Close</button></div>
<textarea id="expout" spellcheck="false"></textarea><p class="note">Save this over the layout file and rebuild the page: wires re-route and splices re-place on the next build.</p></div></div>
<script id="cv-data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('cv-data').textContent);
const NS='http://www.w3.org/2000/svg', svg=document.getElementById('cv'), world=document.getElementById('world');
const el=(t,a={},p)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);if(p)p.appendChild(e);return e};
const esc=s=>String(s??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
const short=s=>{s=String(s??'');const c=s.search(/[(:;]/);s=c>8?s.slice(0,c):s;return s.length>34?s.slice(0,32)+'…':s};
let vb=null, sel=null;
function setVB(b){vb=b;svg.setAttribute('viewBox',b.join(' '))}
function fitTo(x0,y0,x1,y1){const r=svg.getBoundingClientRect(),pad=.04*Math.max(x1-x0,y1-y0);
  let w=x1-x0+2*pad,h=y1-y0+2*pad;const ar=r.width/Math.max(r.height,1);
  if(w/h<ar){const nw=h*ar;x0-=(nw-w)/2;w=nw}else{const nh=w/ar;y0-=(nh-h)/2;h=nh}setVB([x0-pad,y0-pad,w,h])}
function fit(){const b=D.bounds;fitTo(b[0],b[1],b[2],b[3])}
// ---- backdrop + trunks
if(D.backdrop){const b=D.backdrop;el('image',{id:'bd',href:b.href,x:b.x,y:b.y,width:b.w,height:b.h,preserveAspectRatio:'none'},document.getElementById('bdl'))}
const TG=document.getElementById('trunks');
for(const t of D.trunks){el('line',{x1:t.pts[0][0],y1:t.pts[0][1],x2:t.pts[1][0],y2:t.pts[1][1],stroke:'#000','stroke-width':Math.max(t.d,8),'stroke-linecap':'round',opacity:t.n?1:.45},TG)}
// ---- connector glyphs (face drawings from the model's part numbers)
function faceSVG(f,size,fill){const w=f.shape==='round'?size:size,h=f.shape==='round'?size:size/f.aspect;
  const g=el('g');const pad=size*.08;
  if(f.shape==='round')el('circle',{class:'outline',cx:w/2,cy:h/2,r:w/2,fill:f.housing||'#3b3b3b',stroke:'#111','stroke-width':2},g);
  else if(f.shape==='tri')el('path',{class:'outline',d:`M${w*.06} ${h*.04} L${w*.94} ${h*.04} L${w/2} ${h*.98} Z`,'stroke-linejoin':'round',fill:f.housing||'#3b3b3b',stroke:'#111','stroke-width':2},g);
  else el('rect',{class:'outline',x:0,y:0,width:w,height:h,rx:Math.min(w,h)*.18,fill:f.housing||'#3b3b3b',stroke:'#111','stroke-width':2},g);
  const n=f.cavities.length,P=f.cavities.map(c=>[pad+c.x*(w-2*pad),pad+c.y*(h-2*pad)]);let md=Infinity;  // size cavities from their spacing
  for(let i=0;i<n;i++)for(let j=i+1;j<n;j++)md=Math.min(md,Math.hypot(P[i][0]-P[j][0],P[i][1]-P[j][1]));
  const cr0=Math.max(2,Math.min(Math.min(w,h)*.13,isFinite(md)?md*.36:Infinity));
  const SZ={4:1.9,8:1.6,12:1.35,16:1,20:.72};
  for(const c of f.cavities){const cx=pad+c.x*(w-2*pad),cy=pad+c.y*(h-2*pad),hx=fill&&fill(c.id),cr=cr0*(SZ[c.size]||1);
    if(hx&&hx.length>1){el('circle',{cx,cy,r:cr,fill:hx[0],stroke:'#000','stroke-width':.8},g);
      el('path',{d:`M${cx-cr} ${cy} A${cr} ${cr} 0 0 0 ${cx+cr} ${cy} Z`,fill:hx[1]},g)}
    else el('circle',{cx,cy,r:cr,fill:hx?hx[0]:'#d8d6cf',stroke:'#000','stroke-width':.8},g)}
  return {g,w,h}}
const NG=document.getElementById('nodes'),GLYPH={};
function makeGlyph(n){const d=D.nodes[n];if(GLYPH[n])GLYPH[n].remove();
  const size=d.auto?26:d.face.shape==='round'?46:Math.min(110,48+d.face.cavities.length*3);
  const {g,w,h}=faceSVG(d.face,size);g.setAttribute('class','node'+(d.auto?' auto':''));g.dataset.n=n;g._w=w;g._h=h;
  g.setAttribute('transform',`translate(${d.x-w/2},${d.y-h/2})`);
  el('rect',{class:'hs',x:-8,y:-8,width:w+16,height:h+40},g);
  const t=el('text',{x:w/2,y:h+24,'text-anchor':'middle'},g);t.textContent=n;
  NG.appendChild(g);GLYPH[n]=g;g.addEventListener('click',e=>{e.stopPropagation();if(!editing)select(n)})}
for(const [n,d] of Object.entries(D.nodes))if(d.x!==null)makeGlyph(n);
// ---- wires of the selected connector, drawn along their routes
function offsetLine(pts,off){if(!off||pts.length<2)return pts;const out=[],nrm=(a,b)=>{const dx=b[0]-a[0],dy=b[1]-a[1],L=Math.hypot(dx,dy)||1;return[-dy/L,dx/L]};
  for(let i=0;i<pts.length;i++){const p=pts[i];let n;
    if(i===0)n=nrm(pts[0],pts[1]);else if(i===pts.length-1)n=nrm(pts[i-1],pts[i]);
    else{const n1=nrm(pts[i-1],p),n2=nrm(p,pts[i+1]);let mx=n1[0]+n2[0],my=n1[1]+n2[1];const ml=Math.hypot(mx,my);
      if(ml<.3){n=n1}else{mx/=ml;my/=ml;const k=Math.min(3,1/Math.max(.35,mx*n1[0]+my*n1[1]));n=[mx*k,my*k]}}
    out.push([p[0]+n[0]*off,p[1]+n[1]*off])}return out}
const HL=document.getElementById('hl');
function wiresOf(n){return D.wires.filter(w=>w.from[0]===n||w.to[0]===n)}
function drawWires(ws,focus){HL.innerHTML='';const n=ws.filter(w=>w.route).length,pitch=Math.min(7,70/Math.max(n-1,1)),base=Math.max(2.4,Math.min(7,pitch*1.05));
  ws.forEach((w,k)=>{if(!w.route)return;const off=(k-(ws.length-1)/2)*pitch;
    const pts=offsetLine(w.route,off).map(p=>p.join(',')).join(' ');const wd=focus?(focus===w.id?8:base*.6):base;
    const op=focus&&focus!==w.id?.35:1;
    el('polyline',{points:pts,fill:'none',stroke:'#000','stroke-width':wd+2.4,'stroke-linejoin':'round','stroke-linecap':'round',opacity:op,'stroke-dasharray':w.trunk===false?'30 18':''},HL);
    el('polyline',{points:pts,fill:'none',stroke:w.colors[0],'stroke-width':wd,'stroke-linejoin':'round','stroke-linecap':'round',opacity:op,'stroke-dasharray':w.trunk===false?'30 18':''},HL);
    if(w.colors.length>1)el('polyline',{points:pts,fill:'none',stroke:w.colors[1],'stroke-width':wd*.45,'stroke-dasharray':'10 10','stroke-linejoin':'round',opacity:op},HL)})}
function cavityFill(n){const m={},len={};  // several wires in one cavity: show the longest (a mate or jumper link is short)
  for(const w of wiresOf(n))for(const end of [w.from,w.to])if(end[0]===n){const k=String(end[1]),l=w.len_mm||0;
    if(!(k in len)||l>len[k]){m[k]=w.colors;len[k]=l}}
  return id=>m[String(id)]}
function select(n){sel=n;const d=D.nodes[n];svg.classList.add('dimmed');
  Object.values(GLYPH).forEach(g=>g.classList.remove('on','far'));const ws=wiresOf(n);
  if(GLYPH[n])GLYPH[n].classList.add('on');
  for(const w of ws){const o=w.from[0]===n?w.to[0]:w.from[0];if(o&&GLYPH[o]&&o!==n)GLYPH[o].classList.add('far')}
  drawWires(ws);
  const f=d.face,FS=f.cavities.length>20?460:260,big=faceSVG(f,FS,cavityFill(n));const fs=el('svg',{viewBox:`-6 -6 ${big.w+12} ${big.h+12}`});fs.appendChild(big.g);
  for(const c of f.cavities){const pad=FS*.08,cx=pad+c.x*(big.w-2*pad),cy=pad+c.y*(big.h-2*pad);
    const t=el('text',{x:cx,y:cy+4,'text-anchor':'middle','font-size':f.cavities.length>12?9:12,'font-weight':700,fill:'#fff',stroke:'#000','stroke-width':2.2,'paint-order':'stroke'},big.g);t.textContent=c.id}
  const byPin={};for(const w of ws){const mine=w.from[0]===n?w.from[1]:w.to[1];(byPin[mine]=byPin[mine]||[]).push(w)}
  let rows='';for(const [pin,label] of d.pins){const list=byPin[pin]||[];
    if(!list.length){rows+=`<tr><td>${esc(pin)}</td><td title="${esc(label)}">${esc(short(label))}</td><td colspan="4" style="color:var(--mute)">no wire</td></tr>`;continue}
    for(const w of list){const far=w.from[0]===n?w.to:w.from;const sw=w.colors.length>1?`background:linear-gradient(${w.colors[0]} 0 33%,${w.colors[1]} 33% 67%,${w.colors[0]} 67%)`:`background:${w.colors[0]}`;
      const farTxt=far[0]?`<a class="far" data-n="${esc(far[0])}">${esc(far[0])}</a> ${esc(far[1])}${D.nodes[far[0]]&&D.nodes[far[0]].x===null?' <span class="badge warn">not placed</span>':''}`:'<span class="badge warn">one end only</span>';
      rows+=`<tr class="wrow" data-w="${esc(w.id)}"><td>${esc(pin)}</td><td title="${esc(label)}">${esc(short(label))}</td><td><span class="sw" style="${sw}"></span>${esc(w.code)}</td><td>${esc(w.gauge)}</td><td>${esc(w.cable)}</td><td>${farTxt}${w.len_mm?` <span style="color:var(--mute)">${(w.len_mm/1000).toFixed(2)} m</span>`:''}</td></tr>`}}
  const info=document.getElementById('info');
  info.innerHTML=`<h2>${esc(n)}</h2><div class="sub">${esc(d.type)}${d.mpn?' · '+esc(d.mpn):''}</div><div id="face"></div>
   <div class="sub">${esc(f.view)} <span class="badge ${f.verified?'ok':'warn'}">${f.verified?'layout from maker drawing':'layout illustrative'}</span>${f.source?` <span title="${esc(f.source)}" class="badge">source</span>`:''}</div>
   <table><tr><th>Cavity</th><th>Signal</th><th>Colour</th><th>Gauge</th><th>Cable</th><th>Other end · routed</th></tr>${rows}</table>
   ${d.x===null?'<p class="note">This connector is not placed on the vehicle yet.</p>':''}`;
  document.getElementById('face').appendChild(fs);
  info.querySelectorAll('a.far').forEach(a=>a.addEventListener('click',()=>{const m=a.dataset.n;if(D.nodes[m])select(m)}));
  info.querySelectorAll('tr.wrow').forEach(r=>{r.addEventListener('mouseenter',()=>drawWires(ws,r.dataset.w));r.addEventListener('mouseleave',()=>drawWires(ws))})}
function clear(){sel=null;svg.classList.remove('dimmed');HL.innerHTML='';Object.values(GLYPH).forEach(g=>g.classList.remove('on','far'));overview()}
function overview(){const placed=Object.values(D.nodes).filter(n=>n.x!==null).length;
  document.getElementById('info').innerHTML=`<h2>${esc(D.title||'Vehicle view')}</h2><div class="sub">${placed} of ${Object.keys(D.nodes).length} connectors placed · ${D.wires.filter(w=>w.route).length} of ${D.wires.length} wires drawn</div>
  ${editing?`<p><b>Editing the layout.</b> Drag connectors and trunk points (they snap to 5 mm; dropping a point on another joins them). Shift-click a point to delete it. New trunk, click its waypoints, then Finish trunk. Click a name below to place it. Export layout when done.</p>`
   :`<p>Click a connector to light up its wires in their colours, along the trunks, to the connector at each wire's other end. Hover a row to pick out one wire. Drag to pan, wheel or pinch to zoom.</p>`}
  ${dirty?`<p class="note"><b>Layout edited.</b> Wire routes and splice positions are from before the edit; export the layout and rebuild to update them.</p>`:''}
  ${D.unplaced.length?`<p class="note"><b>Not placed yet (${D.unplaced.length}):</b> ${D.unplaced.map(n=>`<a class="far" data-n="${esc(n)}">${esc(n)}</a>`).join(', ')}</p>`:''}
  ${D.stale.length?`<p class="note"><b>In the layout but not in the model:</b> ${D.stale.map(esc).join(', ')}</p>`:''}`;
  document.querySelectorAll('#info a.far').forEach(a=>a.addEventListener('click',()=>{if(editing){if(D.nodes[a.dataset.n].x===null){armed=a.dataset.n;hintEdit()}}else select(a.dataset.n)}))}
// ---- layout editing: drag connectors and trunk points, draw trunks, export
const SRC=D.source;let editing=false,dirty=false,tool=null,drawPts=null,armed=null,edrag=null,newRuns=0;
const RUNS=SRC?SRC.runs.map((r,i)=>Object.assign({},r,{_pre:(SRC.runs_pre||{})[i]||[]})):[];
const EL=el('g',{id:'edit'},world);
function worldPt(e){const p=svg.createSVGPoint();p.x=e.clientX;p.y=e.clientY;const q=p.matrixTransform(svg.getScreenCTM().inverse());
  return[Math.round(q.x/5)*5,Math.round(q.y/5)*5]}
const pkey=p=>p[0]+','+p[1];
function drawEdit(){EL.innerHTML='';if(!editing&&!dirty)return;
  for(const r of RUNS)if(r.path.length>1)el('polyline',{points:r.path.map(p=>p.join(',')).join(' '),fill:'none',stroke:'#000','stroke-width':editing?6:8,'stroke-linejoin':'round',opacity:.85},EL);
  if(!editing)return;
  if(drawPts&&drawPts.length)el('polyline',{points:drawPts.map(p=>p.join(',')).join(' '),fill:'none',stroke:'#c4540f','stroke-width':7,'stroke-dasharray':'14 8'},EL);
  const seen=new Set();for(const r of RUNS)for(const p of r.path){const k=pkey(p);if(seen.has(k))continue;seen.add(k);
    const c=el('circle',{class:'vh',cx:p[0],cy:p[1],r:13,fill:'#fff',stroke:'#000','stroke-width':3},EL);c.dataset.k=k}}
function hintEdit(){const h=document.getElementById('ehint');
  h.textContent=armed?`click the car to place ${armed}`:tool==='draw'?'click waypoints (click an existing point to join it), then Finish trunk':'drag connectors and trunk points; shift-click a point to delete it'}
function setEditing(on){editing=on;tool=null;drawPts=null;armed=null;document.getElementById('editbar').hidden=!on;
  document.getElementById('editbtn').textContent=on?'Done editing':'Edit layout';
  if(on)clear();TG.style.display=(on||dirty)?'none':'';drawEdit();hintEdit();overview()}
function moveNode(n,x,y){const d=D.nodes[n],g=GLYPH[n];d.x=x;d.y=y;g.setAttribute('transform',`translate(${x-g._w/2},${y-g._h/2})`);dirty=true}
function editDown(e){if(!editing)return false;const t=e.target;
  if(armed){const p=worldPt(e),n=armed;D.nodes[n].x=p[0];D.nodes[n].y=p[1];makeGlyph(n);D.unplaced=D.unplaced.filter(m=>m!==n);armed=null;dirty=true;hintEdit();overview();return true}
  if(tool==='draw'){const p=t.classList&&t.classList.contains('vh')?t.dataset.k.split(',').map(Number):worldPt(e);(drawPts=drawPts||[]).push(p);drawEdit();return true}
  if(t.classList&&t.classList.contains('vh')){const k=t.dataset.k;
    if(e.shiftKey){for(const r of RUNS)r.path=r.path.filter(p=>pkey(p)!==k);for(let i=RUNS.length-1;i>=0;i--)if(RUNS[i].path.length<2)RUNS.splice(i,1);dirty=true;drawEdit();return true}
    edrag={k};svg.setPointerCapture(e.pointerId);return true}
  const g=t.closest&&t.closest('.node');if(g&&!g.classList.contains('auto')){edrag={n:g.dataset.n};svg.setPointerCapture(e.pointerId);return true}
  return false}
function editMove(e){if(!edrag)return false;const p=worldPt(e);
  if(edrag.n)moveNode(edrag.n,p[0],p[1]);
  else{for(const r of RUNS)r.path=r.path.map(q=>pkey(q)===edrag.k?p:q);edrag.k=pkey(p);dirty=true;drawEdit()}return true}
function editUp(){if(!edrag)return false;edrag=null;return true}
const flow=o=>'{'+Object.entries(o).filter(([k])=>k[0]!=='_').map(([k,v])=>`${k}: ${JSON.stringify(v)}`).join(', ')+'}';
const nodeLine=(n,d,note)=>`  ${(n+':').padEnd(13)} [${Math.round(d.x)}, ${Math.round(d.y)}]`+(note?`  # ${note}`:'');
function layoutYaml(){const L=[...SRC.header];if(dirty)L.push(`# edited in the car view, ${new Date().toISOString().slice(0,10)}`);
  const order=[...SRC.order];for(const k of ['nodes','runs'])if(!order.includes(k))order.push(k);
  for(const k of order){L.push('');
    if(k==='nodes'){L.push('nodes:');const done=new Set();
      for(const nd of SRC.nodes){const d=D.nodes[nd.name];done.add(nd.name);
        if(!d){const q=(SRC.pos||{})[nd.name]||[0,0];nd.pre.forEach(c=>L.push('  '+c));L.push(nodeLine(nd.name,{x:q[0],y:q[1]},nd.note));continue}
        if(d.x===null||d.auto)continue;nd.pre.forEach(c=>L.push('  '+c));L.push(nodeLine(nd.name,d,nd.note))}
      const extra=Object.keys(D.nodes).filter(n=>!done.has(n)&&D.nodes[n].x!==null&&!D.nodes[n].auto);
      if(extra.length){L.push('  # ---- placed in the car view');extra.forEach(n=>L.push(nodeLine(n,D.nodes[n],'')))}}
    else if(k==='runs'){L.push('runs:');for(const r of RUNS){r._pre.forEach(c=>L.push('  '+c));L.push('  - '+flow(r))}}
    else if(k==='insets'){L.push('insets:');(SRC.insets||[]).forEach(i=>L.push('  - '+flow(i)))}
    else{const v=SRC.top[k];if(v&&typeof v==='object'&&!Array.isArray(v)){L.push(k+':');for(const [a,b] of Object.entries(v))L.push(`  ${a}: ${JSON.stringify(b)}`)}
      else L.push(`${k}: ${JSON.stringify(v)}`)}}
  return L.join('\n')+'\n'}
document.getElementById('editbtn').onclick=()=>setEditing(!editing);
document.getElementById('newtrunk').onclick=()=>{tool='draw';drawPts=[];hintEdit();drawEdit()};
document.getElementById('fintrunk').onclick=()=>{if(drawPts&&drawPts.length>1){RUNS.push({name:`NEW TRUNK ${++newRuns}`,path:drawPts,_pre:[]});dirty=true}
  tool=null;drawPts=null;hintEdit();drawEdit()};
document.getElementById('exportbtn').onclick=()=>{document.getElementById('expout').value=layoutYaml();document.getElementById('exp').hidden=false};
document.getElementById('expclose').onclick=()=>{document.getElementById('exp').hidden=true};
document.getElementById('expcopy').onclick=()=>navigator.clipboard&&navigator.clipboard.writeText(document.getElementById('expout').value);
document.getElementById('expdl').onclick=()=>{const a=document.createElement('a');
  a.href=URL.createObjectURL(new Blob([document.getElementById('expout').value],{type:'text/yaml'}));a.download=SRC.file||'layout.yml';a.click()};
window.addEventListener('keydown',e=>{if(e.key==='Escape'&&editing){tool=null;drawPts=null;armed=null;hintEdit();drawEdit()}});
if(!SRC)document.getElementById('editbtn').hidden=true;
// ---- pan and zoom
let drag=null;const pts=new Map();
svg.addEventListener('pointerdown',e=>{if(editDown(e))return;svg.setPointerCapture(e.pointerId);pts.set(e.pointerId,[e.clientX,e.clientY]);drag={x:e.clientX,y:e.clientY,vb:vb.slice(),moved:false};svg.classList.add('drag')});
svg.addEventListener('pointermove',e=>{if(editMove(e))return;if(!drag)return;const r=svg.getBoundingClientRect();
  if(pts.size===2&&pts.has(e.pointerId)){const [a,b]=[...pts.values()];const d0=Math.hypot(a[0]-b[0],a[1]-b[1]);pts.set(e.pointerId,[e.clientX,e.clientY]);
    const [c,d]=[...pts.values()];const d1=Math.hypot(c[0]-d[0],c[1]-d[1]);if(d0>0)zoomAt((c[0]+d[0])/2,(c[1]+d[1])/2,d0/d1);drag.moved=true;return}
  const s=vb[2]/r.width,dx=(e.clientX-drag.x)*s,dy=(e.clientY-drag.y)*s;if(Math.abs(dx)+Math.abs(dy)>2*s)drag.moved=true;
  setVB([drag.vb[0]-dx,drag.vb[1]-dy,vb[2],vb[3]])});
svg.addEventListener('pointerup',e=>{pts.delete(e.pointerId);if(editUp(e))return;svg.classList.remove('drag');if(drag&&!drag.moved&&e.target===svg&&!editing)clear();drag=null});
function zoomAt(cx,cy,k){const r=svg.getBoundingClientRect(),x=vb[0]+(cx-r.left)/r.width*vb[2],y=vb[1]+(cy-r.top)/r.height*vb[3];
  setVB([x-(x-vb[0])*k,y-(y-vb[1])*k,vb[2]*k,vb[3]*k])}
svg.addEventListener('wheel',e=>{e.preventDefault();zoomAt(e.clientX,e.clientY,Math.exp(e.deltaY*.0015))},{passive:false});
document.getElementById('fit').onclick=fit;
const IN=document.getElementById('insets');for(const i of D.insets){const b=document.createElement('button');b.textContent=i.name;b.onclick=()=>fitTo(...i.box);IN.appendChild(b)}
const DL=document.getElementById('names');for(const n of Object.keys(D.nodes).sort()){const o=document.createElement('option');o.value=n;DL.appendChild(o)}
document.getElementById('q').addEventListener('change',e=>{const n=e.target.value.trim().toUpperCase();const m=Object.keys(D.nodes).find(k=>k.toUpperCase()===n);
  if(m){select(m);const d=D.nodes[m];if(d.x!==null)fitTo(d.x-500,d.y-350,d.x+500,d.y+350)}});
window.addEventListener('resize',()=>{if(vb)setVB(vb)});
fit();overview();
</script></body></html>
"""
