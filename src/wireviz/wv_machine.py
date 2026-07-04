# -*- coding: utf-8 -*-
"""Wire-processing (cut/strip machine) export.

Produces a per-wire job list in the shape automated cutting/stripping machines
(Schleuniger, Komax, …) consume: article (gauge + colour), cut length in mm,
strip length at each end, seals, and marker text. It reuses the cut sheet for
lengths/endpoints and the marker builder for end labels, so the shop-floor
machine job stays consistent with the drawing.
"""

from dataclasses import dataclass
from typing import List, Optional

from wireviz.wv_cutsheet import CutSheetOptions, build_cut_list
from wireviz.wv_formboard import to_mm
from wireviz.wv_idents import ident_string

JOB_COLUMNS = [
    "seq",
    "article",
    "gauge",
    "color",
    "length_mm",
    "strip_left_mm",
    "strip_right_mm",
    "seal_left",
    "seal_right",
    "marker",
    "from",
    "to",
]


@dataclass
class MachineOptions:
    strip_left_mm: float = 5.0
    strip_right_mm: float = 5.0
    seal_left: str = ""
    seal_right: str = ""


def machine_joblist(
    harness,
    cut_options: Optional[CutSheetOptions] = None,
    machine: Optional[MachineOptions] = None,
) -> List[dict]:
    """One machine job row per wire (cut length in mm)."""
    machine = machine or MachineOptions()
    rows = build_cut_list(harness, cut_options)
    out = []
    for i, r in enumerate(rows, start=1):
        length_mm = round(to_mm(r["length"], r["unit"] or "mm"), 1)
        color = str(r.get("color", ""))
        gauge = str(r.get("gauge", ""))
        article = " ".join(x for x in (gauge, color) if x) or r["wire"]
        out.append(
            {
                "seq": i,
                "article": article,
                "gauge": gauge,
                "color": color,
                "length_mm": length_mm,
                "strip_left_mm": machine.strip_left_mm,
                "strip_right_mm": machine.strip_right_mm,
                "seal_left": machine.seal_left,
                "seal_right": machine.seal_right,
                "marker": ident_string(r.get("ident_code", "")) or r["wire"],
                "from": r.get("from", ""),
                "to": r.get("to", ""),
            }
        )
    return out


def to_csv(rows: List[dict]) -> str:
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(JOB_COLUMNS)
    for r in rows:
        w.writerow([r.get(c, "") for c in JOB_COLUMNS])
    return buf.getvalue()
