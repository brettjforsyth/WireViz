# -*- coding: utf-8 -*-
"""Splice / junction planner.

Finds the points where wires branch — a connector pin where several wires meet,
or a dedicated splice connector (``style: simple``) — and rolls them into a
splice BOM. Where the cables declare a current, it also sums the current at each
splice so an under-sized distribution point can be flagged.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from wireviz.wv_electrical import ampacity_for


def _is_shield(vp):
    return isinstance(vp, str) and vp.lower() == "s"


@dataclass
class SpliceWire:
    cable: str
    wire: object
    other: str
    current: Optional[float]
    gauge: Optional[str]
    gauge_unit: Optional[str]


@dataclass
class Splice:
    connector: str
    pin: object
    branches: int
    dedicated: bool  # a style:simple splice connector
    wires: List[SpliceWire] = field(default_factory=list)

    @property
    def total_current(self) -> Optional[float]:
        cur = [w.current for w in self.wires if w.current is not None]
        return round(sum(cur), 3) if cur else None


def _terminations(harness) -> Dict[Tuple[str, object], List[SpliceWire]]:
    term: Dict[Tuple[str, object], List[SpliceWire]] = {}
    for cname, cable in harness.cables.items():
        for c in cable.connections:
            wid = "s" if _is_shield(c.via_port) else c.via_port
            for name, pin, other in (
                (c.from_name, c.from_pin, (c.to_name, c.to_pin)),
                (c.to_name, c.to_pin, (c.from_name, c.from_pin)),
            ):
                if name is None:
                    continue
                term.setdefault((name, pin), []).append(
                    SpliceWire(
                        cable=cname,
                        wire=wid,
                        other=f"{other[0]}:{other[1]}" if other[0] else "open",
                        current=cable.current,
                        gauge=cable.gauge,
                        gauge_unit=cable.gauge_unit,
                    )
                )
    return term


def find_splices(harness, min_branches: int = 3) -> List[Splice]:
    """Splice points: pins with >= min_branches wires, or simple-style connectors."""
    term = _terminations(harness)
    splices = []
    for (name, pin), wires in term.items():
        conn = harness.connectors.get(name)
        dedicated = bool(conn and conn.style == "simple")
        if len(wires) >= min_branches or (dedicated and len(wires) >= 2):
            splices.append(
                Splice(
                    connector=name,
                    pin=pin,
                    branches=len(wires),
                    dedicated=dedicated,
                    wires=sorted(wires, key=lambda w: (w.cable, str(w.wire))),
                )
            )
    return sorted(splices, key=lambda s: (s.connector, str(s.pin)))


def splice_bom(harness, min_branches: int = 3) -> List[dict]:
    """Group splices by branch count for purchasing (e.g. '3-way x2')."""
    counts: Dict[int, List[str]] = {}
    for s in find_splices(harness, min_branches):
        counts.setdefault(s.branches, []).append(f"{s.connector}:{s.pin}")
    return [
        {"type": f"{b}-way splice", "branches": b, "qty": len(locs), "locations": locs}
        for b, locs in sorted(counts.items())
    ]


def current_overloads(harness, min_branches: int = 3) -> List[dict]:
    """Splices whose summed current exceeds the thinnest branch wire's ampacity."""
    out = []
    for s in find_splices(harness, min_branches):
        total = s.total_current
        if total is None:
            continue
        amps = [
            ampacity_for(w.gauge, w.gauge_unit)
            for w in s.wires
            if w.gauge
        ]
        amps = [a for a in amps if a]
        if amps and total > min(amps):
            out.append(
                {
                    "splice": f"{s.connector}:{s.pin}",
                    "total_current": total,
                    "min_branch_ampacity": round(min(amps), 1),
                }
            )
    return out
