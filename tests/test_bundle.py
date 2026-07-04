"""Tests for bundle diameter and fill (wireviz.wv_bundle)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_bundle import (  # noqa: E402
    bundle_diameter,
    bundle_report,
    conductor_diameter,
    fill_ratio,
    recommend_sleeve,
    wire_outer_diameter,
)


def test_conductor_diameter_known():
    # 24 AWG ~0.205 mm^2 -> ~0.511 mm conductor diameter
    assert abs(conductor_diameter("24", "AWG") - 0.511) < 0.01


def test_wire_od_adds_insulation():
    cd = conductor_diameter("24", "AWG")
    od = wire_outer_diameter("24", "AWG", wall=0.4)
    assert abs(od - (cd + 0.8)) < 1e-9


def test_single_wire_bundle_is_wire_od():
    assert bundle_diameter([1.3]) == 1.3


def test_bundle_grows_with_count():
    d = 1.3
    assert bundle_diameter([d, d, d]) > bundle_diameter([d, d]) > d


def test_fill_ratio():
    # one 1.3 mm wire in a 3 mm sleeve
    fr = fill_ratio([1.3], 3.0)
    assert abs(fr - (1.3**2) / (3.0**2)) < 1e-9


def test_recommend_sleeve_picks_smallest_within_limit():
    ods = [1.311, 1.311, 1.311]
    s = recommend_sleeve(ods)
    assert s == 4  # 3 mm overfills (>40%), 4 mm fits


def test_bundle_report_on_harness():
    h = wireviz.parse(
        """
connectors:
  X1: {pincount: 3}
  X2: {pincount: 3}
cables:
  W1: {wirecount: 3, gauge: 24 AWG}
connections:
  -
    - X1: [1, 2, 3]
    - W1: [1, 2, 3]
    - X2: [1, 2, 3]
""",
        return_types="harness",
    )
    rep = bundle_report(h)
    w1 = next(r for r in rep if r.cable == "W1")
    assert w1.wire_count == 3
    assert w1.bundle_od > w1.wire_od
    assert w1.recommended_sleeve in (3, 4, 5)


def test_shield_counts_as_a_wire():
    h = wireviz.parse(
        """
connectors:
  X1: {pincount: 1}
  X2: {pincount: 1}
cables:
  W1: {wirecount: 2, gauge: 24 AWG, shield: true}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
""",
        return_types="harness",
    )
    w1 = next(r for r in bundle_report(h) if r.cable == "W1")
    assert w1.wire_count == 3  # 2 wires + shield


def test_gaugeless_cable_still_reports_wire_count():
    # regression: a populated cable with no gauge must still report its count
    h = wireviz.parse(
        """
connectors:
  X1: {pincount: 4}
  X2: {pincount: 4}
cables:
  W1: {wirecount: 4, length: 2}
connections:
  -
    - X1: [1, 2, 3, 4]
    - W1: [1, 2, 3, 4]
    - X2: [1, 2, 3, 4]
""",
        return_types="harness",
    )
    w1 = next(r for r in bundle_report(h) if r.cable == "W1")
    assert w1.wire_count == 4  # not silently 0
    assert w1.wire_od is None  # but no diameter without a gauge


def test_no_gauge_yields_no_diameter():
    h = wireviz.parse(
        """
connectors:
  X1: {pincount: 1}
  X2: {pincount: 1}
cables:
  W1: {wirecount: 1}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
""",
        return_types="harness",
    )
    w1 = next(r for r in bundle_report(h) if r.cable == "W1")
    assert w1.wire_od is None


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
    print(f"\n{passed}/{len(tests)} bundle tests passed")
    sys.exit(0 if passed == len(tests) else 1)
