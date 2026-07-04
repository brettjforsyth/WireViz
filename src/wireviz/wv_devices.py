# -*- coding: utf-8 -*-
"""Reusable device library for WireViz harnesses.

A *device* is a named, pre-configured multi-connector component — an ECU, a
relay, a sensor — that expands into one or more connectors with their pin
labels already filled in. Referencing a device in a harness saves re-typing a
connector definition and its cavity map every time, which is the single biggest
time-saver in dedicated harness tools.

Usage in a harness file:

    devices:
      ECU1: generic_ecu_26        # instance name : device type
      RLY1: {device: relay_iso_5} # long form, allows extra options

Each device instance expands into connectors named ``<instance>`` (single
connector) or ``<instance>_<port>`` (multi-connector), which can then be wired
in the ``connections`` section like any other connector. The ``_`` join keeps
the names clear of WireViz's ``.`` template separator.

The built-in library below deliberately contains only **generic** pinouts (no
proprietary manufacturer cavity maps); add your own with :func:`register_device`
or by extending :data:`DEVICE_LIBRARY`.
"""

import copy
from typing import Dict, List, Tuple

# name -> {"description": str, "connectors": {port: connector_attrs}}
DEVICE_LIBRARY: Dict[str, dict] = {
    "generic_ecu_26": {
        "description": "Generic 26-pin engine ECU (two connectors)",
        "connectors": {
            "A": {
                "type": "ECU",
                "subtype": "connector A",
                "pinlabels": [
                    "BATT+", "IGN", "GND", "GND", "INJ1", "INJ2", "INJ3",
                    "INJ4", "IGN1", "IGN2", "IGN3", "IGN4", "CANH", "CANL",
                ],
            },
            "B": {
                "type": "ECU",
                "subtype": "connector B",
                "pinlabels": [
                    "5V", "SENSOR_GND", "TPS", "MAP", "CLT", "IAT", "O2",
                    "CRANK", "CAM", "VSS", "TACH", "AUX1",
                ],
            },
        },
    },
    "relay_iso_5": {
        "description": "Generic ISO-280 automotive relay, 5 terminals",
        "connectors": {
            "": {  # single connector -> instance name only
                "type": "Relay",
                "subtype": "ISO 5-pin",
                "pins": [30, 85, 86, 87, "87a"],
                "pinlabels": ["COM", "COIL-", "COIL+", "NO", "NC"],
            },
        },
    },
    "sensor_3": {
        "description": "Generic 3-wire sensor (supply / signal / ground)",
        "connectors": {
            "": {
                "type": "Sensor",
                "subtype": "3-wire",
                "pinlabels": ["VCC", "SIG", "GND"],
            },
        },
    },
    "power_dist_6": {
        "description": "Generic 6-way fused power distribution block",
        "connectors": {
            "": {
                "type": "PDM",
                "subtype": "6-way",
                "pinlabels": ["IN", "F1", "F2", "F3", "F4", "F5"],
            },
        },
    },
}


def register_device(name: str, description: str, connectors: Dict[str, dict]) -> None:
    """Add or replace a device in the library."""
    DEVICE_LIBRARY[name] = {"description": description, "connectors": connectors}


def list_devices() -> List[Tuple[str, str]]:
    """Return [(name, description)] for every device, sorted by name."""
    return sorted((n, d["description"]) for n, d in DEVICE_LIBRARY.items())


def get_device(name: str) -> dict:
    if name not in DEVICE_LIBRARY:
        raise KeyError(
            f"unknown device '{name}'. Known devices: "
            + ", ".join(n for n, _ in list_devices())
        )
    return DEVICE_LIBRARY[name]


def _connector_name(instance: str, port: str, separator: str) -> str:
    return f"{instance}{separator}{port}" if port else instance


def expand_devices(data: dict, separator: str = "_") -> dict:
    """Return a copy of `data` with any ``devices`` section expanded.

    Each device instance becomes one or more entries in ``connectors``. The
    original dict is not mutated. A ``devices`` key is consumed (removed) from
    the result. Raises ``KeyError`` for an unknown device and ``ValueError`` on
    a connector-name collision with an existing connector.
    """
    if not isinstance(data, dict) or "devices" not in data:
        return data
    result = copy.deepcopy(data)
    devices = result.pop("devices") or {}
    connectors = result.setdefault("connectors", {})
    for instance, spec in devices.items():
        if isinstance(spec, str):
            device_name = spec
        elif isinstance(spec, dict) and "device" in spec:
            device_name = spec["device"]
        else:
            raise ValueError(
                f"device instance '{instance}' must be a device name or a "
                f"mapping with a 'device' key"
            )
        device = get_device(device_name)
        for port, attrs in device["connectors"].items():
            cname = _connector_name(instance, port, separator)
            if cname in connectors:
                raise ValueError(
                    f"device '{instance}' would create connector '{cname}', "
                    f"which already exists"
                )
            connectors[cname] = copy.deepcopy(attrs)
    return result
