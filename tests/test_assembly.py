"""Tests for the assembly traveler (wireviz.wv_assembly)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_assembly import build_traveler, to_text  # noqa: E402

YML = """
connectors:
  X1: {pincount: 2, type: Header}
  X2: {pincount: 2}
cables:
  W1: {wirecount: 2, gauge: 24 AWG, length: 0.5}
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""


def h(yml=YML):
    return wireviz.parse(yml, return_types="harness")


def test_steps_numbered_sequentially():
    steps = build_traveler(h())
    assert [s.number for s in steps] == list(range(1, len(steps) + 1))


def test_has_cut_and_populate_steps():
    steps = build_traveler(h())
    kinds = [s.kind for s in steps]
    assert "cut" in kinds and "populate" in kinds
    # cut comes before populate
    assert kinds.index("cut") < kinds.index("populate")


def test_populate_lists_cavities():
    steps = build_traveler(h())
    pop = next(s for s in steps if s.kind == "populate" and "X1" in s.title)
    assert "cavity 1" in pop.detail and "W1:1" in pop.detail
    assert "Header" in pop.title  # connector type shown


def test_mate_step_present():
    steps = build_traveler(
        h(
            """
connectors:
  X1: {pincount: 1}
  X2: {pincount: 1}
connections:
  -
    - X1
    - ==>
    - X2
"""
        )
    )
    assert any(s.kind == "mate" for s in steps)


def test_cavities_sorted_numerically():
    # regression: cavity 2 must come before cavity 10, not lexicographically after
    yml = """
connectors:
  X1: {pincount: 12}
  X2: {pincount: 12}
cables:
  W1: {wirecount: 12}
connections:
  -
    - X1: [1-12]
    - W1: [1-12]
    - X2: [1-12]
"""
    steps = build_traveler(h(yml))
    pop = next(s for s in steps if s.kind == "populate" and "X1" in s.title)
    assert pop.detail.index("cavity 2 ") < pop.detail.index("cavity 10 ")


def test_to_text_renders():
    t = to_text(build_traveler(h()))
    assert "Assembly Traveler" in t and "Cut W1" in t


def test_all_examples_produce_travelers():
    for subdir in ("examples", "tutorial"):
        for y in sorted((REPO_ROOT / subdir).glob("*.yml")):
            steps = build_traveler(wireviz.parse(str(y), return_types="harness"))
            assert isinstance(steps, list)


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
    print(f"\n{passed}/{len(tests)} assembly tests passed")
    sys.exit(0 if passed == len(tests) else 1)
