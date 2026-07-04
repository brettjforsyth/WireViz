# -*- coding: utf-8 -*-
"""1:1 formboard (nail-board) output for WireViz harnesses.

A formboard is a full-scale drawing of the harness laid out flat. It is printed
at 1:1, taped to a board, and the real connectors/wires are built directly on
top of it — so the drawn geometry must be at true physical scale and each
bundle must carry its exact length.

This renders the harness to an SVG whose user unit is one millimetre and whose
``width``/``height`` carry a ``mm`` suffix, so it prints life-size. Connectors
are placed at physical positions (columns spaced by cable length), each cable is
drawn as an orthogonal bundle run labelled with its exact length, and a dashed
page grid shows how the board tiles across sheets of the chosen size.

Geometry is exact (drawn length == physical length) for the common case where
each connector is reached by a single cable (linear and tree harnesses); where a
connector is fed by several cables of differing length the column spacing
follows the longest, and every bundle still carries its true length as a label.
"""

from collections import Counter
from dataclasses import dataclass, field
from html import escape
from typing import Dict, List, Optional, Tuple

# millimetres per unit
_UNIT_MM = {
    "mm": 1.0,
    "cm": 10.0,
    "m": 1000.0,
    "in": 25.4,
    '"': 25.4,
    "ft": 304.8,
    "'": 304.8,
    "yd": 914.4,
}

# printable sheet sizes in mm (portrait width x height)
PAGE_SIZES = {
    "A4": (210.0, 297.0),
    "A3": (297.0, 420.0),
    "A2": (420.0, 594.0),
    "A1": (594.0, 841.0),
    "A0": (841.0, 1189.0),
    "letter": (215.9, 279.4),
    "tabloid": (279.4, 431.8),
}


def to_mm(value: float, unit: Optional[str]) -> float:
    return float(value or 0) * _UNIT_MM.get((unit or "mm").strip().lower(), 1.0)


@dataclass
class FormboardConfig:
    page: str = "A3"
    landscape: bool = True
    page_margin: float = 10.0  # mm, printable border on each sheet
    connector_w: float = 18.0  # mm
    header_h: float = 8.0  # mm
    pin_h: float = 6.0  # mm per pin
    row_gap: float = 25.0  # mm between stacked connectors
    min_gap: float = 20.0  # mm minimum horizontal cable run
    default_length: float = 100.0  # mm, used when a cable has no length
    bundle_width: float = 2.5  # mm stroke
    peg_radius: float = 3.0  # mm mounting-peg marker
    margin: float = 15.0  # mm drawing border

    def page_wh(self) -> Tuple[float, float]:
        w, h = PAGE_SIZES.get(self.page, PAGE_SIZES["A3"])
        return (h, w) if self.landscape else (w, h)


def _cable_endpoints(cable) -> Tuple[Optional[str], Optional[str]]:
    """Most common (from_connector, to_connector) across a cable's connections."""
    froms = Counter(c.from_name for c in cable.connections if c.from_name)
    tos = Counter(c.to_name for c in cable.connections if c.to_name)
    f = froms.most_common(1)[0][0] if froms else None
    t = tos.most_common(1)[0][0] if tos else None
    return f, t


def _connector_height(conn, cfg) -> float:
    return cfg.header_h + max(len(conn.pins), 1) * cfg.pin_h


def _assign_columns(harness, links) -> Dict[str, int]:
    """Longest-path column per connector over from->to cable links."""
    names = list(harness.connectors.keys())
    col = {n: 0 for n in names}
    for _ in range(len(names) + 1):
        changed = False
        for f, t, _l, _c in links:
            if f in col and t in col and col[t] < col[f] + 1:
                col[t] = col[f] + 1
                changed = True
        if not changed:
            break
    return col


