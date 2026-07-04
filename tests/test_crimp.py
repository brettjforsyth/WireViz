"""Tests for crimp tooling selection (wireviz.wv_crimp)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_connectors import apply_connector_types  # noqa: E402
from wireviz.wv_crimp import (  # noqa: E402
    crimp_for,
    crimp_report,
    crimp_setup_summary,
    register_crimp,
)


def test_crimp_for_in_range():
    spec = crimp_for("DT", 18)
    assert spec and spec["tool"] == "HDT-48-00" and spec["die"] == "size-16"


def test_crimp_for_selects_by_gauge():
    assert crimp_for("DT", 12)["die"] == "size-12"  # different range
    assert crimp_for("DT", 30) is None  # out of range
    assert crimp_for(None, 18) is None


def h_with_dt():
    data = {
        "connectors": {"X1": {"connector_type": "deutsch_dt_4"}, "X2": {"pincount": 4}},
        "cables": {"W1": {"wirecount": 4, "gauge": "18 AWG"}},
        "connections": [[{"X1": [1, 2, 3, 4]}, {"W1": [1, 2, 3, 4]}, {"X2": [1, 2, 3, 4]}]],
    }
    return wireviz.parse(apply_connector_types(data), return_types="harness")


def test_report_derives_tool_from_series_and_gauge():
    rows = crimp_report(h_with_dt())
    x1 = [r for r in rows if r.connector == "X1"]
    assert x1 and all(r.series == "DT" for r in x1)
    assert x1[0].awg == 18
    assert x1[0].tool == "HDT-48-00"


def test_setup_summary_groups():
    summ = crimp_setup_summary(h_with_dt())
    dt = next(g for g in summ if g["series"] == "DT")
    assert dt["tool"] == "HDT-48-00"
    assert len(dt["pins"]) == 4  # 4 DT pins on X1


def test_mm2_gauge_converted_to_awg():
    data = {
        "connectors": {"X1": {"connector_type": "molex_microfit_4"}, "X2": {"pincount": 4}},
        "cables": {"W1": {"wirecount": 4, "gauge": 0.25}},  # ~24 AWG
        "connections": [[{"X1": [1, 2, 3, 4]}, {"W1": [1, 2, 3, 4]}, {"X2": [1, 2, 3, 4]}]],
    }
    h = wireviz.parse(apply_connector_types(data), return_types="harness")
    x1 = [r for r in crimp_report(h) if r.connector == "X1"]
    assert x1[0].awg in (23, 24)  # 0.25 mm^2 ~ 23-24 AWG
    assert x1[0].tool == "638119200"  # Micro-Fit spec for 20-24


def test_register_custom_series():
    register_crimp("MYSER", [{"awg_min": 10, "awg_max": 12, "tool": "T", "die": "D", "height": 3}])
    assert crimp_for("MYSER", 11)["tool"] == "T"


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
    print(f"\n{passed}/{len(tests)} crimp tests passed")
    sys.exit(0 if passed == len(tests) else 1)
