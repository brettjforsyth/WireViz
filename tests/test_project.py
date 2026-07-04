"""Tests for project BOM consolidation (wireviz.wv_project)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_project import consolidate_bom, to_tsv  # noqa: E402

HARNESS = """
connectors:
  X1: {pincount: 1, type: Widget, mpn: CONN-A, manufacturer: TE}
  X2: {pincount: 1, type: Widget, mpn: CONN-A, manufacturer: TE}
cables:
  W1: {wirecount: 1, gauge: 24 AWG, length: 1, mpn: CBL-1}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
"""


def harness():
    return wireviz.parse(HARNESS, return_types="harness")


def test_quantities_summed_across_harnesses():
    rows = consolidate_bom({"H1": harness(), "H2": harness()})
    conn = next(r for r in rows if r["mpn"] == "CONN-A")
    # 2 connectors per harness x 2 harnesses = 4
    assert conn["qty"] == 4
    assert conn["harnesses"] == ["H1", "H2"]


def test_cable_length_summed():
    rows = consolidate_bom({"H1": harness(), "H2": harness()})
    cbl = next(r for r in rows if r["mpn"] == "CBL-1")
    assert cbl["qty"] == 2  # 1 m + 1 m
    assert cbl["unit"] == "m"


def test_designators_namespaced_by_harness():
    rows = consolidate_bom({"HA": harness()})
    conn = next(r for r in rows if r["mpn"] == "CONN-A")
    assert all(d.startswith("HA/") for d in conn["designators"])


def test_single_harness_is_its_own_bom():
    rows = consolidate_bom({"H1": harness()})
    assert any(r["mpn"] == "CONN-A" and r["qty"] == 2 for r in rows)


def test_tsv_renders():
    t = to_tsv(consolidate_bom({"H1": harness(), "H2": harness()}))
    assert "Description\tMpn" in t
    assert "CONN-A" in t


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
    print(f"\n{passed}/{len(tests)} project tests passed")
    sys.exit(0 if passed == len(tests) else 1)
