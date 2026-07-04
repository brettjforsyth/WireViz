# -*- coding: utf-8 -*-
"""Project-level BOM consolidation.

Rolls up the BOMs of several harnesses into one purchasing BOM: identical line
items are merged across harnesses, quantities summed, and the source harnesses
recorded — what a buyer needs to order for a whole vehicle/program at once
rather than one harness at a time.
"""

from typing import Dict, List


def consolidate_bom(harnesses: Dict[str, object]) -> List[dict]:
    """Merge the BOMs of ``{name: harness}`` into one list of purchasing lines.

    Line items are keyed on the per-harness BOM grouping key (description +
    part numbers), so the same part in two harnesses becomes one line with the
    combined quantity and the designators namespaced by harness.
    """
    merged: Dict[tuple, dict] = {}
    for hname, harness in harnesses.items():
        for row in harness.bom():
            key = tuple(row.get("key") or (row.get("description", ""),))
            m = merged.setdefault(
                key,
                {
                    "description": row.get("description", ""),
                    "mpn": row.get("mpn"),
                    "manufacturer": row.get("manufacturer"),
                    "unit": row.get("unit") or "",
                    "qty": 0.0,
                    "harnesses": set(),
                    "designators": [],
                },
            )
            m["qty"] += float(row.get("qty", 1) or 0)
            m["harnesses"].add(hname)
            m["designators"] += [f"{hname}/{d}" for d in row.get("designators", [])]

    out = []
    for i, m in enumerate(
        sorted(merged.values(), key=lambda r: (str(r["mpn"] or ""), r["description"])),
        start=1,
    ):
        q = round(m["qty"], 4)
        out.append(
            {
                "id": i,
                "description": m["description"],
                "mpn": m["mpn"],
                "manufacturer": m["manufacturer"],
                "qty": int(q) if float(q).is_integer() else q,
                "unit": m["unit"],
                "harnesses": sorted(m["harnesses"]),
                "designators": m["designators"],
            }
        )
    return out


def to_tsv(rows: List[dict]) -> str:
    cols = ["id", "description", "mpn", "manufacturer", "qty", "unit", "harnesses", "designators"]
    lines = ["\t".join(c.capitalize() for c in cols)]
    for r in rows:
        lines.append(
            "\t".join(
                [
                    str(r["id"]),
                    r["description"],
                    str(r["mpn"] or ""),
                    str(r["manufacturer"] or ""),
                    str(r["qty"]),
                    r["unit"],
                    ", ".join(r["harnesses"]),
                    ", ".join(r["designators"]),
                ]
            )
        )
    return "\n".join(lines) + "\n"
