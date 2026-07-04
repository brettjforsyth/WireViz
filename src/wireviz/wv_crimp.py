# -*- coding: utf-8 -*-
"""Crimp tooling & die selection.

Maps a connector's contact series and the wire gauge landing on each pin to the
crimp tool, die/locator, and target crimp height — the setup a shop needs before
terminating. Only generic example specs ship (no proprietary manufacturer tool
data); add your own with :func:`register_crimp`.

The contact series comes from the connector's ``connector_type`` (via the
connector library's ``series``), and the wire gauge from the cable on each pin.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from wireviz.wv_connectors import get_connector
from wireviz.wv_electrical import _normalize_gauge, area_to_awg

# series -> list of gauge-range crimp specs (AWG range inclusive)
# height in mm is illustrative; replace with your qualified process values.
CRIMP_SPECS: Dict[str, List[dict]] = {
    "DT": [
        {"awg_min": 16, "awg_max": 20, "tool": "HDT-48-00", "die": "size-16", "height": 1.5},
        {"awg_min": 12, "awg_max": 14, "tool": "HDT-48-00", "die": "size-12", "height": 2.0},
    ],
    "DTM": [
        {"awg_min": 20, "awg_max": 24, "tool": "HDT-48-00", "die": "size-20", "height": 1.1},
    ],
    "Micro-Fit 3.0": [
        {"awg_min": 20, "awg_max": 24, "tool": "638119200", "die": "std", "height": 1.0},
        {"awg_min": 26, "awg_max": 30, "tool": "638119200", "die": "std", "height": 0.8},
    ],
    "Mini-Fit Jr.": [
        {"awg_min": 18, "awg_max": 24, "tool": "638190000", "die": "std", "height": 1.6},
    ],
    "PH": [
        {"awg_min": 24, "awg_max": 28, "tool": "YC-160R", "die": "PH", "height": 0.7},
    ],
}


def register_crimp(series: str, specs: List[dict]) -> None:
    CRIMP_SPECS[series] = specs


def _to_awg(gauge, unit) -> Optional[int]:
    area = _normalize_gauge(gauge, unit)
    if not area:
        return None
    return round(area_to_awg(area))


def crimp_for(series: str, awg: Optional[int]) -> Optional[dict]:
    """The crimp spec whose AWG range contains `awg`, or None."""
    if series is None or awg is None:
        return None
    for spec in CRIMP_SPECS.get(series, []):
        if spec["awg_min"] <= awg <= spec["awg_max"]:
            return spec
    return None


def _series_of(harness, name) -> Optional[str]:
    conn = harness.connectors.get(name)
    ct = getattr(conn, "connector_type", None) if conn else None
    entry = get_connector(ct) if ct else None
    return entry.get("series") if entry else None


def _pin_gauges(harness):
    """(connector, pin) -> (gauge, gauge_unit) from the cable on that pin."""
    out = {}
    for cable in harness.cables.values():
        for c in cable.connections:
            for name, pin in ((c.from_name, c.from_pin), (c.to_name, c.to_pin)):
                if name is not None and pin is not None:
                    out[(name, pin)] = (cable.gauge, cable.gauge_unit)
    return out


@dataclass
class CrimpRow:
    connector: str
    pin: object
    series: Optional[str]
    awg: Optional[int]
    tool: Optional[str]
    die: Optional[str]
    height: Optional[float]


def crimp_report(harness) -> List[CrimpRow]:
    """A crimp row per terminated pin (only where series + gauge resolve)."""
    gauges = _pin_gauges(harness)
    rows = []
    for name, conn in harness.connectors.items():
        series = _series_of(harness, name)
        for pin in conn.pins:
            g = gauges.get((name, pin))
            if not g:
                continue
            awg = _to_awg(*g)
            spec = crimp_for(series, awg)
            rows.append(
                CrimpRow(
                    connector=name,
                    pin=pin,
                    series=series,
                    awg=awg,
                    tool=spec["tool"] if spec else None,
                    die=spec["die"] if spec else None,
                    height=spec["height"] if spec else None,
                )
            )
    return rows


def crimp_setup_summary(harness) -> List[dict]:
    """Unique (series, tool, die, height) setups with the pins that use each."""
    groups: Dict[tuple, dict] = {}
    for r in crimp_report(harness):
        if not r.tool:
            continue
        key = (r.series, r.tool, r.die, r.height)
        g = groups.setdefault(
            key,
            {"series": r.series, "tool": r.tool, "die": r.die, "height": r.height, "pins": []},
        )
        g["pins"].append(f"{r.connector}:{r.pin}")
    return sorted(groups.values(), key=lambda g: (g["series"] or "", g["tool"]))
