# -*- coding: utf-8 -*-
"""Wire cut-sheet / cut-list generation for WireViz harnesses.

A cut sheet is the shop-floor document that tells an assembler exactly which
wires to cut, to what length, in which colour/gauge, and where each end
terminates. WireViz's built-in `length` field is a single per-cable number;
this module turns the parsed :class:`Harness` into a proper per-wire cut list
with manufacturing allowances, modelled on the cut-length math used by
dedicated harness tools:

    cut length = cable length
               + (insertion allowance x number of terminated ends)
               + service slack
               , scaled by an optional twist factor,
               then floored to a minimum and rounded to a stock increment.

Everything is computed in the cable's own length unit; allowances are given in
that same unit. Defaults are all zero / identity, so with no options the cut
length equals the cable length (no surprises vs. the current behaviour).
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

COLUMNS = [
    "wire",
    "from",
    "to",
    "color",
    "gauge",
    "length",
    "unit",
    "label",
]


@dataclass
class CutSheetOptions:
    """Manufacturing allowances applied to every wire's cut length."""

    insertion_allowance: float = 0.0  # added per terminated end (strip+crimp+seat)
    slack: float = 0.0  # flat service-loop slack added to every wire
    twist_factor: float = 0.0  # extra fraction for twisted runs, e.g. 0.20 = +20%
    min_length: float = 0.0  # never cut shorter than this
    round_increment: float = 0.0  # round the result to this multiple (0 = no rounding)
    round_mode: str = "up"  # 'up' | 'down' | 'nearest'
    strip_length: Optional[float] = None  # informational strip length per end


def _round_to(value: float, increment: float, mode: str) -> float:
    if not increment:
        return value
    q = value / increment
    if mode == "down":
        import math

        n = math.floor(q)
    elif mode == "nearest":
        n = round(q)
    else:  # 'up' (default) — never come up short
        import math

        n = math.ceil(q)
    return n * increment


def _clean(value: float) -> float:
    """Drop floating-point fuzz and render whole numbers as ints downstream."""
    r = round(value, 4)
    return int(r) if float(r).is_integer() else r


def _pin_display(connector, pin) -> str:
    """Return 'pin' or 'pin (label)' for a connector endpoint."""
    if connector is None or pin is None:
        return "—"
    label = None
    labels = getattr(connector, "pinlabels", None) or []
    pins = getattr(connector, "pins", None) or []
    idx = None
    if pin in pins:
        idx = pins.index(pin)
    elif isinstance(pin, int) and 1 <= pin <= len(pins):
        idx = pin - 1
    if idx is not None and idx < len(labels) and labels[idx]:
        label = labels[idx]
    return f"{pin} ({label})" if label else f"{pin}"


def _endpoint(harness, name, pin) -> str:
    if name is None:
        return "—"
    connector = harness.connectors.get(name)
    return f"{name}:{_pin_display(connector, pin)}"


def _is_shield(via_port) -> bool:
    return isinstance(via_port, str) and via_port.lower() == "s"


def _wire_color(cable, via_port) -> str:
    if _is_shield(via_port):
        return str(cable.shield) if not isinstance(cable.shield, bool) else "shield"
    if isinstance(via_port, int) and 1 <= via_port <= len(cable.colors):
        return cable.colors[via_port - 1] or ""
    return ""


def _wire_label(cable, via_port) -> str:
    wl = cable.wirelabels or []
    if isinstance(via_port, int) and 1 <= via_port <= len(wl):
        return str(wl[via_port - 1])
    return ""


def compute_length(cable, terminated_ends: int, options: CutSheetOptions) -> float:
    """Apply the allowance/twist/rounding chain to a cable's base length."""
    length = float(cable.length or 0)
    length += options.insertion_allowance * terminated_ends
    length += options.slack
    if options.twist_factor:
        length *= 1.0 + options.twist_factor
    if options.min_length:
        length = max(length, options.min_length)
    length = _round_to(length, options.round_increment, options.round_mode)
    return length


def build_cut_list(
    harness, options: Optional[CutSheetOptions] = None
) -> List[Dict[str, object]]:
    """Return one row per physical wire (and shield) across all cables.

    Rows are ordered by cable, then wire number, with the shield last.
    """
    options = options or CutSheetOptions()
    rows: List[Dict[str, object]] = []
    for cable_name, cable in harness.cables.items():
        for conn in cable.connections:
            via = conn.via_port
            terminated = sum(1 for n in (conn.from_name, conn.to_name) if n is not None)
            wire_id = "s" if _is_shield(via) else via
            length = compute_length(cable, terminated, options)
            rows.append(
                {
                    "wire": f"{cable_name}:{wire_id}",
                    "from": _endpoint(harness, conn.from_name, conn.from_pin),
                    "to": _endpoint(harness, conn.to_name, conn.to_pin),
                    "color": _wire_color(cable, via),
                    "gauge": (
                        f"{cable.gauge} {cable.gauge_unit}".strip()
                        if cable.gauge
                        else ""
                    ),
                    "length": _clean(length),
                    "unit": cable.length_unit or "",
                    "label": _wire_label(cable, via),
                    "_sort": (cable_name, 1 if _is_shield(via) else 0, via if isinstance(via, int) else 0),
                }
            )
    rows.sort(key=lambda r: r.pop("_sort"))
    return rows


def total_length_by_gauge(rows: List[Dict[str, object]]) -> Dict[str, float]:
    """Sum cut length per (gauge, unit) — useful for bulk wire purchasing."""
    totals: Dict[str, float] = {}
    for r in rows:
        key = f"{r['gauge']}".strip() or "(unspecified)"
        key = f"{key} [{r['unit']}]" if r["unit"] else key
        totals[key] = totals.get(key, 0) + float(r["length"] or 0)
    return {k: _clean(v) for k, v in totals.items()}


# --- formatters ------------------------------------------------------------

_HEADERS = {
    "wire": "Wire",
    "from": "From",
    "to": "To",
    "color": "Color",
    "gauge": "Gauge",
    "length": "Length",
    "unit": "Unit",
    "label": "Label",
}


def to_tsv(rows: List[Dict[str, object]]) -> str:
    lines = ["\t".join(_HEADERS[c] for c in COLUMNS)]
    for r in rows:
        lines.append("\t".join(str(r.get(c, "")) for c in COLUMNS))
    return "\n".join(lines) + "\n"


def to_csv(rows: List[Dict[str, object]]) -> str:
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_HEADERS[c] for c in COLUMNS)
    for r in rows:
        writer.writerow(r.get(c, "") for c in COLUMNS)
    return buf.getvalue()


def to_html(rows: List[Dict[str, object]], title: str = "Wire Cut Sheet") -> str:
    from html import escape

    head = "".join(f"<th>{escape(_HEADERS[c])}</th>" for c in COLUMNS)
    body = []
    for r in rows:
        cells = "".join(f"<td>{escape(str(r.get(c, '')))}</td>" for c in COLUMNS)
        body.append(f"<tr>{cells}</tr>")
    return (
        f"<table class='cutsheet'>\n<caption>{escape(title)}</caption>\n"
        f"<thead><tr>{head}</tr></thead>\n<tbody>\n"
        + "\n".join(body)
        + "\n</tbody>\n</table>\n"
    )
