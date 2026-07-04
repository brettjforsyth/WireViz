"""Tests for ZPL label export (wireviz.wv_zpl)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_zpl import harness_to_zpl, marker_to_zpl, markers_to_zpl  # noqa: E402
from wireviz.wv_markers import build_markers  # noqa: E402

YML = """
connectors:
  X1: {pincount: 2}
  X2: {pincount: 2}
cables:
  W1: {wirecount: 2}
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""


def h():
    return wireviz.parse(YML, return_types="harness")


def test_single_label_structure():
    zpl = marker_to_zpl("W1:1 X1:1->X2:1")
    assert zpl.startswith("^XA") and zpl.endswith("^XZ")
    assert "^FDW1:1" in zpl and "^FS" in zpl


def test_control_chars_neutralised():
    zpl = marker_to_zpl("a^b~c")
    assert "^b" not in zpl.replace("^FD", "")  # the caret in data is gone
    assert "a b c" in zpl


def test_one_label_per_marker():
    markers = build_markers(h())
    zpl = markers_to_zpl(markers)
    assert zpl.count("^XA") == len(markers) == 4
    assert zpl.count("^XZ") == 4


def test_harness_convenience():
    zpl = harness_to_zpl(h())
    assert zpl.count("^XA") == 4
    assert "W1:1" in zpl


def test_all_examples_export_zpl():
    for subdir in ("examples", "tutorial"):
        for y in sorted((REPO_ROOT / subdir).glob("*.yml")):
            zpl = harness_to_zpl(wireviz.parse(str(y), return_types="harness"))
            # balanced start/end markers
            assert zpl.count("^XA") == zpl.count("^XZ")


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
    print(f"\n{passed}/{len(tests)} zpl tests passed")
    sys.exit(0 if passed == len(tests) else 1)
