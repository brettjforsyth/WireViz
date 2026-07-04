# -*- coding: utf-8 -*-
"""Accessory and covering data model.

Connectors and cables can declare accessories — contacts, cavity seals, locks,
boots, backshells, dust covers — and coverings — braided sleeve, spiral wrap,
tubing, corrugated tube, heatshrink, tape. Each accessory's quantity is either
stated directly or derived per pin / per connector / per length, so the tool can
roll them into a complete bill of materials that WireViz's core never captured.

Declare them in YAML on a connector or cable:

    connectors:
      X1:
        pincount: 4
        accessories:
          - {type: contact, mpn: 0460-215-16141}   # per pin -> qty 4
          - {type: seal,    per: pin}
          - {type: backshell, qty: 1, mpn: BS-1}
    cables:
      W1:
        length: 2
        accessories:
          - {type: braided_sleeve, mpn: PT2}        # per length -> qty 2 m
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

# accessory type -> how its quantity is derived by default
DEFAULT_PER = {
    "contact": "pin",
    "terminal": "pin",
    "seal": "pin",
    "cavity_seal": "pin",
    "wire_seal": "pin",
    "lock": "connector",
    "tpa": "connector",
    "cpa": "connector",
    "backshell": "connector",
    "boot": "connector",
    "dust_cover": "connector",
    "cover": "connector",
    "cap": "connector",
    "braided_sleeve": "length",
    "spiral_wrap": "length",
    "tubing": "length",
    "corrugated_tube": "length",
    "convoluted_tube": "length",
    "heatshrink": "length",
    "tape": "length",
}

COVERING_TYPES = {
    "braided_sleeve",
    "spiral_wrap",
    "tubing",
    "corrugated_tube",
    "convoluted_tube",
    "heatshrink",
    "tape",
}


@dataclass
class AccessoryLine:
    host: str  # connector/cable designator
    host_kind: str  # 'connector' | 'cable'
    type: str
    category: str  # 'accessory' | 'covering'
    qty: float
    unit: str
    mpn: Optional[str] = None
    manufacturer: Optional[str] = None


def _metric(host, host_kind, per) -> float:
    per = (per or "").lower()
    if per in ("connector", "cable", "each", "1"):
        return 1
    if per == "pin":
        return len(host.pins) if host_kind == "connector" else (host.wirecount or 0)
    if per == "populated":
        return sum(getattr(host, "visible_pins", {}).values())
    if per == "wire":
        return host.wirecount or 0
    if per == "length":
        return float(getattr(host, "length", 0) or 0)
    return 1


def _expand(name, host_kind, host, spec) -> Optional[AccessoryLine]:
    if not isinstance(spec, dict) or "type" not in spec:
        return None
    t = str(spec["type"])
    default_per = DEFAULT_PER.get(
        t.lower(), "length" if host_kind == "cable" else "connector"
    )
    per = spec.get("per", default_per)
    qty = spec.get("qty")
    if qty is None:
        qty = _metric(host, host_kind, per) * float(spec.get("multiplier", 1))
    is_covering = t.lower() in COVERING_TYPES or per == "length"
    unit = spec.get("unit")
    if unit is None:
        # length unit only for coverings; discrete accessories are 'ea'
        unit = (getattr(host, "length_unit", None) or "m") if is_covering else "ea"
    return AccessoryLine(
        host=name,
        host_kind=host_kind,
        type=t,
        category="covering" if is_covering else "accessory",
        qty=round(float(qty), 4),
        unit=unit,
        mpn=spec.get("mpn"),
        manufacturer=spec.get("manufacturer"),
    )


def derive_accessories(harness) -> List[AccessoryLine]:
    """All accessory lines declared across connectors and cables."""
    lines: List[AccessoryLine] = []
    for kind, container in (("connector", harness.connectors), ("cable", harness.cables)):
        for name, host in container.items():
            for spec in getattr(host, "accessories", None) or []:
                line = _expand(name, kind, host, spec)
                if line:
                    lines.append(line)
    return lines


def accessory_bom(harness) -> List[dict]:
    """Group accessory lines by (type, mpn, manufacturer, unit), summing qty."""
    groups: Dict[tuple, dict] = {}
    for ln in derive_accessories(harness):
        key = (ln.type, ln.mpn, ln.manufacturer, ln.unit)
        g = groups.setdefault(
            key,
            {
                "type": ln.type,
                "category": ln.category,
                "mpn": ln.mpn,
                "manufacturer": ln.manufacturer,
                "unit": ln.unit,
                "qty": 0.0,
                "hosts": [],
            },
        )
        g["qty"] = round(g["qty"] + ln.qty, 4)
        g["hosts"].append(ln.host)
    return sorted(groups.values(), key=lambda g: (g["category"], g["type"], g["mpn"] or ""))


def to_tsv(bom: List[dict]) -> str:
    cols = ["category", "type", "mpn", "manufacturer", "qty", "unit", "hosts"]
    lines = ["\t".join(c.capitalize() for c in cols)]
    for g in bom:
        lines.append(
            "\t".join(
                [
                    g["category"],
                    g["type"],
                    g["mpn"] or "",
                    g["manufacturer"] or "",
                    str(g["qty"]),
                    g["unit"],
                    ", ".join(g["hosts"]),
                ]
            )
        )
    return "\n".join(lines) + "\n"
