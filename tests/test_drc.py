"""Tests for the design-rule checker (wireviz.wv_drc)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_drc import Severity, has_errors, run_drc  # noqa: E402


def drc(yml: str):
    harness = wireviz.parse(yml, return_types="harness")
    return run_drc(harness)


def codes(findings):
    return {f.code for f in findings}


# The bundled examples are hand-authored and should be free of DRC *errors*.
def test_examples_have_no_drc_errors():
    offenders = []
    for subdir in ("examples", "tutorial"):
        for y in sorted((REPO_ROOT / subdir).glob("*.yml")):
            harness = wireviz.parse(str(y), return_types="harness")
            findings = run_drc(harness)
            if has_errors(findings):
                errs = [str(f) for f in findings if f.severity >= Severity.ERROR]
                offenders.append(f"{y.name}: {errs}")
    assert not offenders, "examples tripped DRC errors:\n" + "\n".join(offenders)


def test_clean_harness_reports_no_errors():
    yml = """
connectors:
  X1:
    pincount: 2
  X2:
    pincount: 2
cables:
  W1:
    wirecount: 2
    gauge: 24 AWG
    length: 1
    mpn: CBL-1
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""
    findings = drc(yml)
    assert not has_errors(findings)


def test_wire_out_of_range():
    yml = """
connectors:
  X1: {pincount: 2}
  X2: {pincount: 2}
cables:
  W1: {wirecount: 2}
connections:
  -
    - X1: [1]
    - W1: [5]
    - X2: [1]
"""
    assert "E-WIRE-RANGE" in codes(drc(yml))


def test_wire_zero_is_out_of_range():
    yml = """
connectors:
  X1: {pincount: 2}
  X2: {pincount: 2}
cables:
  W1: {wirecount: 2}
connections:
  -
    - X1: [1]
    - W1: [0]
    - X2: [1]
"""
    assert "E-WIRE-RANGE" in codes(drc(yml))


def test_shield_absent():
    yml = """
connectors:
  X1: {pincount: 1}
  X2: {pincount: 1}
cables:
  W1: {wirecount: 1}
connections:
  -
    - X1: [1]
    - W1: [s]
    - X2: [1]
"""
    assert "E-SHIELD-ABSENT" in codes(drc(yml))


def test_shield_present_ok():
    yml = """
connectors:
  X1: {pincount: 1}
  X2: {pincount: 1}
cables:
  W1: {wirecount: 1, shield: true}
connections:
  -
    - X1: [1]
    - W1: [s]
    - X2: [1]
"""
    assert "E-SHIELD-ABSENT" not in codes(drc(yml))


def test_unused_wire():
    yml = """
connectors:
  X1: {pincount: 1}
  X2: {pincount: 1}
cables:
  W1: {wirecount: 3}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
"""
    findings = drc(yml)
    assert "W-WIRE-UNUSED" in codes(findings)
    # wires 2 and 3 are unused
    msg = [f for f in findings if f.code == "W-WIRE-UNUSED"][0].message
    assert "2" in msg and "3" in msg


def test_unconnected_pin():
    yml = """
connectors:
  X1: {pincount: 3}
  X2: {pincount: 1}
cables:
  W1: {wirecount: 1}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
"""
    findings = drc(yml)
    assert "W-PIN-UNCONNECTED" in codes(findings)


def test_label_count_mismatch():
    yml = """
connectors:
  X1:
    pincount: 3
    pinlabels: [A, B]
  X2: {pincount: 1}
cables:
  W1: {wirecount: 1}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
"""
    assert "W-LABEL-COUNT" in codes(drc(yml))


def test_no_mpn_is_info_only():
    yml = """
connectors:
  X1: {pincount: 1}
  X2: {pincount: 1}
cables:
  W1: {wirecount: 1, gauge: 24 AWG, length: 1}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
"""
    findings = drc(yml)
    assert "I-NO-MPN" in codes(findings)
    assert not has_errors(findings)


def test_mate_pincount_mismatch():
    yml = """
connectors:
  X1: {pincount: 2}
  X2: {pincount: 3}
connections:
  -
    - X1
    - ==>
    - X2
"""
    assert "E-MATE-PINCOUNT" in codes(drc(yml))


def test_mate_gender_same_warns():
    yml = """
connectors:
  X1: {pincount: 1, gender: pin}
  X2: {pincount: 1, gender: pin}
connections:
  -
    - X1: [1]
    - ==>
    - X2: [1]
"""
    assert "W-MATE-GENDER" in codes(drc(yml))


def test_mate_gender_opposing_ok():
    yml = """
connectors:
  X1: {pincount: 1, gender: pin}
  X2: {pincount: 1, gender: socket}
connections:
  -
    - X1: [1]
    - ==>
    - X2: [1]
"""
    assert "W-MATE-GENDER" not in codes(drc(yml))


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
    print(f"\n{passed}/{len(tests)} DRC tests passed")
    sys.exit(0 if passed == len(tests) else 1)
