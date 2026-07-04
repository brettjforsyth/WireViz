# -*- coding: utf-8 -*-
"""Revision diff between two harnesses.

Compares two parsed harnesses (an old and a new revision) and reports what was
added, removed, or changed at the connector, cable, and wire level — a
changelog for a harness so a reviewer can see exactly what moved between revs.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

# connector/cable attributes worth diffing
_CONNECTOR_ATTRS = ("pincount", "type", "subtype", "manufacturer", "mpn", "gender", "pinlabels")
_CABLE_ATTRS = ("wirecount", "gauge", "gauge_unit", "length", "length_unit", "colors", "shield", "mpn")


@dataclass
class ItemChange:
    name: str
    changes: List[Tuple[str, Any, Any]] = field(default_factory=list)  # (attr, old, new)


@dataclass
class HarnessDiff:
    connectors_added: List[str] = field(default_factory=list)
    connectors_removed: List[str] = field(default_factory=list)
    connectors_changed: List[ItemChange] = field(default_factory=list)
    cables_added: List[str] = field(default_factory=list)
    cables_removed: List[str] = field(default_factory=list)
    cables_changed: List[ItemChange] = field(default_factory=list)
    wires_added: List[str] = field(default_factory=list)
    wires_removed: List[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not any(
            (
                self.connectors_added,
                self.connectors_removed,
                self.connectors_changed,
                self.cables_added,
                self.cables_removed,
                self.cables_changed,
                self.wires_added,
                self.wires_removed,
            )
        )


def _attr_diff(old, new, attrs) -> List[Tuple[str, Any, Any]]:
    changes = []
    for a in attrs:
        ov, nv = getattr(old, a, None), getattr(new, a, None)
        if ov != nv:
            changes.append((a, ov, nv))
    return changes


def _wire_keys(harness) -> Dict[str, str]:
    """Map a stable wire key -> its endpoint description, per connection."""
    out = {}
    for cname, cable in harness.cables.items():
        for c in cable.connections:
            key = f"{cname}:{c.via_port} {c.from_name}:{c.from_pin}->{c.to_name}:{c.to_pin}"
            out[key] = key
    return out


def diff_harnesses(old, new) -> HarnessDiff:
    d = HarnessDiff()

    # connectors
    old_c, new_c = old.connectors, new.connectors
    d.connectors_added = sorted(set(new_c) - set(old_c))
    d.connectors_removed = sorted(set(old_c) - set(new_c))
    for name in sorted(set(old_c) & set(new_c)):
        ch = _attr_diff(old_c[name], new_c[name], _CONNECTOR_ATTRS)
        if ch:
            d.connectors_changed.append(ItemChange(name, ch))

    # cables
    old_w, new_w = old.cables, new.cables
    d.cables_added = sorted(set(new_w) - set(old_w))
    d.cables_removed = sorted(set(old_w) - set(new_w))
    for name in sorted(set(old_w) & set(new_w)):
        ch = _attr_diff(old_w[name], new_w[name], _CABLE_ATTRS)
        if ch:
            d.cables_changed.append(ItemChange(name, ch))

    # wires (connections)
    ok, nk = set(_wire_keys(old)), set(_wire_keys(new))
    d.wires_added = sorted(nk - ok)
    d.wires_removed = sorted(ok - nk)
    return d


def to_text(d: HarnessDiff) -> str:
    if d.empty:
        return "No changes.\n"
    lines = []

    def section(title, added, removed, changed=None):
        if not (added or removed or changed):
            return
        lines.append(title)
        for a in added:
            lines.append(f"  + {a}")
        for r in removed:
            lines.append(f"  - {r}")
        for c in changed or []:
            for attr, ov, nv in c.changes:
                lines.append(f"  ~ {c.name}.{attr}: {ov!r} -> {nv!r}")

    section("Connectors:", d.connectors_added, d.connectors_removed, d.connectors_changed)
    section("Cables:", d.cables_added, d.cables_removed, d.cables_changed)
    section("Wires:", d.wires_added, d.wires_removed)
    return "\n".join(lines) + "\n"
