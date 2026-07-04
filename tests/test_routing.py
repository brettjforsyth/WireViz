"""Tests for branch-segment routed length (wireviz.wv_routing)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_routing import (  # noqa: E402
    apply_routed_lengths,
    missing_segments,
    routed_length,
    routed_lengths,
    unused_segments,
)

YML = """
connectors:
  A: {pincount: 1}
  B: {pincount: 1}
  C: {pincount: 1}
cables:
  W1: {wirecount: 1, length: 0.5}
  W2: {wirecount: 1, length: 0.5}
connections:
  -
    - A: [1]
    - W1: [1]
    - B: [1]
  -
    - A: [1]
    - W2: [1]
    - C: [1]
"""

ROUTING = {
    "segments": {"trunk": 1.2, "branch_a": 0.4, "branch_b": 0.8},
    "cables": {"W1": ["trunk", "branch_a"], "W2": ["trunk", "branch_b"]},
}


def h():
    return wireviz.parse(YML, return_types="harness")


def test_routed_length_sums_path():
    assert routed_length(["trunk", "branch_a"], ROUTING["segments"]) == 1.6


def test_routed_lengths_per_cable():
    r = routed_lengths(h(), ROUTING)
    assert r["W1"] == 1.6 and r["W2"] == 2.0


def test_unrouted_cable_keeps_own_length():
    routing = {"segments": {"trunk": 1.0}, "cables": {"W1": ["trunk"]}}
    r = routed_lengths(h(), routing)
    assert r["W1"] == 1.0
    assert r["W2"] == 0.5  # not routed -> own declared length


def test_apply_sets_cable_length():
    harness = h()
    apply_routed_lengths(harness, ROUTING)
    assert harness.cables["W1"].length == 1.6
    assert harness.cables["W2"].length == 2.0


def test_unused_and_missing_segments():
    routing = {
        "segments": {"trunk": 1.0, "spare": 0.3},
        "cables": {"W1": ["trunk", "branch_x"]},
    }
    assert unused_segments(routing) == ["spare"]
    assert missing_segments(routing) == ["branch_x"]


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
    print(f"\n{passed}/{len(tests)} routing tests passed")
    sys.exit(0 if passed == len(tests) else 1)
