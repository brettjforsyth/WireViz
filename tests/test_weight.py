"""Tests for harness weight/length rollup (wireviz.wv_weight)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_weight import (  # noqa: E402
    copper_mass_per_m,
    weight_report,
    wire_mass_per_m,
)


def test_copper_mass_known():
    # 1 mm^2 copper weighs 8.96 g/m
    assert abs(copper_mass_per_m(1, "mm2") - 8.96) < 1e-6


def test_wire_mass_includes_insulation():
    cu = copper_mass_per_m("24", "AWG")
    total = wire_mass_per_m("24", "AWG")
    assert total > cu  # insulation adds mass


def test_report_totals():
    h = wireviz.parse(
        """
connectors:
  X1: {pincount: 3}
  X2: {pincount: 3}
cables:
  W1: {wirecount: 3, gauge: 24 AWG, length: 2}
connections:
  -
    - X1: [1, 2, 3]
    - W1: [1, 2, 3]
    - X2: [1, 2, 3]
""",
        return_types="harness",
    )
    rep = weight_report(h)
    # 3 wires * 2 m = 6 conductor-metres
    assert abs(rep["total_conductor_length_m"] - 6.0) < 1e-6
    assert rep["total_mass_g"] and rep["total_mass_g"] > 0


def test_no_gauge_gives_none_mass_but_length():
    h = wireviz.parse(
        """
connectors:
  X1: {pincount: 1}
  X2: {pincount: 1}
cables:
  W1: {wirecount: 1, length: 5}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
""",
        return_types="harness",
    )
    rep = weight_report(h)
    cw = rep["cables"][0]
    assert cw.mass_g is None
    assert abs(cw.conductor_length_m - 5.0) < 1e-6
    assert rep["total_mass_g"] is None  # nothing had a gauge


def test_shield_not_weighed_as_conductor():
    # regression: a braided shield must not be counted as a full copper wire
    def mass(shield):
        s = "shield: true" if shield else "shield: false"
        h = wireviz.parse(
            f"""
connectors:
  X1: {{pincount: 2}}
  X2: {{pincount: 2}}
cables:
  W1: {{wirecount: 2, gauge: 24 AWG, {s}, length: 1}}
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
""",
            return_types="harness",
        )
        return weight_report(h)

    shielded, plain = mass(True), mass(False)
    assert shielded["total_mass_g"] == plain["total_mass_g"]
    assert shielded["total_conductor_length_m"] == plain["total_conductor_length_m"] == 2.0


def test_all_examples_weigh():
    for subdir in ("examples", "tutorial"):
        for y in sorted((REPO_ROOT / subdir).glob("*.yml")):
            rep = weight_report(wireviz.parse(str(y), return_types="harness"))
            assert rep["total_conductor_length_m"] >= 0


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
    print(f"\n{passed}/{len(tests)} weight tests passed")
    sys.exit(0 if passed == len(tests) else 1)
