"""Tests for the wire cut-sheet generator (wireviz.wv_cutsheet)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_cutsheet import (  # noqa: E402
    CutSheetOptions,
    build_cut_list,
    compute_length,
    to_csv,
    to_tsv,
    total_length_by_gauge,
)


def harness_of(yml):
    return wireviz.parse(yml, return_types="harness")


BASIC = """
connectors:
  X1:
    pincount: 2
    pinlabels: [SIG, GND]
  X2:
    pincount: 2
cables:
  W1:
    wirecount: 2
    gauge: 24 AWG
    length: 2
    colors: [RD, BK]
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""


def test_row_per_wire():
    rows = build_cut_list(harness_of(BASIC))
    assert len(rows) == 2
    wires = [r["wire"] for r in rows]
    assert wires == ["W1:1", "W1:2"]


def test_endpoints_and_labels():
    rows = build_cut_list(harness_of(BASIC))
    first = rows[0]
    # from X1 pin 1 which has pinlabel SIG
    assert first["from"] == "X1:1 (SIG)"
    assert first["to"] == "X2:1"
    assert first["color"] == "RD"
    assert first["gauge"] == "24 AWG"
    assert first["length"] == 2
    assert first["unit"] == "m"


def test_default_length_equals_cable_length():
    rows = build_cut_list(harness_of(BASIC))
    assert all(r["length"] == 2 for r in rows)


def test_allowances_and_rounding():
    class Cable:
        length = 2.0
    opts = CutSheetOptions(
        insertion_allowance=0.05,
        slack=0.1,
        round_increment=0.25,
        round_mode="up",
    )
    # 2 + 0.05*2 + 0.1 = 2.2 -> round up to 0.25 increment -> 2.25
    assert compute_length(Cable(), 2, opts) == 2.25


def test_round_modes():
    class Cable:
        length = 2.1
    up = compute_length(Cable(), 0, CutSheetOptions(round_increment=1, round_mode="up"))
    down = compute_length(Cable(), 0, CutSheetOptions(round_increment=1, round_mode="down"))
    near = compute_length(Cable(), 0, CutSheetOptions(round_increment=1, round_mode="nearest"))
    assert (up, down, near) == (3, 2, 2)


def test_twist_factor():
    class Cable:
        length = 1.0
    v = compute_length(Cable(), 0, CutSheetOptions(twist_factor=0.2))
    assert abs(v - 1.2) < 1e-9


def test_min_length_floor():
    class Cable:
        length = 0.1
    v = compute_length(Cable(), 0, CutSheetOptions(min_length=0.5))
    assert v == 0.5


def test_shield_row_present_and_last():
    yml = """
connectors:
  X1: {pincount: 1}
  X2: {pincount: 1}
cables:
  W1: {wirecount: 1, shield: true, length: 1}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
  -
    - X1: [1]
    - W1: [s]
    - X2: [1]
"""
    rows = build_cut_list(harness_of(yml))
    assert rows[-1]["wire"] == "W1:s"
    assert rows[-1]["color"] == "shield"


def test_total_length_by_gauge():
    rows = build_cut_list(harness_of(BASIC))
    totals = total_length_by_gauge(rows)
    # two 24 AWG wires of length 2 -> 4
    assert any(v == 4 for v in totals.values())


def test_formatters_roundtrip():
    rows = build_cut_list(harness_of(BASIC))
    tsv = to_tsv(rows)
    csv = to_csv(rows)
    assert "Wire\tFrom\tTo" in tsv
    assert "W1:1" in tsv and "W1:1" in csv
    assert tsv.count("\n") == len(rows) + 1  # header + rows (+trailing)


TWISTED = """
connectors:
  X1: {pincount: 3}
  X2: {pincount: 3}
cables:
  W1:
    wirecount: 3
    length: 1
    colors: [WH, BU, BK]
    twisting: [[1, 2]]
connections:
  -
    - X1: [1, 2, 3]
    - W1: [1, 2, 3]
    - X2: [1, 2, 3]
"""


def test_twist_column_shows_partners():
    rows = build_cut_list(harness_of(TWISTED))
    w1 = next(r for r in rows if r["wire"] == "W1:1")
    w2 = next(r for r in rows if r["wire"] == "W1:2")
    w3 = next(r for r in rows if r["wire"] == "W1:3")
    assert w1["twist"] == "2" and w2["twist"] == "1"
    assert w3["twist"] == ""  # not twisted


def test_twist_factor_only_on_twisted_wires():
    opts = CutSheetOptions(twist_factor=0.2)
    rows = build_cut_list(harness_of(TWISTED), opts)
    w1 = next(r for r in rows if r["wire"] == "W1:1")
    w3 = next(r for r in rows if r["wire"] == "W1:3")
    assert abs(w1["length"] - 1.2) < 1e-9  # twisted -> +20%
    assert w3["length"] == 1  # untwisted -> unchanged


def test_examples_produce_cut_lists():
    # every example with connections should yield a cut list without crashing
    for subdir in ("examples", "tutorial"):
        for y in sorted((REPO_ROOT / subdir).glob("*.yml")):
            h = wireviz.parse(str(y), return_types="harness")
            rows = build_cut_list(h)
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
    print(f"\n{passed}/{len(tests)} cut-sheet tests passed")
    sys.exit(0 if passed == len(tests) else 1)
