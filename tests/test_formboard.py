"""Tests for the 1:1 formboard output (wireviz.wv_formboard)."""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_formboard import (  # noqa: E402
    FormboardConfig,
    build_formboard,
    page_grid,
    render_formboard,
    to_mm,
)


def harness_of(yml):
    return wireviz.parse(yml, return_types="harness")


BASIC = """
connectors:
  X1: {pincount: 2}
  X2: {pincount: 2}
cables:
  W1:
    wirecount: 2
    length: 0.2   # metres -> 200 mm
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""


def test_unit_conversion():
    assert to_mm(1, "m") == 1000
    assert to_mm(1, "cm") == 10
    assert to_mm(1, "in") == 25.4
    assert to_mm(2, None) == 2  # default mm


def test_cable_length_is_physical_mm():
    lay = build_formboard(harness_of(BASIC))
    b = lay["bundles"][0]
    assert b["length_mm"] == 200.0
    assert "200 mm" in b["label"]


def test_connectors_spaced_by_cable_length():
    # single cable -> exact 1:1: horizontal gap between the connectors equals
    # the cable length (endpoints at the same y, so no vertical component)
    cfg = FormboardConfig()
    lay = build_formboard(harness_of(BASIC), cfg)
    x1 = lay["connectors"]["X1"]
    x2 = lay["connectors"]["X2"]
    gap = x2["x"] - (x1["x"] + cfg.connector_w)
    assert abs(gap - 200.0) < 1e-6


def test_output_is_life_size_svg():
    svg = render_formboard(harness_of(BASIC))
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")
    # width/height carry a mm suffix so it prints 1:1
    assert root.get("width").endswith("mm")
    assert root.get("height").endswith("mm")


def test_page_grid_counts():
    # a long harness must tile across multiple sheets
    yml = """
connectors:
  X1: {pincount: 1}
  X2: {pincount: 1}
cables:
  W1: {wirecount: 1, length: 5}   # 5 m = 5000 mm, far wider than one A3
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
"""
    cfg = FormboardConfig(page="A3", landscape=True)
    lay = build_formboard(harness_of(yml), cfg)
    grid = page_grid(lay, cfg)
    assert grid["cols"] >= 2
    assert grid["total"] == grid["cols"] * grid["rows"]


def test_short_cable_flagged():
    # a very short cable between connectors forced apart is flagged SHORT
    yml = """
connectors:
  X1: {pincount: 2}
  X2: {pincount: 2}
  X3: {pincount: 2}
cables:
  W1: {wirecount: 1, length: 2}      # long, sets the column spacing
  W2: {wirecount: 1, length: 0.001}  # 1 mm, cannot span the forced gap
connections:
  -
    - X1: [1]
    - W1: [1]
    - X3: [1]
  -
    - X2: [1]
    - W2: [1]
    - X3: [2]
"""
    lay = build_formboard(harness_of(yml))
    assert any(b["short"] for b in lay["bundles"])


def test_all_examples_render_formboard():
    for subdir in ("examples", "tutorial"):
        for y in sorted((REPO_ROOT / subdir).glob("*.yml")):
            h = wireviz.parse(str(y), return_types="harness")
            svg = render_formboard(h)
            ET.fromstring(svg)  # valid XML


if __name__ == "__main__":
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
            print(f"ok   {t.__name__}")
        except Exception:
            print(f"FAIL {t.__name__}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} formboard tests passed")
    sys.exit(0 if passed == len(tests) else 1)
