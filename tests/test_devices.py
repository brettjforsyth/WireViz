"""Tests for the device library (wireviz.wv_devices)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402

from wireviz import wireviz  # noqa: E402
from wireviz.wv_devices import (  # noqa: E402
    expand_devices,
    get_device,
    list_devices,
    register_device,
)


def test_list_and_get_device():
    names = [n for n, _ in list_devices()]
    assert "relay_iso_5" in names
    assert get_device("relay_iso_5")["connectors"][""]["type"] == "Relay"


def test_unknown_device_raises():
    with pytest.raises(KeyError):
        get_device("no_such_device")


def test_expand_single_connector_device():
    data = {"devices": {"RLY1": "relay_iso_5"}}
    out = expand_devices(data)
    assert "devices" not in out
    assert "RLY1" in out["connectors"]
    assert out["connectors"]["RLY1"]["pinlabels"][0] == "COM"


def test_expand_multi_connector_device():
    data = {"devices": {"ECU1": "generic_ecu_26"}}
    out = expand_devices(data)
    # multi-connector device -> instance_port names (underscore avoids the
    # WireViz '.' template separator)
    assert "ECU1_A" in out["connectors"]
    assert "ECU1_B" in out["connectors"]


def test_expand_long_form():
    data = {"devices": {"S1": {"device": "sensor_3"}}}
    out = expand_devices(data)
    assert out["connectors"]["S1"]["pinlabels"] == ["VCC", "SIG", "GND"]


def test_expand_does_not_mutate_input():
    data = {"devices": {"RLY1": "relay_iso_5"}, "connectors": {}}
    expand_devices(data)
    assert "devices" in data  # original untouched


def test_collision_raises():
    data = {"devices": {"X1": "sensor_3"}, "connectors": {"X1": {"pincount": 1}}}
    with pytest.raises(ValueError):
        expand_devices(data)


def test_no_devices_section_is_passthrough():
    data = {"connectors": {"X1": {"pincount": 1}}}
    assert expand_devices(data) is data


def test_register_device_then_expand():
    register_device(
        "test_widget", "unit-test widget", {"": {"pinlabels": ["P1", "P2"]}}
    )
    out = expand_devices({"devices": {"WdgT": "test_widget"}})
    assert out["connectors"]["WdgT"]["pinlabels"] == ["P1", "P2"]


def test_expanded_device_parses_into_harness():
    data = {
        "devices": {"RLY1": "relay_iso_5", "S1": "sensor_3"},
        "cables": {"W1": {"wirecount": 1}},
        "connections": [
            [
                {"RLY1": ["COIL+"]},
                {"W1": [1]},
                {"S1": ["VCC"]},
            ]
        ],
    }
    expanded = expand_devices(data)
    harness = wireviz.parse(expanded, return_types="harness")
    assert "RLY1" in harness.connectors
    assert "S1" in harness.connectors
    # the relay connector kept its labelled pins
    assert "COM" in harness.connectors["RLY1"].pinlabels


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
    print(f"\n{passed}/{len(tests)} device tests passed")
    sys.exit(0 if passed == len(tests) else 1)
