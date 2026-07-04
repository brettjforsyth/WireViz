# -*- coding: utf-8 -*-
"""Importers: bootstrap a WireViz harness from external formats.

WireViz could only start from its own YAML. These importers turn the two most
common interchange formats — a from/to wire list (CSV) and a KiCad netlist —
into a WireViz data dict that ``wireviz.parse`` accepts, so a design can be
seeded from an existing pin list or schematic.
"""

import csv
import io
import re
from collections import OrderedDict, defaultdict
from typing import Dict, List, Optional

# header aliases -> canonical column
_ALIASES = {
    "from": "from", "from_connector": "from", "source": "from", "src": "from",
    "from_pin": "from_pin", "source_pin": "from_pin", "from_cavity": "from_pin",
    "to": "to", "to_connector": "to", "target": "to", "dest": "to", "destination": "to",
    "to_pin": "to_pin", "target_pin": "to_pin", "to_cavity": "to_pin",
    "color": "color", "colour": "color",
    "gauge": "gauge", "awg": "gauge",
    "cable": "cable", "bundle": "cable",
    "wire": "wire", "wire_number": "wire",
}


def _norm_header(h: str) -> Optional[str]:
    return _ALIASES.get(re.sub(r"[\s\-]+", "_", h.strip().lower()))


def _all_numeric(pins) -> bool:
    return all(str(p).isdigit() for p in pins)


def _pin_val(p):
    return int(p) if str(p).isdigit() else p


def from_wirelist(csv_text: str) -> dict:
    """Convert a from/to wire-list CSV into a WireViz data dict.

    Required columns (aliases accepted): from, from_pin, to, to_pin.
    Optional: color, gauge, cable. One cable is created per connector pair.
    """
    reader = csv.reader(io.StringIO(csv_text))
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return {"connectors": {}, "cables": {}, "connections": []}
    header = [_norm_header(c) for c in rows[0]]
    need = {"from", "from_pin", "to", "to_pin"}
    if not need.issubset({h for h in header if h}):
        raise ValueError(f"wire list needs columns {sorted(need)}; got {rows[0]}")

    connectors: Dict[str, set] = defaultdict(set)
    pairs: "OrderedDict[tuple, list]" = OrderedDict()
    for r in rows[1:]:
        rec = {header[i]: r[i].strip() for i in range(min(len(header), len(r))) if header[i]}
        fc, fp, tc, tp = rec.get("from"), rec.get("from_pin"), rec.get("to"), rec.get("to_pin")
        if not (fc and tc):
            continue
        connectors[fc].add(fp)
        connectors[tc].add(tp)
        key = (fc, tc, rec.get("cable") or "")
        pairs.setdefault(key, []).append(rec)

    data = {"connectors": {}, "cables": {}, "connections": []}
    for name, pins in connectors.items():
        pins = [p for p in pins if p]
        if pins and _all_numeric(pins):
            data["connectors"][name] = {"pincount": max(int(p) for p in pins)}
        else:
            data["connectors"][name] = {"pins": sorted(pins)}

    used_names = set()
    for (fc, tc, cname), wires in pairs.items():
        name = cname or f"{fc}-{tc}"
        base, i = name, 2
        while name in used_names:
            name, i = f"{base}_{i}", i + 1
        used_names.add(name)
        colors = [w.get("color", "") or "" for w in wires]
        gauges = {w.get("gauge") for w in wires if w.get("gauge")}
        cable = {"wirecount": len(wires)}
        if any(colors):
            cable["colors"] = colors
        if len(gauges) == 1:
            cable["gauge"] = gauges.pop()
        data["cables"][name] = cable
        from_pins = [_pin_val(w["from_pin"]) for w in wires]
        to_pins = [_pin_val(w["to_pin"]) for w in wires]
        data["connections"].append(
            [{fc: from_pins}, {name: list(range(1, len(wires) + 1))}, {tc: to_pins}]
        )
    return data


# --- KiCad netlist ---------------------------------------------------------


def _sexpr_tokens(text: str):
    for tok in re.findall(r'\(|\)|"[^"]*"|[^\s()]+', text):
        yield tok


def _parse_sexpr(text: str):
    stack, cur = [], []
    for tok in _sexpr_tokens(text):
        if tok == "(":
            new = []
            cur.append(new)
            stack.append(cur)
            cur = new
        elif tok == ")":
            cur = stack.pop()
        else:
            cur.append(tok.strip('"'))
    return cur[0] if cur else []


def _find_all(node, tag):
    out = []
    if isinstance(node, list):
        if node and node[0] == tag:
            out.append(node)
        for child in node:
            out.extend(_find_all(child, tag))
    return out


def _field(node, tag):
    for child in node if isinstance(node, list) else []:
        if isinstance(child, list) and child and child[0] == tag:
            return child[1] if len(child) > 1 else None
    return None


def from_kicad_netlist(text: str) -> dict:
    """Convert a KiCad ``(export ...)`` netlist into a WireViz data dict.

    Each component becomes a connector; each net's nodes are chained into
    point-to-point wires (one cable per connector pair).
    """
    tree = _parse_sexpr(text)
    connectors: Dict[str, set] = defaultdict(set)
    pairs: "OrderedDict[tuple, list]" = OrderedDict()

    for comp in _find_all(tree, "comp"):
        ref = _field(comp, "ref")
        if ref:
            connectors.setdefault(ref, set())

    for net in _find_all(tree, "net"):
        nodes = []
        for n in _find_all(net, "node"):
            ref, pin = _field(n, "ref"), _field(n, "pin")
            if ref and pin is not None:
                nodes.append((ref, pin))
                connectors[ref].add(pin)
        # chain consecutive nodes into wires
        for (fc, fp), (tc, tp) in zip(nodes, nodes[1:]):
            pairs.setdefault((fc, tc), []).append((fp, tp))

    data = {"connectors": {}, "cables": {}, "connections": []}
    for name, pins in connectors.items():
        pins = [p for p in pins if p]
        if pins and _all_numeric(pins):
            data["connectors"][name] = {"pincount": max(int(p) for p in pins)}
        elif pins:
            data["connectors"][name] = {"pins": sorted(pins)}
        else:
            data["connectors"][name] = {"pincount": 1}

    used = set()
    for (fc, tc), wires in pairs.items():
        name, base, i = f"{fc}-{tc}", f"{fc}-{tc}", 2
        while name in used:
            name, i = f"{base}_{i}", i + 1
        used.add(name)
        data["cables"][name] = {"wirecount": len(wires)}
        data["connections"].append(
            [
                {fc: [_pin_val(fp) for fp, _ in wires]},
                {name: list(range(1, len(wires) + 1))},
                {tc: [_pin_val(tp) for _, tp in wires]},
            ]
        )
    return data
