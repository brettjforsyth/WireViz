"""Tests for net extraction and netlist export (wireviz.wv_nets)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_nets import (  # noqa: E402
    compute_nets,
    floating_nodes,
    to_csv,
    to_kicad_netlist,
    to_text,
)


def h(yml):
    return wireviz.parse(yml, return_types="harness")


def net_of(nets, node):
    for n in nets:
        if node in n.nodes:
            return n
    return None


def test_wire_joins_two_pins():
    nets = compute_nets(
        h(
            """
connectors:
  X1: {pincount: 2}
  X2: {pincount: 2}
cables:
  W1: {wirecount: 2}
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""
        )
    )
    n = net_of(nets, ("X1", 1))
    assert ("X2", 1) in n.nodes
    assert ("X1", 2) not in n.nodes  # different wire, different net


def test_splice_merges_into_one_net():
    # a 1-pin splice S joins wires from X1, X2, X3 into a single net
    nets = compute_nets(
        h(
            """
connectors:
  X1: {pincount: 1}
  X2: {pincount: 1}
  X3: {pincount: 1}
  S:  {style: simple, pincount: 1}
cables:
  W1: {wirecount: 1}
  W2: {wirecount: 1}
connections:
  -
    - X1: [1]
    - W1: [1]
    - S: [1]
  -
    - S: [1]
    - W2: [1]
    - X2: [1]
"""
        )
    )
    n = net_of(nets, ("X1", 1))
    assert ("X2", 1) in n.nodes  # X1 and X2 common through the splice


def test_mate_pin_joins_pins():
    nets = compute_nets(
        h(
            """
connectors:
  X1: {pincount: 1}
  X2: {pincount: 1}
cables: {}
connections:
  -
    - X1: [1]
    - ==>
    - X2: [1]
"""
        )
    )
    n = net_of(nets, ("X1", 1))
    assert ("X2", 1) in n.nodes


def test_floating_pin_detected():
    nets = compute_nets(
        h(
            """
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
        )
    )
    floats = floating_nodes(nets)
    # X1 pins 2 and 3 are unconnected
    assert ("X1", 2) in floats and ("X1", 3) in floats


def test_exports_do_not_crash():
    nets = compute_nets(
        h(
            """
connectors:
  X1: {pincount: 1}
  X2: {pincount: 1}
cables:
  W1: {wirecount: 1}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
"""
        )
    )
    assert "N001" in to_text(nets)
    assert "net,connector,pin" in to_csv(nets)
    assert "(export" in to_kicad_netlist(nets)


def test_all_examples_compute_nets():
    for subdir in ("examples", "tutorial"):
        for y in sorted((REPO_ROOT / subdir).glob("*.yml")):
            nets = compute_nets(wireviz.parse(str(y), return_types="harness"))
            # every node appears in exactly one net
            seen = set()
            for net in nets:
                for node in net.nodes:
                    assert node not in seen
                    seen.add(node)


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
    print(f"\n{passed}/{len(tests)} net tests passed")
    sys.exit(0 if passed == len(tests) else 1)