def build_formboard(harness, cfg: Optional[FormboardConfig] = None) -> dict:
    """Compute the physical (mm) formboard layout."""
    cfg = cfg or FormboardConfig()

    # cable links with physical length in mm
    links = []  # (from, to, length_mm, cable)
    for name, cable in harness.cables.items():
        f, t = _cable_endpoints(cable)
        if not f or not t or f not in harness.connectors or t not in harness.connectors:
            continue
        length_mm = to_mm(cable.length, cable.length_unit) or cfg.default_length
        links.append((f, t, length_mm, cable))

    col = _assign_columns(harness, links)
    columns: Dict[int, List[str]] = {}
    for name in harness.connectors:
        columns.setdefault(col[name], []).append(name)

    # y positions (independent of x): stack connectors within each column
    conns: Dict[str, dict] = {}
    for c in sorted(columns):
        y = cfg.margin
        for name in columns[c]:
            conn = harness.connectors[name]
            h = _connector_height(conn, cfg)
            conns[name] = {
                "name": name,
                "y": y,
                "h": h,
                "cy": y + h / 2,
                "pincount": len(conn.pins),
                "col": c,
            }
            y += h + cfg.row_gap

    # x positions: each column placed so the longest incoming cable is 1:1
    incoming: Dict[int, List[tuple]] = {}
    for f, t, length_mm, cable in links:
        incoming.setdefault(col[t], []).append((f, t, length_mm))
    col_x: Dict[int, float] = {}
    prev_right = cfg.margin
    for c in sorted(columns):
        if c == min(columns):
            x = cfg.margin
        else:
            x = prev_right + cfg.min_gap  # fallback if nothing feeds this column
            for f, t, length_mm in incoming.get(c, []):
                dy = abs(conns[t]["cy"] - conns[f]["cy"])
                gap = max(cfg.min_gap, length_mm - dy)
                x = max(x, conns[f]["x"] + cfg.connector_w + gap)
        for name in columns[c]:
            conns[name]["x"] = x
        prev_right = max(prev_right, x + cfg.connector_w)
        col_x[c] = x

    # bundle geometry
    bundles = []
    for f, t, length_mm, cable in links:
        a = conns[f]
        b = conns[t]
        x0 = a["x"] + cfg.connector_w
        x1 = b["x"]
        y0, y1 = a["cy"], b["cy"]
        h_total = max(x1 - x0, 0)
        dy = abs(y1 - y0)
        manhattan = h_total + dy
        short = length_mm + 0.5 < manhattan
        # midpoint jog
        xm = x0 + h_total / 2
        points = [(x0, y0), (xm, y0), (xm, y1), (x1, y1)]
        label = f"{cable.name}: {round(length_mm)} mm"
        if cable.wirecount:
            label += f"  ({cable.wirecount}×)"
        bundles.append(
            {
                "cable": cable.name,
                "points": points,
                "length_mm": round(length_mm, 1),
                "label": label,
                "short": short,
                "mid": (xm, (y0 + y1) / 2),
            }
        )

    width = prev_right + cfg.margin
    height = max((c["y"] + c["h"] for c in conns.values()), default=cfg.margin) + cfg.margin
    return {"connectors": conns, "bundles": bundles, "width": width, "height": height}


def page_grid(layout: dict, cfg: Optional[FormboardConfig] = None) -> dict:
    """Return page tiling info: printable size and column/row counts."""
    cfg = cfg or FormboardConfig()
    pw, ph = cfg.page_wh()
    printable_w = pw - 2 * cfg.page_margin
    printable_h = ph - 2 * cfg.page_margin
    import math

    cols = max(1, math.ceil(layout["width"] / printable_w))
    rows = max(1, math.ceil(layout["height"] / printable_h))
    return {
        "printable_w": printable_w,
        "printable_h": printable_h,
        "cols": cols,
        "rows": rows,
        "total": cols * rows,
    }


# --- SVG emission ----------------------------------------------------------


