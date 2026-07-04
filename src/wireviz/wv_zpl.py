# -*- coding: utf-8 -*-
"""ZPL (Zebra) label export for wire markers.

Emits each wire marker as a ZPL II label so it prints directly on a Zebra (or
compatible) label printer, without going through label-design software. Reuses
the marker builder so the printed labels match the drawing and cut sheet.
"""

from typing import List, Optional

from wireviz.wv_markers import Marker, build_markers


def _zpl_safe(text: str) -> str:
    """Neutralise ZPL control characters (^ and ~) in field data."""
    return str(text).replace("^", " ").replace("~", " ")


def marker_to_zpl(
    text: str, font_h: int = 28, font_w: int = 28, x: int = 20, y: int = 20
) -> str:
    """A single ^XA…^XZ label for one marker string."""
    return (
        "^XA"  # start label
        "^CI28"  # UTF-8
        f"^FO{x},{y}"  # field origin (dots)
        f"^A0N,{font_h},{font_w}"  # scalable font
        f"^FD{_zpl_safe(text)}^FS"  # field data
        "^XZ"  # end label
    )


def markers_to_zpl(markers: List[Marker], **kwargs) -> str:
    return "\n".join(marker_to_zpl(m.text, **kwargs) for m in markers)


def harness_to_zpl(harness, template: Optional[str] = None, **kwargs) -> str:
    """Convenience: build the harness's wire markers and render them as ZPL."""
    return markers_to_zpl(build_markers(harness, template), **kwargs)
