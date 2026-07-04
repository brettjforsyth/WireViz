"""Tests for wire-processing machine export (wireviz.wv_machine)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_machine import MachineOptions, machine_joblist, to_csv  # noqa: E402

YML = """
connectors:
  X1: {pincount: 2}
  X2: {pincount: 2}
cables:
  W1: {wirecount: 2, gauge: 24 AWG, length: 0.2, colors: [RD, BK]}
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""


def h(yml=YML):
    return wireviz.parse(yml, return_types="harness")


def test_length_converted_to_mm():
    rows = machine_joblist(h())
    assert rows[0]["length_mm"] == 200.0  # 0.2 m -> 200 mm


def test_article_is_gauge_and_color():
    rows = machine_joblist(h())
    assert rows[0]["article"] == "24 AWG RD"


def test_strip_lengths_from_options():
    rows = machine_joblist(h(), machine=MachineOptions(strip_left_mm=8, strip_right_mm=6))
    assert rows[0]["strip_left_mm"] == 8 and rows[0]["strip_right_mm"] == 6


def test_one_row_per_wire():
    rows = machine_joblist(h())
    assert len(rows) == 2
    assert [r["seq"] for r in rows] == [1, 2]


def test_csv_export():
    csv = to_csv(machine_joblist(h()))
    assert "seq,article,gauge" in csv
    assert "200.0" in csv


def test_all_examples_export():
    for subdir in ("examples", "tutorial"):
        for y in sorted((REPO_ROOT / subdir).glob("*.yml")):
            rows = machine_joblist(wireviz.parse(str(y), return_types="harness"))
            assert isinstance(rows, list)


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
    print(f"\n{passed}/{len(tests)} machine tests passed")
    sys.exit(0 if passed == len(tests) else 1)
