# -*- coding: utf-8 -*-
"""Harness weight and length rollup.

Estimates the mass of each cable (copper conductors + insulation) and the whole
harness, plus total conductor length — the numbers aerospace/automotive
programs track but that WireViz never computed.

Copper: 1 mm^2 of conductor weighs 8.96 g/m (density 8.96 g/cm^3). Insulation:
the annular cross-section between the conductor and the wire OD, at a PVC-like
1.4 g/cm^3 by default.
"""

import math
from dataclasses import dataclass
from typing import List, Optional

from wireviz.wv_bundle import DEFAULT_WALL_MM, wire_outer_diameter
from wireviz.wv_electrical import _normalize_gauge
from wireviz.wv_formboard import to_mm

COPPER_G_PER_MM2_M = 8.96  # g per (mm^2 * metre)
PVC_G_PER_MM2_M = 1.40  # g per (mm^2 * metre)


def copper_mass_per_m(gauge, unit) -> Optional[float]:
    """Grams of copper per metre of a single conductor."""
    area = _normalize_gauge(gauge, unit)
    return None if not area else area * COPPER_G_PER_MM2_M


def insulation_mass_per_m(
    gauge, unit, wall: float = DEFAULT_WALL_MM, density: float = PVC_G_PER_MM2_M
) -> Optional[float]:
    """Grams of insulation per metre (annulus between conductor and wire OD)."""
    area = _normalize_gauge(gauge, unit)
    od = wire_outer_diameter(gauge, unit, wall)
    if area is None or od is None:
        return None
    ins_area = math.pi / 4 * od * od - area
    return max(ins_area, 0.0) * density


def wire_mass_per_m(gauge, unit, wall: float = DEFAULT_WALL_MM) -> Optional[float]:
    cu = copper_mass_per_m(gauge, unit)
    if cu is None:
        return None
    ins = insulation_mass_per_m(gauge, unit, wall) or 0.0
    return cu + ins


@dataclass
class CableWeight:
    cable: str
    length_m: float
    wire_count: int
    conductor_length_m: float  # wirecount * length
    mass_g: Optional[float]


def weight_report(harness, wall: float = DEFAULT_WALL_MM) -> dict:
    """Per-cable and total harness weight + conductor length."""
    cables: List[CableWeight] = []
    total_mass = 0.0
    total_cond_len = 0.0
    have_mass = False
    for name, cable in harness.cables.items():
        length_m = to_mm(cable.length, cable.length_unit) / 1000.0
        n = (cable.wirecount or 0) + (1 if cable.shield else 0)
        cond_len = n * length_m
        per_m = wire_mass_per_m(cable.gauge, cable.gauge_unit, wall)
        mass = round(per_m * cond_len, 2) if per_m is not None else None
        if mass is not None:
            total_mass += mass
            have_mass = True
        total_cond_len += cond_len
        cables.append(
            CableWeight(
                cable=name,
                length_m=round(length_m, 4),
                wire_count=n,
                conductor_length_m=round(cond_len, 4),
                mass_g=mass,
            )
        )
    return {
        "cables": cables,
        "total_mass_g": round(total_mass, 2) if have_mass else None,
        "total_conductor_length_m": round(total_cond_len, 4),
    }
