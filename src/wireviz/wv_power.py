# -*- coding: utf-8 -*-
"""Power / voltage-drop report.

For every cable that carries a declared current, computes the conductor
resistance, the end-to-end voltage drop (absolute and as a percentage of the
circuit voltage), and the I^2R power dissipated in the wire — the power budget a
designer needs to size a supply and check that loads see enough voltage.
"""

from dataclasses import dataclass
from typing import List, Optional

from wireviz.wv_electrical import resistance_per_m
from wireviz.wv_formboard import to_mm


@dataclass
class PowerRow:
    cable: str
    current: float
    voltage: Optional[float]
    length_m: float
    resistance_ohm: Optional[float]
    vdrop_v: Optional[float]
    vdrop_pct: Optional[float]
    power_loss_w: Optional[float]


def power_report(harness, conductors: int = 2) -> dict:
    """Per-cable power/voltage-drop rows (only cables that declare a current).

    `conductors` is the number of conductors in the current loop counted for
    resistance (2 = supply + return, the default).
    """
    rows: List[PowerRow] = []
    total_loss = 0.0
    have_loss = False
    for name, cable in harness.cables.items():
        if not cable.current:
            continue
        length_m = to_mm(cable.length, cable.length_unit) / 1000.0
        r_per_m = resistance_per_m(cable.gauge, cable.gauge_unit)
        resistance = drop = pct = loss = None
        if r_per_m is not None and length_m:
            resistance = round(r_per_m * length_m * conductors, 6)
            drop = round(cable.current * resistance, 4)
            loss = round(cable.current ** 2 * resistance, 4)
            total_loss += loss
            have_loss = True
            if cable.voltage:
                pct = round(drop / cable.voltage * 100, 2)
        rows.append(
            PowerRow(
                cable=name,
                current=cable.current,
                voltage=cable.voltage,
                length_m=round(length_m, 4),
                resistance_ohm=resistance,
                vdrop_v=drop,
                vdrop_pct=pct,
                power_loss_w=loss,
            )
        )
    return {
        "rows": rows,
        "total_power_loss_w": round(total_loss, 4) if have_loss else None,
    }


def to_text(report: dict) -> str:
    lines = [
        f"{'Cable':<10}{'I(A)':>7}{'V':>6}{'L(m)':>7}{'R(ohm)':>10}"
        f"{'Vdrop':>9}{'%':>7}{'Ploss(W)':>10}"
    ]
    for r in report["rows"]:
        def s(v):
            return "-" if v is None else v
        lines.append(
            f"{r.cable:<10}{r.current:>7}{s(r.voltage):>6}{r.length_m:>7}"
            f"{s(r.resistance_ohm):>10}{s(r.vdrop_v):>9}{s(r.vdrop_pct):>7}"
            f"{s(r.power_loss_w):>10}"
        )
    if report["total_power_loss_w"] is not None:
        lines.append(f"\nTotal I^2R loss: {report['total_power_loss_w']} W")
    return "\n".join(lines) + "\n"
