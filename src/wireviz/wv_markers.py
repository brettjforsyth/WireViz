# -*- coding: utf-8 -*-
"""Wire marker / label sheet generation.

Every terminated wire end gets a marker that says which wire it is and where the
other end goes, so an assembler can label wires as they build. Output is a CSV
(paste-ready for label-printer software) and a printable SVG label sheet.
"""

from dataclasses import dataclass
from html import escape
from typing import List, Optional

from wireviz.wv_idents import ident_string


@dataclass
class Marker:
    wire: str  # e.g. "W1:3"
    end: str  # 'from' | 'to'
    connector: str
    pin: object
    other: str  # "X2:1"
    color: str
    gauge: str
    ident: str
    text: str


def _is_shield(vp):
    return isinstance(vp, str) and vp.lower() == "s"


def _endpoint(name, pin):
    return f"{name}:{pin}" if name is not None else "—"


def build_markers(harness, template: Optional[str] = None) -> List[Marker]:
    """Two markers per wire (one per terminated end).

    `template` is a format string over: wire, this, other, color, gauge, ident.
    Default: ``"{wire}  {this}→{other}"``.
    """
    template = template or "{wire}  {this}→{other}"
    markers: List[Marker] = []
    for cname, cable in harness.cables.items():
        gauge = f"{cable.gauge} {cable.gauge_unit}".strip() if cable.gauge else ""
        for c in cable.connections:
            wid = "s" if _is_shield(c.via_port) else c.via_port
            wire = f"{cname}:{wid}"
            color = ""
            if isinstance(c.via_port, int) and 1 <= c.via_port <= len(cable.colors):
                color = cable.colors[c.via_port - 1] or ""
            ident = ident_string(c.via_port if isinstance(c.via_port, int) else "")
            for end, (nm, pn), (onm, opn) in (
                ("from", (c.from_name, c.from_pin), (c.to_name, c.to_pin)),
                ("to", (c.to_name, c.to_pin), (c.from_name, c.from_pin)),
            ):
                if nm is None:
                    continue  # open end, nothing to label
                text = template.format(
                    wire=wire,
                    this=_endpoint(nm, pn),
                    other=_endpoint(onm, opn),
                    color=color,
                    gauge=gauge,
                    ident=ident,
                )
                markers.append(
                    Marker(
                        wire=wire,
                        end=end,
                        connector=nm,
                        pin=pn,
                        other=_endpoint(onm, opn),
                        color=color,
                        gauge=gauge,
                        ident=ident,
                        text=text,
                    )
                )
    return markers


def to_csv(markers: List[Marker]) -> str:
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["marker", "wire", "end", "connector", "pin", "other", "color", "gauge", "ident"])
    for i, m in enumerate(markers, start=1):
        w.writerow([m.text, m.wire, m.end, m.connector, m.pin, m.other, m.color, m.gauge, m.ident])
    return buf.getvalue()


def to_svg_sheet(
    markers: List[Marker], cols: int = 4, label_w: float = 45, label_h: float = 14, gap: float = 2
) -> str:
    """A printable grid of labels (mm units, prints life-size)."""
    n = len(markers)
    rows = (n + cols - 1) // cols
    W = cols * (label_w + gap) + gap
    H = rows * (label_h + gap) + gap
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.1f}mm" '
        f'height="{H:.1f}mm" viewBox="0 0 {W:.1f} {H:.1f}">',
        f'<rect width="{W:.1f}" height="{H:.1f}" fill="#fff"/>',
    ]
    for i, m in enumerate(markers):
        r, c = divmod(i, cols)
        x = gap + c * (label_w + gap)
        y = gap + r * (label_h + gap)
        parts.append(
            f'<g class="label">'
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{label_w:.1f}" '
            f'height="{label_h:.1f}" rx="1.5" fill="none" stroke="#999" '
            f'stroke-width="0.3"/>'
            f'<text x="{x + 2:.1f}" y="{y + label_h / 2 + 1.5:.1f}" '
            f'font-size="3.5" font-family="monospace" fill="#111">'
            f"{escape(m.text)}</text>"
            f"</g>"
        )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"