def _page_overlay(layout, grid, cfg) -> str:
    parts = []
    pw, ph = grid["printable_w"], grid["printable_h"]
    for i in range(1, grid["cols"]):
        x = i * pw
        parts.append(
            f'<line x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{layout["height"]:.1f}" '
            f'stroke="#c00" stroke-width="0.3" stroke-dasharray="4 3"/>'
        )
    for j in range(1, grid["rows"]):
        y = j * ph
        parts.append(
            f'<line x1="0" y1="{y:.1f}" x2="{layout["width"]:.1f}" y2="{y:.1f}" '
            f'stroke="#c00" stroke-width="0.3" stroke-dasharray="4 3"/>'
        )
    for j in range(grid["rows"]):
        for i in range(grid["cols"]):
            parts.append(
                f'<text x="{i * pw + 3:.1f}" y="{j * ph + 8:.1f}" '
                f'font-size="5" fill="#c00" font-family="sans-serif">'
                f"R{j + 1}C{i + 1}</text>"
            )
    return "".join(parts)


def _connector_svg(c, cfg) -> str:
    x, y, w, h = c["x"], c["y"], cfg.connector_w, c["h"]
    return (
        f'<g class="fb-connector">'
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="1.5" '
        f'fill="#fff" stroke="#111" stroke-width="0.6"/>'
        # mounting peg at the connector centre
        f'<circle cx="{x + w / 2:.1f}" cy="{c["cy"]:.1f}" r="{cfg.peg_radius:.1f}" '
        f'fill="none" stroke="#111" stroke-width="0.5"/>'
        f'<circle cx="{x + w / 2:.1f}" cy="{c["cy"]:.1f}" r="0.7" fill="#111"/>'
        f'<text x="{x + w / 2:.1f}" y="{y - 2:.1f}" font-size="5" '
        f'text-anchor="middle" font-family="sans-serif" fill="#111">'
        f'{escape(str(c["name"]))} ({c["pincount"]}p)</text>'
        f"</g>"
    )


def _bundle_svg(b, cfg) -> str:
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in b["points"])
    color = "#b00" if b["short"] else "#333"
    mx, my = b["mid"]
    warn = " ⚠ SHORT" if b["short"] else ""
    return (
        f'<g class="fb-bundle">'
        f'<polyline points="{pts}" fill="none" stroke="{color}" '
        f'stroke-width="{cfg.bundle_width}" stroke-linejoin="round" '
        f'stroke-linecap="round"/>'
        f'<text x="{mx:.1f}" y="{my - 2:.1f}" font-size="4.5" '
        f'text-anchor="middle" font-family="sans-serif" fill="{color}">'
        f'{escape(b["label"] + warn)}</text>'
        f"</g>"
    )


def render_formboard(harness, cfg: Optional[FormboardConfig] = None) -> str:
    """Render a 1:1 (life-size, mm-unit) formboard SVG with page tiling."""
    cfg = cfg or FormboardConfig()
    layout = build_formboard(harness, cfg)
    grid = page_grid(layout, cfg)
    w, h = layout["width"], layout["height"]
    body = [
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{w:.1f}mm" height="{h:.1f}mm" viewBox="0 0 {w:.1f} {h:.1f}">',
        f'<rect width="{w:.1f}" height="{h:.1f}" fill="#fff"/>',
        '<g class="fb-pages">',
        _page_overlay(layout, grid, cfg),
        "</g>",
        '<g class="fb-bundles">',
        *[_bundle_svg(b, cfg) for b in layout["bundles"]],
        "</g>",
        '<g class="fb-connectors">',
        *[_connector_svg(c, cfg) for c in layout["connectors"].values()],
        "</g>",
        f'<text x="2" y="{h - 2:.1f}" font-size="4" fill="#888" '
        f'font-family="sans-serif">1:1 formboard · {grid["cols"]}×'
        f'{grid["rows"]} {cfg.page} sheet(s) · print at 100%</text>',
        "</svg>",
    ]
    return "\n".join(body) + "\n"
