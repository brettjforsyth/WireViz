# -*- coding: utf-8 -*-
"""Cost / quote rollup for a harness.

Turns a harness plus a price book into a costed quote: wire by length,
connectors/terminals as materials, labour from the crimp and connector counts,
and a markup. Prices are supplied by the caller (a dict, or from the distributor
sourcing module), so this stays offline and testable.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from wireviz.wv_formboard import to_mm


@dataclass
class QuoteConfig:
    labor_per_crimp: float = 0.20  # cost of one crimped termination
    labor_per_connector: float = 1.00  # assembly time per connector housing
    markup: float = 0.30  # fraction added on top of cost
    currency: str = "$"


@dataclass
class LineItem:
    kind: str  # 'wire' | 'connector' | 'labor'
    ref: str
    qty: float
    unit: str
    unit_price: float
    total: float


def _price(prices: Dict, *keys) -> Optional[float]:
    for k in keys:
        if k is not None and k in prices:
            return prices[k]
    return None


def crimp_count(harness) -> int:
    """Number of crimped terminations (each wire end landing on a connector)."""
    n = 0
    for cable in harness.cables.values():
        for c in cable.connections:
            n += (c.from_name is not None) + (c.to_name is not None)
    return n


def quote(
    harness,
    prices: Optional[Dict[str, float]] = None,
    config: Optional[QuoteConfig] = None,
) -> dict:
    """Return a costed quote.

    `prices` maps a component key to a price: connector/cable ``mpn`` or
    designator -> unit price, and a cable designator or its mpn -> price *per
    metre* for wire. Missing prices are treated as 0 and counted as unpriced.
    """
    prices = prices or {}
    cfg = config or QuoteConfig()
    items: List[LineItem] = []
    unpriced: List[str] = []

    # wire by length
    for name, cable in harness.cables.items():
        if cable.ignore_in_bom:
            continue
        length_m = to_mm(cable.length, cable.length_unit) / 1000.0
        per_m = _price(prices, name, cable.mpn if isinstance(cable.mpn, str) else None)
        if per_m is None:
            unpriced.append(f"wire {name}")
            per_m = 0.0
        qty = round(length_m * (cable.wirecount or 1), 4)
        items.append(
            LineItem("wire", name, qty, "m", per_m, round(qty * per_m, 4))
        )

    # connectors as materials
    connector_count = 0
    for name, conn in harness.connectors.items():
        if conn.ignore_in_bom:
            continue
        connector_count += 1
        up = _price(prices, name, conn.mpn if isinstance(conn.mpn, str) else None)
        if up is None:
            unpriced.append(f"connector {name}")
            up = 0.0
        items.append(LineItem("connector", name, 1, "ea", up, round(up, 4)))

    # labour
    crimps = crimp_count(harness)
    labor = crimps * cfg.labor_per_crimp + connector_count * cfg.labor_per_connector
    items.append(
        LineItem(
            "labor",
            f"{crimps} crimps + {connector_count} connectors",
            1,
            "job",
            round(labor, 4),
            round(labor, 4),
        )
    )

    material_cost = round(sum(i.total for i in items if i.kind != "labor"), 4)
    labor_cost = round(labor, 4)
    subtotal = round(material_cost + labor_cost, 4)
    total = round(subtotal * (1 + cfg.markup), 4)
    return {
        "items": items,
        "material_cost": material_cost,
        "labor_cost": labor_cost,
        "subtotal": subtotal,
        "markup": cfg.markup,
        "total": total,
        "currency": cfg.currency,
        "unpriced": unpriced,
    }


def to_text(q: dict) -> str:
    cur = q["currency"]
    lines = [f"{'REF':<24} {'QTY':>8} {'UNIT':>5} {'PRICE':>10} {'TOTAL':>10}"]
    for i in q["items"]:
        lines.append(
            f"{i.ref[:24]:<24} {i.qty:>8} {i.unit:>5} "
            f"{cur}{i.unit_price:>9.2f} {cur}{i.total:>9.2f}"
        )
    lines.append("")
    lines.append(f"Material: {cur}{q['material_cost']:.2f}")
    lines.append(f"Labor:    {cur}{q['labor_cost']:.2f}")
    lines.append(f"Subtotal: {cur}{q['subtotal']:.2f}")
    lines.append(f"Markup:   {q['markup'] * 100:.0f}%")
    lines.append(f"TOTAL:    {cur}{q['total']:.2f}")
    if q["unpriced"]:
        lines.append(f"(unpriced: {', '.join(q['unpriced'])})")
    return "\n".join(lines) + "\n"
