"""Connector face drawings for the vehicle view.

``face_for(connector)`` describes how to draw a connector's face: outline shape,
aspect ratio, housing colour, and where each cavity sits (normalised 0..1, x
right, y down) with the cavity id the model uses for that pin, all as seen from
the WIRE side (where the contacts go in).

A face is only marked ``verified`` when its cavity positions come from the
maker's drawing (``wv_faces_data.FACES``), its part number names that housing
(or the layout names the family for it), and every model pin id is a cavity id
on that drawing. Anything else gets an illustrative grid with the right number
of cavities, in pin order, and says so: a plausible-looking but wrong face is
worse than an honest generic one.
"""

import math
import re
from typing import Dict, List, Optional, Tuple

from wireviz.wv_faces_data import FACES

GENERIC_HOUSING = "#3b3b3b"

# family id -> verified layout (see wv_faces_data). Kept as a module attribute so
# a caller or test can add a family.
FAMILIES: Dict[str, dict] = dict(FACES)


def _grid(n: int):
    """Illustrative positions: rows of cavities, numbered left to right."""
    if n <= 0:
        return [], 1, 1
    if n <= 3:
        cols = n
    elif n == 4:
        cols = 2
    elif n <= 8:
        cols = math.ceil(n / 2)
    else:
        cols = math.ceil(math.sqrt(n * 2.2))
    rows = math.ceil(n / cols)
    out = []
    for i in range(n):
        r, c = divmod(i, cols)
        in_row = cols if r < rows - 1 else n - cols * (rows - 1)
        x0 = (cols - in_row) / 2  # centre a short last row
        out.append(((x0 + c + 0.5) / cols, (r + 0.5) / rows))
    return out, cols, rows


def _pin_ids(conn) -> List:
    pins = list(getattr(conn, "pins", None) or [])
    if not pins and getattr(conn, "pincount", None):
        pins = list(range(1, conn.pincount + 1))
    return pins


def _family_from_part(conn) -> Optional[Tuple[str, str]]:
    """(family, half) named first in the part number, so for "DT06-4S / DT04-4P"
    the harness half (named first) wins."""
    key = str(getattr(conn, "mpn", None) or getattr(conn, "type", None) or "").upper()
    best = None
    for fam_id, fam in FAMILIES.items():
        for pattern, half in fam.get("match", []):
            m = re.search(pattern, key)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), fam_id, half)
    return (best[1], best[2]) if best else None


def _parse_override(spec: str) -> Tuple[str, str]:
    parts = str(spec).split()
    return parts[0], ("mate" if len(parts) > 1 and parts[1].lower() in ("mate", "other") else "main")


def face_for(conn, family: Optional[str] = None) -> dict:
    """``family`` (e.g. "HD30-24-29" or "HD30-24-29 mate") overrides the part
    number match, for connectors whose part string is not a maker number."""
    pins = _pin_ids(conn)
    n = len(pins)
    found = _parse_override(family) if family else _family_from_part(conn)
    note = ""
    if found and found[0] in FAMILIES:
        fam_id, half = found
        fam = FAMILIES[fam_id]
        layout = fam.get(half) or fam["main"]
        ids = [str(c[0]) for c in layout["cavities"]]
        if n == len(ids) and all(str(p) in ids for p in pins):
            return {"family": fam_id, "shape": fam["shape"], "aspect": fam["aspect"],
                    "housing": fam.get("housing", GENERIC_HOUSING),
                    "view": layout["view"], "verified": True, "source": fam["source"],
                    "cavities": [{"id": _model_id(c[0], pins), "x": c[1], "y": c[2], "size": c[3]}
                                 for c in layout["cavities"]]}
        note = (f"; the maker's {fam_id} drawing names its cavities "
                f"{', '.join(ids[:6])}{'...' if len(ids) > 6 else ''}, which the model's pin ids do not match")
    if n == 1:  # a stud, bus or single terminal: draw it round
        return {"family": None, "shape": "round", "aspect": 1.0,
                "housing": GENERIC_HOUSING, "view": "single terminal",
                "verified": False, "source": "",
                "cavities": [{"id": pins[0], "x": 0.5, "y": 0.5}]}
    pos, cols, rows = _grid(n)
    return {"family": None, "shape": "rect", "aspect": max(cols, 1.2) / max(rows, 1) * 1.15,
            "housing": GENERIC_HOUSING,
            "view": "cavities shown in pin order, not the housing's real arrangement" + note,
            "verified": False, "source": "",
            "cavities": [{"id": p, "x": x, "y": y} for p, (x, y) in zip(pins, pos)]}


def _model_id(cavity_id, pins):
    """Return the model's own pin id for a drawing cavity id (ints stay ints)."""
    for p in pins:
        if str(p) == str(cavity_id):
            return p
    return cavity_id
