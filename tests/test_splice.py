"""Tests for the splice/junction planner (wireviz.wv_splice)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_splice import (  # noqa: E402
    current_overloads,
    find_splices,
    splice_bom,
)

# S is a dedicated splice where three wires meet
SPLICE = """
connectors:
  A: {pincount: 1}
  B: {pincount: 1}
  C: {pincount: 1}
  S: {style: simple, pincount: 1}
cables:
  W1: {wirecount: 1, gauge: 22 AWG, current: 10}
  W2: {wirecount: 1, gauge: 22 AWG, current: 5}
  W3: {wirecount: 1, gauge: 22 AWG, current: 5}
connections:
  -
    - A: [1]
    - W1: [1]
    - S: [1]
  -
    - S: [1]
    - W2: [1]
    - B: [1]
  -
    - S: [1]
    - W3: [1]
    - C: [1]
"""


def h(yml=SPLICE):
    return wireviz.parse(yml, return_types="harness")


def test_finds_three_way_splice():
    splices = find_splices(h())
    s = next(s for s in splices if s.connector == "S")
    assert s.branches == 3
    assert s.dedicated is True
    assert {w.cable for w in s.wires} == {"W1", "W2", "W3"}


def test_normal_pin_is_not_a_splice():
    # a plain 2-connector 1-wire link has no >=3-branch pin
    yml = """
connectors: {X1: {pincount: 1}, X2: {pincount: 1}}
cables: {W1: {wirecount: 1}}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
"""
    assert find_splices(h(yml)) == []


def test_splice_bom_groups_by_branch_count():
    bom = splice_bom(h())
    threeway = next(g for g in bom if g["branches"] == 3)
    assert threeway["qty"] == 1
    assert "S:1" in threeway["locations"]


def test_current_sum_overload_flagged():
    # 10 + 5 + 5 = 20 A at S; 22 AWG ampacity ~7 A -> overload
    over = current_overloads(h())
    assert any(o["splice"] == "S:1" for o in over)
    o = next(o for o in over if o["splice"] == "S:1")
    assert o["total_current"] == 20


def test_no_overload_without_current():
    yml = SPLICE.replace(", current: 10", "").replace(", current: 5", "")
    assert current_overloads(h(yml)) == []


def test_all_examples_planned():
    for subdir in ("examples", "tutorial"):
        for y in sorted((REPO_ROOT / subdir).glob("*.yml")):
            assert isinstance(find_splices(wireviz.parse(str(y), return_types="harness")), list)


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
    print(f"\n{passed}/{len(tests)} splice tests passed")
    sys.exit(0 if passed == len(tests) else 1)
