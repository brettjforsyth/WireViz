"""Tests for the power/voltage-drop report (wireviz.wv_power)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_power import power_report, to_text  # noqa: E402


def h(current="", voltage=""):
    cur = f"\n    current: {current}" if current != "" else ""
    volt = f"\n    voltage: {voltage}" if voltage != "" else ""
    return wireviz.parse(
        f"""
connectors:
  X1: {{pincount: 1}}
  X2: {{pincount: 1}}
cables:
  W1:
    wirecount: 1
    gauge: 18 AWG
    length: 5{cur}{volt}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
""",
        return_types="harness",
    )


def test_no_current_no_rows():
    assert power_report(h())["rows"] == []


def test_resistance_and_vdrop_math():
    # 10 A, 18 AWG (0.0209 ohm/m), 5 m, 2 conductors
    r = power_report(h(current=10), conductors=2)["rows"][0]
    assert abs(r.resistance_ohm - 0.209) < 0.005  # 0.0209 * 5 * 2
    assert abs(r.vdrop_v - 2.09) < 0.05  # 10 * R
    assert abs(r.power_loss_w - 20.9) < 0.5  # I^2 * R


def test_percent_when_voltage_given():
    r = power_report(h(current=10, voltage=12))["rows"][0]
    assert abs(r.vdrop_pct - 17.4) < 0.5  # 2.09 / 12


def test_total_loss_summed():
    rep = power_report(h(current=10))
    assert rep["total_power_loss_w"] and rep["total_power_loss_w"] > 0


def test_single_conductor_halves_resistance():
    r2 = power_report(h(current=10), conductors=2)["rows"][0]
    r1 = power_report(h(current=10), conductors=1)["rows"][0]
    assert abs(r2.resistance_ohm - 2 * r1.resistance_ohm) < 1e-6


def test_text_renders():
    t = to_text(power_report(h(current=10)))
    assert "Cable" in t and "Ploss" in t


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
    print(f"\n{passed}/{len(tests)} power tests passed")
    sys.exit(0 if passed == len(tests) else 1)
