"""Tests for the accessory / covering data model (wireviz.wv_accessories)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_accessories import (  # noqa: E402
    accessory_bom,
    derive_accessories,
    to_tsv,
)

YML = """
connectors:
  X1:
    pincount: 4
    accessories:
      - {type: contact, mpn: C-16}
      - {type: seal, per: pin}
      - {type: backshell, qty: 1, mpn: BS-1}
  X2:
    pincount: 4
    accessories:
      - {type: contact, mpn: C-16}
cables:
  W1:
    wirecount: 4
    length: 2
    accessories:
      - {type: braided_sleeve, mpn: PT2}
connections:
  -
    - X1: [1, 2, 3, 4]
    - W1: [1, 2, 3, 4]
    - X2: [1, 2, 3, 4]
"""


def h(yml=YML):
    return wireviz.parse(yml, return_types="harness")


def line(lines, host, type_):
    return next(l for l in lines if l.host == host and l.type == type_)


def test_contact_per_pin():
    lines = derive_accessories(h())
    assert line(lines, "X1", "contact").qty == 4  # one per pin


def test_seal_default_per_pin():
    lines = derive_accessories(h())
    assert line(lines, "X1", "seal").qty == 4


def test_backshell_explicit_qty():
    lines = derive_accessories(h())
    bs = line(lines, "X1", "backshell")
    assert bs.qty == 1 and bs.category == "accessory"


def test_covering_per_length():
    lines = derive_accessories(h())
    sleeve = line(lines, "W1", "braided_sleeve")
    assert sleeve.qty == 2  # cable length
    assert sleeve.category == "covering"
    assert sleeve.unit == "m"


def test_bom_groups_by_mpn():
    bom = accessory_bom(h())
    # C-16 contacts: 4 on X1 + 4 on X2 = 8
    c16 = next(g for g in bom if g["mpn"] == "C-16")
    assert c16["qty"] == 8
    assert set(c16["hosts"]) == {"X1", "X2"}


def test_multiplier():
    yml = """
connectors:
  X1: {pincount: 2}
  X2: {pincount: 2}
cables:
  W1:
    wirecount: 2
    length: 3
    accessories:
      - {type: heatshrink, per: connector, qty: 2}
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""
    lines = derive_accessories(h(yml))
    assert line(lines, "W1", "heatshrink").qty == 2


def test_cable_discrete_accessory_is_each_not_length():
    # regression: a non-covering accessory on a cable must be 'ea', not 'm'
    yml = """
connectors: {X1: {pincount: 1}, X2: {pincount: 1}}
cables:
  W1:
    wirecount: 1
    length: 2
    accessories:
      - {type: backshell, per: connector, qty: 1, mpn: BS}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
"""
    bs = line(derive_accessories(h(yml)), "W1", "backshell")
    assert bs.unit == "ea" and bs.category == "accessory"


def test_tsv_renders():
    t = to_tsv(accessory_bom(h()))
    assert "Category\tType" in t
    assert "braided_sleeve" in t


def test_no_accessories_is_empty():
    yml = """
connectors: {X1: {pincount: 1}, X2: {pincount: 1}}
cables: {W1: {wirecount: 1}}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
"""
    assert derive_accessories(h(yml)) == []


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
    print(f"\n{passed}/{len(tests)} accessory tests passed")
    sys.exit(0 if passed == len(tests) else 1)
