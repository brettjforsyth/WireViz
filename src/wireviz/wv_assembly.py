# -*- coding: utf-8 -*-
"""Assembly traveler (build instructions) generator.

Turns a harness into an ordered, shop-floor build sequence: cut and strip the
wires, populate each connector's cavities, apply coverings, and mate the
connectors. Each step is concrete (which wire in which cavity, which sleeve
size), so a builder can follow it top to bottom.
"""

from dataclasses import dataclass
from typing import List, Optional

from wireviz.DataClasses import MateComponent, MatePin
from wireviz.wv_bundle import bundle_report


@dataclass
class Step:
    number: int
    kind: str  # 'cut' | 'populate' | 'cover' | 'mate'
    title: str
    detail: str


def _is_shield(vp):
    return isinstance(vp, str) and vp.lower() == "s"


def _connector_cavities(harness):
    """connector name -> list of (pin, 'cable:wire', 'other:pin') sorted by pin."""
    cav = {name: [] for name in harness.connectors}
    for cname, cable in harness.cables.items():
        for c in cable.connections:
            wid = "s" if _is_shield(c.via_port) else c.via_port
            wire = f"{cname}:{wid}"
            if c.from_name in cav:
                other = f"{c.to_name}:{c.to_pin}" if c.to_name else "open"
                cav[c.from_name].append((c.from_pin, wire, other))
            if c.to_name in cav:
                other = f"{c.from_name}:{c.from_pin}" if c.from_name else "open"
                cav[c.to_name].append((c.to_pin, wire, other))
    return cav


def build_traveler(harness) -> List[Step]:
    steps: List[Step] = []

    def add(kind, title, detail=""):
        steps.append(Step(len(steps) + 1, kind, title, detail))

    # 1) cut & strip
    for name, cable in harness.cables.items():
        gauge = f"{cable.gauge} {cable.gauge_unit}".strip() if cable.gauge else "?"
        length = f"{cable.length} {cable.length_unit or ''}".strip()
        n = (cable.wirecount or 0) + (1 if cable.shield else 0)
        add(
            "cut",
            f"Cut {name}: {n} × {gauge} @ {length}",
            "Cut to length per the cut sheet; strip and crimp both ends.",
        )

    # 2) populate connectors
    def _pin_key(pin):
        # numeric pins sort numerically (cavity 2 before cavity 10)
        return (0, pin, "") if isinstance(pin, int) else (1, 0, str(pin))

    cav = _connector_cavities(harness)
    for name, conn in harness.connectors.items():
        rows = sorted(cav.get(name, []), key=lambda t: _pin_key(t[0]))
        if not rows:
            continue
        detail = "; ".join(f"cavity {pin} ← {wire} (to {other})" for pin, wire, other in rows)
        ctype = f" ({conn.type})" if getattr(conn, "type", None) else ""
        add("populate", f"Populate {name}{ctype}", detail)

    # 3) coverings
    for b in bundle_report(harness):
        if b.recommended_sleeve and b.wire_count > 1:
            add(
                "cover",
                f"Sleeve {b.cable}",
                f"Apply {b.recommended_sleeve} mm braided sleeve over the "
                f"~{b.bundle_od} mm bundle ({b.wire_count} wires).",
            )

    # 4) mates
    for mate in harness.mates:
        if isinstance(mate, MateComponent):
            add("mate", f"Mate {mate.from_name} ↔ {mate.to_name}", "Mate the connector housings.")
        elif isinstance(mate, MatePin):
            add(
                "mate",
                f"Mate {mate.from_name}:{mate.from_pin} ↔ {mate.to_name}:{mate.to_pin}",
                "",
            )

    return steps


def to_text(steps: List[Step], title: str = "Assembly Traveler") -> str:
    lines = [title, "=" * len(title), ""]
    for s in steps:
        lines.append(f"{s.number:>3}. [{s.kind}] {s.title}")
        if s.detail:
            lines.append(f"      {s.detail}")
    return "\n".join(lines) + "\n"
