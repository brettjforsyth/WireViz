"""Tests for where-used cross-reference (wireviz.wv_whereused)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_whereused import cross_reference, part_index, where_used  # noqa: E402

YML = """
connectors:
  X1:
    pincount: 2
    mpn: CONN-A
    manufacturer: TE
    additional_components:
      - {type: Backshell, mpn: BS-9, qty: 1}
  X2: {pincount: 2, mpn: CONN-A, manufacturer: TE}
cables:
  W1: {wirecount: 2, mpn: CBL-1, manufacturer: Belden}
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""


def h(yml=YML):
    return wireviz.parse(yml, return_types="harness")


def test_where_used_finds_all_places():
    u = where_used(h(), "CONN-A")
    assert {x.designator for x in u} == {"X1", "X2"}
    assert len(u) == 2


def test_accessory_mpn_indexed():
    idx = part_index(h())
    assert "BS-9" in idx
    assert idx["BS-9"][0].kind == "accessory"
    assert idx["BS-9"][0].designator == "X1"


def test_cross_reference_totals():
    xref = cross_reference(h())
    conn_a = next(r for r in xref if r["mpn"] == "CONN-A")
    assert conn_a["total_qty"] == 2
    assert conn_a["used_by"] == ["X1", "X2"]
    assert conn_a["manufacturer"] == "TE"


def test_cable_mpn_indexed():
    assert where_used(h(), "CBL-1")[0].kind == "cable"


def test_missing_mpn_absent():
    assert where_used(h(), "DOES-NOT-EXIST") == []


def test_ignore_in_bom_excluded():
    yml = YML.replace("X2: {pincount: 2, mpn: CONN-A, manufacturer: TE}",
                      "X2: {pincount: 2, mpn: CONN-A, manufacturer: TE, ignore_in_bom: true}")
    u = where_used(h(yml), "CONN-A")
    assert {x.designator for x in u} == {"X1"}  # X2 excluded


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
    print(f"\n{passed}/{len(tests)} whereused tests passed")
    sys.exit(0 if passed == len(tests) else 1)
