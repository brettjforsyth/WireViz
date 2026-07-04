# -*- coding: utf-8 -*-
"""Harness variants / configurations.

One source file can describe a family of harnesses: tag any connector or cable
with ``variants: [sport, base]`` and it is included only in those variants (an
untagged component is in every variant). ``apply_variant`` produces the WireViz
data dict for a chosen variant, dropping the excluded components and any
connection set that references one, so a single YAML yields LHD/RHD, trim
levels, options, etc.

Declare the available variants at the top level::

    variants: [base, sport]
    connectors:
      FOG: {pincount: 2, variants: [sport]}   # only in the 'sport' harness
"""

import copy
from typing import List, Optional, Set


def list_variants(data: dict) -> List[str]:
    """Declared variants (top-level ``variants``) plus any referenced on
    components, de-duplicated in first-seen order."""
    out: List[str] = []
    seen: Set[str] = set()

    def add(v):
        if v not in seen:
            seen.add(v)
            out.append(v)

    for v in data.get("variants", []) or []:
        add(str(v))
    for section in ("connectors", "cables"):
        for attrs in (data.get(section) or {}).values():
            if isinstance(attrs, dict):
                for v in attrs.get("variants", []) or []:
                    add(str(v))
    return out


def _in_variant(attrs: dict, variant: Optional[str]) -> bool:
    tags = attrs.get("variants") if isinstance(attrs, dict) else None
    if not tags:
        return True  # untagged -> in every variant
    if variant is None:
        return True  # no variant selected -> keep everything
    return variant in [str(t) for t in tags]


def _strip(attrs):
    if isinstance(attrs, dict):
        attrs = dict(attrs)
        attrs.pop("variants", None)
    return attrs


def _designators_in_entry(entry) -> Set[str]:
    """Designators referenced by a connection-set entry (dict or string)."""
    out = set()
    if isinstance(entry, dict):
        out.update(str(k) for k in entry.keys())
    elif isinstance(entry, str):
        out.add(entry)
    return out


def apply_variant(data: dict, variant: Optional[str] = None) -> dict:
    """Return the WireViz data dict for `variant` (or all components if None).

    Components whose ``variants`` list excludes the variant are dropped, along
    with any connection set that references a dropped component. The ``variants``
    keys are removed so the result parses as ordinary WireViz data.
    """
    result = copy.deepcopy(data)
    result.pop("variants", None)

    kept: Set[str] = set()
    for section in ("connectors", "cables"):
        items = result.get(section) or {}
        new_items = {}
        for name, attrs in items.items():
            if _in_variant(attrs, variant):
                new_items[name] = _strip(attrs)
                kept.add(str(name))
        if section in result:
            result[section] = new_items

    # keep a connection set only if every designator it references survived
    # (a `X.A1` instance survives when its template connector `X` is kept)
    conns = result.get("connections")
    if isinstance(conns, list):
        filtered = []
        for cset in conns:
            names = {
                d
                for entry in (cset if isinstance(cset, list) else [])
                for d in _designators_in_entry(entry)
                if not _is_arrow(d)
            }
            if all((n in kept or n.split(".")[0] in kept) for n in names):
                filtered.append(cset)
        result["connections"] = filtered
    return result


def _is_arrow(s: str) -> bool:
    return bool(s) and set(str(s)) <= set("-<>=")
