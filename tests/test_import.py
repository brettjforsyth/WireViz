"""Tests for the importers (wireviz.wv_import)."""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_import import from_kicad_netlist, from_wirelist  # noqa: E402


# --- CSV wire list ---------------------------------------------------------

WIRELIST = """from,from_pin,to,to_pin,color
X1,1,X2,1,RD
X1,2,X2,2,BK
X1,3,X3,1,GN
"""


def test_wirelist_builds_parseable_harness():
    data = from_wirelist(WIRELIST)
    h = wireviz.parse(data, return_types="harness")
    assert set(h.connectors) == {"X1", "X2", "X3"}
    assert h.connectors["X1"].pincount == 3  # max pin referenced


def test_wirelist_one_cable_per_pair():
    data = from_wirelist(WIRELIST)
    h = wireviz.parse(data, return_types="harness")
    # X1-X2 (2 wires) and X1-X3 (1 wire)
    assert "X1-X2" in h.cables and h.cables["X1-X2"].wirecount == 2
    assert "X1-X3" in h.cables and h.cables["X1-X3"].wirecount == 1


def test_wirelist_colors_carried():
    data = from_wirelist(WIRELIST)
    assert data["cables"]["X1-X2"]["colors"] == ["RD", "BK"]


def test_wirelist_header_aliases():
    csv = "source,from_pin,target,to_pin\nA,1,B,1\n"
    data = from_wirelist(csv)
    assert "A" in data["connectors"] and "B" in data["connectors"]


def test_wirelist_missing_columns_raises():
    with pytest.raises(ValueError):
        from_wirelist("foo,bar\n1,2\n")


def test_wirelist_wires_connect_correct_pins():
    data = from_wirelist(WIRELIST)
    h = wireviz.parse(data, return_types="harness")
    conns = h.cables["X1-X2"].connections
    # wire 1: X1:1 -> X2:1
    assert any(c.from_name == "X1" and c.to_name == "X2" for c in conns)


# --- KiCad netlist ---------------------------------------------------------

KICAD = """
(export (version D)
  (components
    (comp (ref J1) (value CONN))
    (comp (ref J2) (value CONN)))
  (nets
    (net (code 1) (name /VCC)
      (node (ref J1) (pin 1))
      (node (ref J2) (pin 1)))
    (net (code 2) (name /GND)
      (node (ref J1) (pin 2))
      (node (ref J2) (pin 2)))))
"""


def test_kicad_builds_parseable_harness():
    data = from_kicad_netlist(KICAD)
    h = wireviz.parse(data, return_types="harness")
    assert set(h.connectors) == {"J1", "J2"}
    assert h.connectors["J1"].pincount == 2


def test_kicad_nets_become_wires():
    data = from_kicad_netlist(KICAD)
    h = wireviz.parse(data, return_types="harness")
    cable = h.cables["J1-J2"]
    assert cable.wirecount == 2  # VCC and GND nets


def test_kicad_empty_is_safe():
    data = from_kicad_netlist("(export (version D))")
    assert data["connectors"] == {} and data["cables"] == {}


if __name__ == "__main__":
    import traceback

    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for name, t in tests:
        try:
            t()
            passed += 1
            print(f"ok   {name}")
        except Exception:
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} import tests passed")
    sys.exit(0 if passed == len(tests) else 1)
