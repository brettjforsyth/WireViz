# -*- coding: utf-8 -*-
"""Bundle diameter and conduit/sleeve fill calculations.

Given the wires in a cable, estimate the outer diameter of each wire (conductor
+ insulation), the diameter of the finished bundle, and how full a conduit or
braided sleeve would be — so a designer can size the covering and check fill
without a spreadsheet. Neither benchmarked commercial tool does this.

Bundle diameter uses the cross-sectional-area packing estimate
``d_bundle = sqrt(sum(d_i^2) / packing)`` (a single wire returns its own OD).
"""

import math
from dataclasses import dataclass
from typing import List, Optional

from wireviz.wv_electrical import _normalize_gauge

# common expandable-sleeve / conduit inner diameters (mm)
STANDARD_SLEEVE_MM = [3, 4, 5, 6, 8, 10, 13, 16, 19, 25, 32, 40, 50]

# default insulation wall thickness (mm) for typical hook-up wire
DEFAULT_WALL_MM = 0.4

# NEC-style fill guidance: 1 wire 53%, 2 wires 31%, 3+ wires 40%
def fill_limit(wire_count: int) -> float:
    if wire_count <= 1:
        return 0.53
    if wire_count == 2:
        return 0.31
    return 0.40


def conductor_diameter(gauge, unit) -> Optional[float]:
    """Bare conductor diameter (mm) from gauge, or None if unusable."""
    area = _normalize_gauge(gauge, unit)
    if not area:
        return None
    return 2 * math.sqrt(area / math.pi)


def wire_outer_diameter(gauge, unit, wall: float = DEFAULT_WALL_MM) -> Optional[float]:
    """Insulated wire OD (mm) = conductor diameter + 2 * insulation wall."""
    cd = conductor_diameter(gauge, unit)
    return None if cd is None else cd + 2 * wall


def bundle_diameter(diameters: List[float], packing: float = 0.75) -> float:
    """Estimated finished-bundle OD (mm) from a list of wire ODs."""
    ds = [d for d in diameters if d]
    if not ds:
        return 0.0
    if len(ds) == 1:
        return ds[0]
    return math.sqrt(sum(d * d for d in ds) / packing)


def fill_ratio(diameters: List[float], sleeve_id: float) -> Optional[float]:
    """Fraction of a sleeve's cross-section taken up by the wires."""
    if not sleeve_id:
        return None
    wire_area = sum(math.pi / 4 * d * d for d in diameters if d)
    sleeve_area = math.pi / 4 * sleeve_id * sleeve_id
    return wire_area / sleeve_area if sleeve_area else None


def recommend_sleeve(
    diameters: List[float], sizes=None, limit: Optional[float] = None
) -> Optional[float]:
    """Smallest standard sleeve whose fill is within the limit."""
    sizes = sizes or STANDARD_SLEEVE_MM
    n = len([d for d in diameters if d])
    limit = fill_limit(n) if limit is None else limit
    for s in sorted(sizes):
        fr = fill_ratio(diameters, s)
        if fr is not None and fr <= limit:
            return s
    return None


@dataclass
class BundleInfo:
    cable: str
    wire_count: int
    wire_od: Optional[float]
    bundle_od: float
    recommended_sleeve: Optional[float]


def _cable_wire_count(cable) -> int:
    return (cable.wirecount or 0) + (1 if cable.shield else 0)


def bundle_report(harness, wall: float = DEFAULT_WALL_MM) -> List[BundleInfo]:
    """Per-cable bundle diameter and recommended sleeve size.

    The wire count always reflects the cable's wires (+ shield); only the
    diameters/sleeve are None when the gauge is missing, so a gauge-less cable
    still reports the right count.
    """
    out = []
    for name, cable in harness.cables.items():
        n = _cable_wire_count(cable)
        od = wire_outer_diameter(cable.gauge, cable.gauge_unit, wall)
        ods = [od] * n if od else []
        out.append(
            BundleInfo(
                cable=name,
                wire_count=n,
                wire_od=round(od, 2) if od else None,
                bundle_od=round(bundle_diameter(ods), 2) if ods else 0.0,
                recommended_sleeve=recommend_sleeve(ods) if ods else None,
            )
        )
    return out
