# -*- coding: utf-8 -*-
"""MIL-STD-681F wire identification colour bands.

Wires are marked with a sequence of coloured bands encoding a number, using the
same digit->colour code as resistors (0 black … 9 white). A wire numbered 245
is banded red-yellow-green (2-4-5). A shop reads the bands to find a wire on the
harness, so the cut sheet carries the band sequence for every wire.

This module maps a numeric identifier to its bands and renders them as text
(``RD-YE-GN``), inline HTML swatches, or SVG.
"""

from html import escape
from typing import List

# digit -> (abbreviation, full name, hex) per MIL-STD-681F / IEC 60062
MIL_STD_681F = {
    "0": ("BK", "black", "#000000"),
    "1": ("BN", "brown", "#8b4513"),
    "2": ("RD", "red", "#ff0000"),
    "3": ("OG", "orange", "#ff8c00"),
    "4": ("YE", "yellow", "#ffd700"),
    "5": ("GN", "green", "#00a651"),
    "6": ("BU", "blue", "#0000ff"),
    "7": ("VT", "violet", "#8b00ff"),
    "8": ("GY", "gray", "#808080"),
    "9": ("WH", "white", "#ffffff"),
}


def to_bands(code) -> List[dict]:
    """Return the colour bands for a numeric `code`, or [] if it isn't numeric.

    Each band is ``{"digit", "abbr", "name", "hex"}``. Non-numeric idents (e.g.
    a text wire label) have no band representation and yield an empty list.
    """
    s = str(code).strip()
    if not s.isdigit():
        return []
    bands = []
    for ch in s:
        abbr, name, hexcode = MIL_STD_681F[ch]
        bands.append({"digit": ch, "abbr": abbr, "name": name, "hex": hexcode})
    return bands


def ident_string(code) -> str:
    """Compact text form of the band sequence, e.g. 'RD-YE-GN' for 245."""
    return "-".join(b["abbr"] for b in to_bands(code))


def bands_html(code, height: int = 14, width: int = 7) -> str:
    """Inline HTML swatches for the bands (a visual preview in the cut sheet)."""
    bands = to_bands(code)
    if not bands:
        return ""
    cells = []
    for b in bands:
        border = "#999" if b["hex"].lower() in ("#ffffff", "#fff") else b["hex"]
        cells.append(
            f'<span title="{escape(b["name"])}" style="display:inline-block;'
            f'width:{width}px;height:{height}px;background:{b["hex"]};'
            f'border:1px solid {border};"></span>'
        )
    return (
        f'<span class="ident-bands" style="white-space:nowrap;">'
        + "".join(cells)
        + "</span>"
    )


def bands_svg(code, x: float, y: float, height: float = 12, width: float = 5) -> str:
    """SVG rectangles for the bands, laid out left-to-right starting at (x, y)."""
    parts = []
    for i, b in enumerate(to_bands(code)):
        bx = x + i * width
        parts.append(
            f'<rect x="{bx:.1f}" y="{y:.1f}" width="{width:.1f}" '
            f'height="{height:.1f}" fill="{b["hex"]}" stroke="#333" '
            f'stroke-width="0.3"/>'
        )
    return "".join(parts)
