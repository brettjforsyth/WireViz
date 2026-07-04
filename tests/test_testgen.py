"""Tests for the continuity/isolation test program (wireviz.wv_testgen)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_testgen import (  # noqa: E402
    continuity_tests,
    isolation_tests,
    summary,
    build_test_program,
    to_csv,
)

TWO_NET = """
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


def h(yml=TWO_NET):
    return wireviz.parse(yml, return_types="harness")


def test_continuity_is_n_minus_1_per_net():
    # two nets of two pins each -> 1 + 1 continuity checks
    c = continuity_tests(h())
    assert len(c) == 2
    assert all(s.kind == "continuity" and s.expect == "closed" for s in c)


def test_continuity_three_pin_net():
    yml = """
connectors:
  X1: {pincount: 1}
  X2: {pincount: 1}
  X3: {pincount: 1}
cables:
  W1: {wirecount: 1}
  W2: {wirecount: 1}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
  -
    - X2: [1]
    - W2: [1]
    - X3: [1]
"""
    # X1,X2,X3 all common -> one 3-pin net -> 2 continuity checks
    c = continuity_tests(h(yml))
    assert len(c) == 2


def test_isolation_between_nets():
    iso = isolation_tests(h())
    assert len(iso) == 1  # two nets -> one pairwise isolation check
    assert iso[0].expect == "open"
    assert iso[0].net_a != iso[0].net_b


def test_program_combines_both():
    steps = build_test_program(h())
    cont, iso = summary(steps)
    assert cont == 2 and iso == 1
    assert len(steps) == 3


def test_isolation_can_be_excluded():
    steps = build_test_program(h(), include_isolation=False)
    assert all(s.kind == "continuity" for s in steps)


def test_csv_export():
    csv = to_csv(build_test_program(h()))
    assert "step,kind,point_a" in csv
    assert "continuity" in csv and "isolation" in csv


def test_all_examples_generate_programs():
    for subdir in ("examples", "tutorial"):
        for y in sorted((REPO_ROOT / subdir).glob("*.yml")):
            steps = build_test_program(wireviz.parse(str(y), return_types="harness"))
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
    print(f"\n{passed}/{len(tests)} testgen tests passed")
    sys.exit(0 if passed == len(tests) else 1)
