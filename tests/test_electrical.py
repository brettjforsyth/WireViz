"""Tests for wire electrical properties (wv_electrical) and electrical DRC rules."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_drc import run_drc  # noqa: E402
from wireviz.wv_electrical import (  # noqa: E402
    ampacity_for,
    ampacity_margin,
    area_to_awg,
    awg_area_mm2,
    recommend_gauge,
    resistance_per_m,
    voltage_drop,
)


def codes(findings):
    return {f.code for f in findings}


def drc(yml):
    return run_drc(wireviz.parse(yml, return_types="harness"))


# --- physics ---------------------------------------------------------------


def test_awg_area_matches_known():
    # 24 AWG is ~0.205 mm^2
    assert abs(awg_area_mm2(24) - 0.205) < 0.005


def test_area_awg_roundtrip():
    for awg in (30, 24, 18, 12, 4, 0):
        assert abs(area_to_awg(awg_area_mm2(awg)) - awg) < 1e-6


def test_resistance_awg_matches_known():
    # 24 AWG copper ~0.0842 ohm/m
    assert abs(resistance_per_m("24", "AWG") - 0.0842) < 0.002
    # 18 AWG ~0.0209 ohm/m
    assert abs(resistance_per_m("18", "AWG") - 0.0209) < 0.001


def test_resistance_mm2():
    # 1 mm^2 copper: rho/area = 1.724e-8 / 1e-6 = 0.01724 ohm/m
    assert abs(resistance_per_m(1, "mm²") - 0.01724) < 1e-4


def test_ampacity_table_lookup():
    assert ampacity_for("18", "AWG") == 16.0
    assert ampacity_for("10", "AWG") == 55.0


def test_ampacity_mm2_interpolated():
    a = ampacity_for(0.25, "mm²")
    assert 4.0 < a < 6.0  # ~0.25 mm^2 sits between 24 and 22 AWG


def test_voltage_drop_known():
    # 10 A through 18 AWG (0.0209 ohm/m) over 2 m single conductor ~0.42 V
    v = voltage_drop(10, "18", "AWG", 2.0)
    assert abs(v - 0.418) < 0.02
    # two conductors doubles it
    assert abs(voltage_drop(10, "18", "AWG", 2.0, conductors=2) - 2 * v) < 1e-9


def test_ampacity_margin():
    assert abs(ampacity_margin(8, "18", "AWG") - 0.5) < 0.01  # 8/16


# --- DRC electrical rules --------------------------------------------------


def _cable_yml(current=None, gauge="18 AWG", voltage=None, length=2):
    cur = f"\n    current: {current}" if current is not None else ""
    volt = f"\n    voltage: {voltage}" if voltage is not None else ""
    return f"""
connectors:
  X1: {{pincount: 1}}
  X2: {{pincount: 1}}
cables:
  W1:
    wirecount: 1
    gauge: {gauge}
    length: {length}{cur}{volt}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
"""


def test_no_current_no_electrical_findings():
    c = codes(drc(_cable_yml(current=None)))
    assert "E-AMPACITY" not in c and "W-VDROP" not in c


def test_ampacity_exceeded_is_error():
    # 18 AWG ampacity ~16 A; 25 A exceeds it
    c = codes(drc(_cable_yml(current=25)))
    assert "E-AMPACITY" in c


def test_ampacity_margin_warning():
    # 15 A on 18 AWG is ~94% of 16 A -> margin warning, not error
    c = codes(drc(_cable_yml(current=15)))
    assert "W-AMPACITY-MARGIN" in c
    assert "E-AMPACITY" not in c


def test_ampacity_ok():
    c = codes(drc(_cable_yml(current=5)))
    assert "E-AMPACITY" not in c and "W-AMPACITY-MARGIN" not in c


def test_voltage_drop_warning():
    # 10 A, 18 AWG, 5 m, 12 V -> ~1.05 V = ~8.7% > 5% limit
    c = codes(drc(_cable_yml(current=10, voltage=12, length=5)))
    assert "W-VDROP" in c


def test_voltage_drop_ok_when_short():
    # 10 A, 18 AWG, 0.5 m, 12 V -> ~0.1 V < 5%
    c = codes(drc(_cable_yml(current=10, voltage=12, length=0.5)))
    assert "W-VDROP" not in c


def test_recommend_gauge_ampacity_driven():
    # 30 A over a short run, no drop limit -> thinnest gauge with ampacity >= 30
    # 14 AWG is ~32 A (12 AWG ~41 A is thicker/overkill)
    r = recommend_gauge(30, 1.0)
    assert r["awg"] == 14
    assert r["ampacity"] >= 30


def test_recommend_gauge_voltage_drop_driven():
    # small current but a long run with a tight drop budget forces a thicker
    # gauge than ampacity alone would need
    loose = recommend_gauge(5, 1.0)
    tight = recommend_gauge(5, 10.0, max_drop_v=0.2, conductors=2)
    assert tight["awg"] < loose["awg"]  # thicker (smaller AWG number)
    assert tight["drop_v"] <= 0.2


def test_recommend_gauge_reports_limit_when_impossible():
    # absurd current beyond the thickest gauge -> flagged ampacity-limited
    r = recommend_gauge(1000, 1.0)
    assert r["limited_by"] == "ampacity"


def test_examples_still_clean_with_electrical_rules():
    # examples declare no current, so electrical rules must stay silent
    from wireviz.wv_drc import has_errors

    for subdir in ("examples", "tutorial"):
        for y in sorted((REPO_ROOT / subdir).glob("*.yml")):
            h = wireviz.parse(str(y), return_types="harness")
            findings = run_drc(h)
            assert not has_errors(findings), y.name


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
    print(f"\n{passed}/{len(tests)} electrical tests passed")
    sys.exit(0 if passed == len(tests) else 1)
