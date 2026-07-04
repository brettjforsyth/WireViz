# -*- coding: utf-8 -*-
"""Branch-segment routed length.

A harness length is rarely a single number: a wire runs along a trunk and out a
branch, so its true cut length is the sum of the physical segments it traverses.
This models the harness as named segments with lengths and assigns each cable to
a path of segments; the routed length is the sum of that path.

A ``routing`` spec is a plain dict, so it can live in a side file or a YAML
section::

    routing:
      segments: {trunk: 1.2, branch_a: 0.4, branch_b: 0.8}   # metres
      cables:
        W1: [trunk, branch_a]      # routed length = 1.6 m
        W2: [trunk, branch_b]      # routed length = 2.0 m
"""

from typing import Dict, List, Optional


def routed_length(path: List[str], segment_lengths: Dict[str, float]) -> float:
    """Sum the lengths of the segments in `path` (unknown segments count 0)."""
    return round(sum(segment_lengths.get(s, 0.0) for s in path or []), 6)


def routed_lengths(harness, routing: dict) -> Dict[str, float]:
    """Routed length per cable.

    Cables listed in ``routing['cables']`` get the sum of their segment path;
    any other cable keeps its own declared length.
    """
    seg = routing.get("segments", {}) or {}
    paths = routing.get("cables", {}) or {}
    out: Dict[str, float] = {}
    for name, cable in harness.cables.items():
        if name in paths:
            out[name] = routed_length(paths[name], seg)
        else:
            out[name] = float(cable.length or 0)
    return out


def apply_routed_lengths(harness, routing: dict) -> Dict[str, float]:
    """Set each cable's length to its routed length (so the cut sheet, weight,
    etc. use it) and return the map of applied lengths."""
    lengths = routed_lengths(harness, routing)
    for name, cable in harness.cables.items():
        if name in (routing.get("cables") or {}):
            cable.length = lengths[name]
    return lengths


def unused_segments(routing: dict) -> List[str]:
    """Declared segments not referenced by any cable path."""
    seg = set((routing.get("segments") or {}).keys())
    used = set()
    for path in (routing.get("cables") or {}).values():
        used.update(path or [])
    return sorted(seg - used)


def missing_segments(routing: dict) -> List[str]:
    """Segments referenced by a cable path but never given a length."""
    seg = set((routing.get("segments") or {}).keys())
    used = set()
    for path in (routing.get("cables") or {}).values():
        used.update(path or [])
    return sorted(used - seg)
