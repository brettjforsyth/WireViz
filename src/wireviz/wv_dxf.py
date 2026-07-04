# -*- coding: utf-8 -*-
"""DXF export of the formboard geometry.

Writes a minimal AutoCAD R12 ASCII DXF containing the formboard's connectors
(rectangles + mounting-peg circles), bundle runs (polylines), and text labels,
so the layout can be opened in CAD or fed to a cutting/plotting machine. Units
are millimetres and the Y axis is flipped into CAD's y-up convention.
"""

from typing import List, Optional

from wireviz.wv_formboard import FormboardConfig, build_formboard


class _Dxf:
    """Accumulates R12 ASCII DXF entities."""

    def __init__(self, height: float):
        self._h = height
        self._lines: List[str] = []

    def _y(self, y: float) -> float:
        return self._h - y  # flip to CAD y-up

    def _pair(self, code: int, value) -> None:
        self._lines.append(str(code))
        self._lines.append(f"{value}")

    def line(self, x1, y1, x2, y2, layer="0") -> None:
        self._pair(0, "LINE")
        self._pair(8, layer)
        self._pair(10, f"{x1:.3f}")
        self._pair(20, f"{self._y(y1):.3f}")
        self._pair(11, f"{x2:.3f}")
        self._pair(21, f"{self._y(y2):.3f}")

    def polyline(self, points, layer="0") -> None:
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            self.line(x1, y1, x2, y2, layer)

    def circle(self, cx, cy, r, layer="0") -> None:
        self._pair(0, "CIRCLE")
        self._pair(8, layer)
        self._pair(10, f"{cx:.3f}")
        self._pair(20, f"{self._y(cy):.3f}")
        self._pair(40, f"{r:.3f}")

    def rect(self, x, y, w, h, layer="0") -> None:
        self.polyline(
            [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)], layer
        )

    def text(self, x, y, s, height=4.0, layer="TEXT") -> None:
        self._pair(0, "TEXT")
        self._pair(8, layer)
        self._pair(10, f"{x:.3f}")
        self._pair(20, f"{self._y(y):.3f}")
        self._pair(40, f"{height:.3f}")
        self._pair(1, str(s).replace("\n", " "))

    def render(self) -> str:
        head = ["0", "SECTION", "2", "ENTITIES"]
        tail = ["0", "ENDSEC", "0", "EOF"]
        return "\n".join(head + self._lines + tail) + "\n"


def formboard_to_dxf(harness, cfg: Optional[FormboardConfig] = None) -> str:
    """Return a DXF string of the harness formboard."""
    cfg = cfg or FormboardConfig()
    layout = build_formboard(harness, cfg)
    dxf = _Dxf(layout["height"])

    for b in layout["bundles"]:
        dxf.polyline(b["points"], layer="BUNDLES")
        mx, my = b["mid"]
        dxf.text(mx, my - 2, b["label"], height=3.5, layer="TEXT")

    for c in layout["connectors"].values():
        dxf.rect(c["x"], c["y"], cfg.connector_w, c["h"], layer="CONNECTORS")
        dxf.circle(c["x"] + cfg.connector_w / 2, c["cy"], cfg.peg_radius, layer="PEGS")
        dxf.text(c["x"], c["y"] - 2, f'{c["name"]}', height=4.0, layer="TEXT")

    return dxf.render()
