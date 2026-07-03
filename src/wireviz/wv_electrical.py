# -*- coding: utf-8 -*-
"""Wire electrical properties: resistance, ampacity, and voltage drop.

This is the engineering layer that the DRC uses for the checks that neither
benchmarked commercial harness tool performs: current-vs-ampacity and
voltage-drop. It is deliberately unit-aware (AWG and mm2) and free of any
rendering or model dependencies so it can be unit-tested in isolation.

Resistance is computed from conductor geometry (annealed copper, 20 C), so it
is exact for any gauge rather than relying on a lookup table:

    d(mm)  = 0.127 * 92**((36 - awg) / 39)           # AWG -> diameter
    A(mm2) = pi/4 * d**2                              # -> cross-section
    R/m    = RHO_COPPER / (A * 1e-6)                  # ohms per metre

Ampacity is inherently install-dependent (bundling, ambient temperature,
insulation rating), so the table below is the widely-published *chassis
wiring* column (single conductor in free air) used as a conservative default.
Callers may pass their own table. Treat results as advisory.
"""

import math
from typing import Dict, Optional

RHO_COPPER = 1.724e-8  # ohm-metre, annealed copper at 20 C

# Chassis-wiring ampacity (amps), single conductor in free air.
# Keyed by AWG as a float (negative values are 1/0=-1 ... 4/0=-4).
AWG_CHASSIS_AMPACITY: Dict[float, float] = {
    32: 0.53,
    30: 0.86,
    28: 1.4,
    26: 2.2,
    24: 3.5,
    22: 7.0,
    20: 11.0,
    18: 16.0,
    16: 22.0,
    14: 32.0,
    12: 41.0,
    10: 55.0,
    8: 73.0,
    6: 101.0,
    4: 135.0,
    2: 181.0,
    1: 211.0,
    0: 245.0,  # 1/0
    -1: 283.0,  # 2/0
    -2: 328.0,  # 3/0
    -3: 380.0,  # 4/0
}


def _parse_awg(value) -> Optional[float]:
    """Turn '4/0', '0000', '1/0', '24', 24 into a numeric AWG (4/0 -> -3)."""
    s = str(value).strip().upper().replace("AWG", "").strip()
    if not s:
        return None
    if s.endswith("/0"):  # e.g. '2/0'
        try:
            return -(int(s[:-2]) - 1)
        except ValueError:
            return None
    if s == "0" or set(s) == {"0"}:  # '0','00','000','0000'
        return -(len(s) - 1)
    try:
        return float(s)
    except ValueError:
        return None


def awg_area_mm2(awg: float) -> float:
    """Cross-sectional area (mm2) of an AWG conductor."""
    d_mm = 0.127 * 92 ** ((36 - awg) / 39)
    return math.pi / 4 * d_mm ** 2


def area_to_awg(area_mm2: float) -> float:
    """Inverse of awg_area_mm2: a (possibly fractional) AWG for a given area."""
    d_mm = 2 * math.sqrt(area_mm2 / math.pi)
    return 36 - 39 * math.log(d_mm / 0.127, 92)


def _normalize_gauge(gauge, unit) -> Optional[float]:
    """Return an area in mm2 for a (gauge, unit) pair, or None if unusable."""
    if gauge in (None, "", 0):
        return None
    u = (unit or "").strip().lower()
    try:
        num = float(str(gauge).split()[0])
    except (ValueError, IndexError):
        # maybe an AWG like '4/0'
        awg = _parse_awg(gauge)
        return awg_area_mm2(awg) if awg is not None else None
    if "awg" in u or "awg" in str(gauge).lower():
        awg = _parse_awg(gauge)
        return awg_area_mm2(awg) if awg is not None else None
    # default: metric mm2
    return num


def resistance_per_m(gauge, unit) -> Optional[float]:
    """Ohms per metre for a copper conductor of the given gauge, or None."""
    area = _normalize_gauge(gauge, unit)
    if not area:
        return None
    return RHO_COPPER / (area * 1e-6)


def ampacity_for(
    gauge, unit, table: Optional[Dict[float, float]] = None
) -> Optional[float]:
    """Ampacity (amps) for a gauge, interpolated over the ampacity table.

    AWG gauges are looked up / interpolated directly; metric gauges are mapped
    to an equivalent AWG by cross-sectional area first.
    """
    table = table or AWG_CHASSIS_AMPACITY
    area = _normalize_gauge(gauge, unit)
    if not area:
        return None
    awg = area_to_awg(area)
    points = sorted(table.items())  # ascending awg (thicker -> smaller/negative)
    # ampacity decreases as awg number increases (thinner wire)
    if awg <= points[0][0]:
        return points[0][1]
    if awg >= points[-1][0]:
        return points[-1][1]
    for (a0, i0), (a1, i1) in zip(points, points[1:]):
        if a0 <= awg <= a1:
            # linear interpolation in awg-space
            frac = (awg - a0) / (a1 - a0) if a1 != a0 else 0
            return round(i0 + frac * (i1 - i0), 3)
    return None


def voltage_drop(
    current: float, gauge, unit, length_m: float, conductors: int = 1
) -> Optional[float]:
    """Voltage drop (volts) for `current` A over `length_m` m of wire.

    conductors=1 is a single conductor (default); use 2 to include the return
    path of a simple two-wire circuit.
    """
    r = resistance_per_m(gauge, unit)
    if r is None:
        return None
    return current * r * length_m * conductors


def ampacity_margin(current: float, gauge, unit) -> Optional[float]:
    """Fraction of ampacity used (1.0 == exactly at the limit), or None."""
    amp = ampacity_for(gauge, unit)
    if not amp:
        return None
    return current / amp
