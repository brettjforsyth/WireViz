"""Tests for revision diff (wireviz.wv_diff)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_diff import diff_harnesses, to_text  # noqa: E402


def h(yml):
    return wireviz.parse(yml, return_types="harness")


OLD = """
connectors:
  X1: {pincount: 2}
  X2: {pincount: 2}
cables:
  W1: {wirecount: 2, gauge: 24 AWG, length: 1}
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""

NEW = """
connectors:
  X1: {pincount: 3}          # changed pincount
  X2: {pincount: 2}
  X3: {pincount: 1}          # added connector (wired below so it exists)
cables:
  W1: {wirecount: 2, gauge: 22 AWG, length: 1}   # changed gauge
  W2: {wirecount: 1}                              # added cable
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
  -
    - X1: [3]
    - W2: [1]
    - X3: [1]
"""


def test_identical_is_empty():
    d = diff_harnesses(h(OLD), h(OLD))
    assert d.empty
    assert to_text(d) == "No changes.\n"


def test_connector_added():
    d = diff_harnesses(h(OLD), h(NEW))
    assert "X3" in d.connectors_added


def test_connector_attr_changed():
    d = diff_harnesses(h(OLD), h(NEW))
    x1 = next(c for c in d.connectors_changed if c.name == "X1")
    attrs = {a for a, _, _ in x1.changes}
    assert "pincount" in attrs


def test_cable_attr_changed():
    d = diff_harnesses(h(OLD), h(NEW))
    w1 = next(c for c in d.cables_changed if c.name == "W1")
    attrs = {a for a, _, _ in w1.changes}
    assert "gauge" in attrs


def test_connector_removed():
    d = diff_harnesses(h(NEW), h(OLD))  # reversed
    assert "X3" in d.connectors_removed


def test_wire_changes_detected():
    old = """
connectors: {X1: {pincount: 2}, X2: {pincount: 2}}
cables: {W1: {wirecount: 2}}
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""
    new = """
connectors: {X1: {pincount: 2}, X2: {pincount: 2}}
cables: {W1: {wirecount: 2}}
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [2, 1]
"""
    d = diff_harnesses(h(old), h(new))
    assert d.wires_added and d.wires_removed


def test_equivalent_gauge_is_not_a_change():
    # regression: 0.25 (number) and "0.25 mm2" are the same gauge
    a = """
connectors: {X1: {pincount: 1}, X2: {pincount: 1}}
cables: {W1: {wirecount: 1, gauge: 0.25}}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
"""
    b = a.replace("gauge: 0.25", "gauge: 0.25 mm2")
    d = diff_harnesses(h(a), h(b))
    changed = {c.name for c in d.cables_changed}
    assert "W1" not in changed  # no phantom gauge change


def test_text_report_lists_changes():
    t = to_text(diff_harnesses(h(OLD), h(NEW)))
    assert "X3" in t and "pincount" in t


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
    print(f"\n{passed}/{len(tests)} diff tests passed")
    sys.exit(0 if passed == len(tests) else 1)
