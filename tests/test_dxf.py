"""Tests for DXF export (wireviz.wv_dxf)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_dxf import formboard_to_dxf  # noqa: E402

YML = """
connectors:
  X1: {pincount: 2}
  X2: {pincount: 2}
cables:
  W1: {wirecount: 2, length: 0.3}
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""


def h(yml=YML):
    return wireviz.parse(yml, return_types="harness")


def test_dxf_structure():
    dxf = formboard_to_dxf(h())
    assert dxf.startswith("0\nSECTION\n2\nENTITIES")
    assert dxf.rstrip().endswith("EOF")


def test_has_expected_entities():
    dxf = formboard_to_dxf(h())
    assert "\nLINE\n" in dxf  # connector rects + bundles
    assert "\nCIRCLE\n" in dxf  # mounting pegs
    assert "\nTEXT\n" in dxf  # labels


def test_layers_present():
    dxf = formboard_to_dxf(h())
    for layer in ("BUNDLES", "CONNECTORS", "PEGS", "TEXT"):
        assert layer in dxf


def test_coordinate_pairs_are_numeric():
    dxf = formboard_to_dxf(h())
    lines = dxf.splitlines()
    # every group code 10/20 must be followed by a float
    for i, ln in enumerate(lines[:-1]):
        if ln in ("10", "20", "11", "21", "40"):
            float(lines[i + 1])  # raises if not numeric


def test_all_examples_export_dxf():
    for subdir in ("examples", "tutorial"):
        for y in sorted((REPO_ROOT / subdir).glob("*.yml")):
            dxf = formboard_to_dxf(wireviz.parse(str(y), return_types="harness"))
            assert dxf.rstrip().endswith("EOF")


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
    print(f"\n{passed}/{len(tests)} dxf tests passed")
    sys.exit(0 if passed == len(tests) else 1)
