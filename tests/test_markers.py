"""Tests for wire markers (wireviz.wv_markers)."""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_markers import build_markers, to_csv, to_svg_sheet  # noqa: E402

YML = """
connectors:
  X1: {pincount: 2}
  X2: {pincount: 2}
cables:
  W1: {wirecount: 2, colors: [RD, BK]}
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""


def h():
    return wireviz.parse(YML, return_types="harness")


def test_two_markers_per_wire():
    markers = build_markers(h())
    # 2 wires * 2 terminated ends = 4 markers
    assert len(markers) == 4
    ends = {(m.wire, m.end) for m in markers}
    assert ("W1:1", "from") in ends and ("W1:1", "to") in ends


def test_marker_text_shows_destination():
    markers = build_markers(h())
    frm = next(m for m in markers if m.wire == "W1:1" and m.end == "from")
    assert "X1:1" in frm.text and "X2:1" in frm.text


def test_open_end_not_labelled():
    # a shield connected only at one end -> only one marker for it
    yml = """
connectors:
  X1: {pincount: 1}
  X2: {pincount: 1}
cables:
  W1: {wirecount: 1, shield: true}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
  -
    - X1: [1]
    - W1: [s]
"""
    markers = build_markers(h_yml(yml))
    shield_markers = [m for m in markers if m.wire == "W1:s"]
    assert len(shield_markers) == 1  # only the terminated end


def h_yml(yml):
    return wireviz.parse(yml, return_types="harness")


def test_csv_and_svg():
    markers = build_markers(h())
    csv = to_csv(markers)
    assert "marker,wire,end" in csv
    svg = to_svg_sheet(markers)
    ET.fromstring(svg)  # valid XML
    assert svg.count("<g class=\"label\">") == 4


def test_custom_template():
    markers = build_markers(h(), template="{wire} [{color}]")
    frm = next(m for m in markers if m.wire == "W1:1")
    assert "[RD]" in frm.text


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
    print(f"\n{passed}/{len(tests)} marker tests passed")
    sys.exit(0 if passed == len(tests) else 1)
