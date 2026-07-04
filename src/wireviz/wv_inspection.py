# -*- coding: utf-8 -*-
"""Inspection checklist and traceability code.

Generates a build/QA inspection checklist derived from the harness (connectors
to seat, wires/crimps to verify, continuity, marking, coverings — referencing
the IPC/WHMA-A-620 workmanship standard) and a deterministic traceability code:
a short hash of the harness's canonical definition, so a built unit can be tied
back to the exact spec revision it was built from.
"""

import hashlib
from dataclasses import dataclass
from typing import List


@dataclass
class CheckItem:
    category: str
    item: str
    reference: str = "IPC/WHMA-A-620"


def _is_shield(vp):
    return isinstance(vp, str) and vp.lower() == "s"


def inspection_checklist(harness) -> List[CheckItem]:
    """A checklist tailored to this harness's connectors, wires, and coverings."""
    items: List[CheckItem] = []

    for name, conn in harness.connectors.items():
        items.append(CheckItem("Connector", f"{name}: contacts fully seated / locked ({conn.pincount} pins)"))
        if getattr(conn, "gender", None):
            items.append(CheckItem("Connector", f"{name}: correct gender/keying ({conn.gender})"))
        for ac in getattr(conn, "accessories", None) or []:
            if isinstance(ac, dict) and ac.get("type"):
                items.append(CheckItem("Accessory", f"{name}: {ac['type']} installed"))

    for name, cable in harness.cables.items():
        gauge = f"{cable.gauge} {cable.gauge_unit}".strip() if cable.gauge else "?"
        items.append(CheckItem("Wire", f"{name}: {cable.wirecount} x {gauge}, correct colours"))
        items.append(CheckItem("Crimp", f"{name}: crimp height / pull-test per spec"))
        if cable.length:
            items.append(CheckItem("Wire", f"{name}: cut length {cable.length} {cable.length_unit or ''}".rstrip()))
        for ac in getattr(cable, "accessories", None) or []:
            if isinstance(ac, dict) and ac.get("type"):
                items.append(CheckItem("Covering", f"{name}: {ac['type']} applied"))

    items.append(CheckItem("Electrical", "Continuity: all nets connected per test program"))
    items.append(CheckItem("Electrical", "Isolation: no shorts between nets"))
    items.append(CheckItem("Marking", "Wire markers / idents present and legible"))
    items.append(CheckItem("General", "Workmanship, dress, and strain relief acceptable"))
    return items


def _canonical(harness) -> str:
    """A deterministic textual fingerprint of the harness definition."""
    parts = []
    for name in sorted(harness.connectors):
        c = harness.connectors[name]
        parts.append(f"C|{name}|{c.pincount}|{c.mpn}|{list(c.pins)}|{list(c.pinlabels)}")
    for name in sorted(harness.cables):
        w = harness.cables[name]
        parts.append(f"W|{name}|{w.wirecount}|{w.gauge}|{w.gauge_unit}|{w.length}|{w.mpn}|{list(w.colors)}")
    conns = []
    for cname in sorted(harness.cables):
        for c in harness.cables[cname].connections:
            conns.append(f"{cname}:{c.via_port}:{c.from_name}:{c.from_pin}>{c.to_name}:{c.to_pin}")
    parts.append("N|" + "|".join(sorted(conns)))
    return "\n".join(parts)


def traceability_code(harness, length: int = 10) -> str:
    """A short deterministic hash of the harness definition (upper-case hex)."""
    digest = hashlib.sha256(_canonical(harness).encode("utf-8")).hexdigest()
    return digest[:length].upper()


def to_text(harness, title: str = "Inspection Checklist") -> str:
    code = traceability_code(harness)
    lines = [title, "=" * len(title), f"Traceability: {code}", ""]
    last = None
    for it in inspection_checklist(harness):
        if it.category != last:
            lines.append(f"\n[{it.category}]")
            last = it.category
        lines.append(f"  [ ] {it.item}   ({it.reference})")
    return "\n".join(lines) + "\n"


def to_csv(harness) -> str:
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["category", "item", "reference", "result", "traceability"])
    code = traceability_code(harness)
    for it in inspection_checklist(harness):
        w.writerow([it.category, it.item, it.reference, "", code])
    return buf.getvalue()
