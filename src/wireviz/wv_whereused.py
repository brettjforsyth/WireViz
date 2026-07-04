# -*- coding: utf-8 -*-
"""Where-used / part cross-reference.

Reverse-lookup: for any manufacturer part number, find every place it is used —
connectors, cables, and their additional components — so an engineer handling an
obsolescence or an ECN can see the full impact of a part change at a glance.
"""

from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class Usage:
    mpn: str
    manufacturer: Optional[str]
    kind: str  # 'connector' | 'cable' | 'accessory'
    designator: str  # where it's used
    qty: float


def _as_list(v):
    return v if isinstance(v, list) else [v]


def part_index(harness) -> "OrderedDict[str, List[Usage]]":
    """Map each MPN to the list of usages across the harness (first-seen order)."""
    idx: "OrderedDict[str, List[Usage]]" = OrderedDict()

    def add(mpn, manufacturer, kind, designator, qty):
        if mpn in (None, "", "N/A"):
            return
        idx.setdefault(str(mpn), []).append(
            Usage(str(mpn), manufacturer, kind, designator, qty)
        )

    for name, conn in harness.connectors.items():
        if not conn.ignore_in_bom:
            add(conn.mpn, conn.manufacturer, "connector", name, 1)
        for ac in getattr(conn, "additional_components", None) or []:
            add(ac.mpn, ac.manufacturer, "accessory", name, ac.qty)

    for name, cable in harness.cables.items():
        if not cable.ignore_in_bom:
            # bundles may carry a per-wire list of mpns
            for m, mfr in zip(_as_list(cable.mpn), _as_list(cable.manufacturer)):
                add(m, mfr, "cable", name, 1)
        for ac in getattr(cable, "additional_components", None) or []:
            add(ac.mpn, ac.manufacturer, "accessory", name, ac.qty)

    return idx


def where_used(harness, mpn: str) -> List[Usage]:
    """Every usage of a specific MPN."""
    return part_index(harness).get(str(mpn), [])


def cross_reference(harness) -> List[dict]:
    """One row per MPN: manufacturer, total qty, and the designators using it."""
    out = []
    for mpn, usages in part_index(harness).items():
        out.append(
            {
                "mpn": mpn,
                "manufacturer": next((u.manufacturer for u in usages if u.manufacturer), None),
                "total_qty": round(sum(u.qty for u in usages), 4),
                "used_by": sorted({u.designator for u in usages}),
                "count": len(usages),
            }
        )
    return sorted(out, key=lambda r: r["mpn"])


def to_text(rows: List[dict]) -> str:
    lines = [f"{'MPN':<24}{'Mfr':<16}{'Qty':>6}  Used by"]
    for r in rows:
        lines.append(
            f"{r['mpn'][:24]:<24}{(r['manufacturer'] or '')[:16]:<16}"
            f"{r['total_qty']:>6}  {', '.join(r['used_by'])}"
        )
    return "\n".join(lines) + "\n"
