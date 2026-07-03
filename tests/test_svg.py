"""Tests for the native grid-snapped SVG renderer (wireviz.wv_svg)."""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_svg import GridConfig, build_layout, render_svg  # noqa: E402

BASIC = """
connectors:
  X1: {pincount: 2}
  X2: {pincount: 2}
cables:
  W1:
    wirecount: 2
    colors: [RD, BK]
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""


def harness_of(yml):
    return wireviz.parse(yml, return_types="harness")


def test_output_is_valid_svg():
    svg = render_svg(harness_of(BASIC))
    root = ET.fromstring(svg)
    assert root.tag.endswith("svg")


def test_layering_left_to_right():
    lay = build_layout(harness_of(BASIC))
    cols = {n: lay["nodes"][n]["column"] for n in lay["nodes"]}
    assert cols["X1"] < cols["W1"] < cols["X2"]


def test_all_coordinates_snap_to_grid():
    cfg = GridConfig(pitch=10)
    lay = build_layout(harness_of(BASIC), cfg)
    for node in lay["nodes"].values():
        for key in ("x", "y", "w", "h"):
            assert node[key] % cfg.pitch == 0
        for pin in node["pins"]:
            assert pin["y"] % cfg.pitch == 0
    for wire in lay["wires"]:
        for x, y in wire["points"]:
            assert x % cfg.pitch == 0 and y % cfg.pitch == 0


def test_wires_are_orthogonal():
    lay = build_layout(harness_of(BASIC))
    assert lay["wires"], "expected some routed wires"
    for wire in lay["wires"]:
        pts = wire["points"]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            assert x1 == x2 or y1 == y2, "segment is neither horizontal nor vertical"


def test_grid_pitch_changes_geometry():
    small = build_layout(harness_of(BASIC), GridConfig(pitch=10))
    big = build_layout(harness_of(BASIC), GridConfig(pitch=25, pin_pitch=50))
    assert big["height"] != small["height"]
    for wire in big["wires"]:
        for x, y in wire["points"]:
            assert x % 25 == 0 and y % 25 == 0


def test_wire_colors_resolved_to_hex():
    lay = build_layout(harness_of(BASIC))
    colors = {w["color"] for w in lay["wires"]}
    # RD -> #ff0000, BK -> #000000 (at least one recognisable hex present)
    assert any(c.startswith("#") for c in colors)
    assert "#ff0000" in colors


def test_shield_row_rendered():
    yml = """
connectors:
  X1: {pincount: 1}
  X2: {pincount: 1}
cables:
  W1: {wirecount: 1, shield: true}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
"""
    lay = build_layout(harness_of(yml))
    cable = lay["nodes"]["W1"]
    assert any(p["id"] == "s" for p in cable["pins"])


def test_all_examples_render():
    for subdir in ("examples", "tutorial"):
        for y in sorted((REPO_ROOT / subdir).glob("*.yml")):
            h = wireviz.parse(str(y), return_types="harness")
            svg = render_svg(h)
            ET.fromstring(svg)  # must be well-formed XML


def test_layout_dict_is_json_serializable():
    import json

    lay = build_layout(harness_of(BASIC))
    json.dumps(lay)  # must not raise


IMAGED = """
connectors:
  X1:
    pincount: 1
    image:
      src: resources/does-not-need-to-exist.png
  X2: {pincount: 1}
cables:
  W1: {wirecount: 1}
connections:
  -
    - X1: [1]
    - W1: [1]
    - X2: [1]
"""


def test_connector_image_rendered():
    svg = render_svg(harness_of(IMAGED))
    assert "<image " in svg
    ET.fromstring(svg)  # still valid XML with the image element


def test_image_metadata_in_layout():
    lay = build_layout(harness_of(IMAGED))
    assert "image" in lay["nodes"]["X1"]
    assert lay["nodes"]["X1"]["image"]["src"].endswith(".png")
    # a node with an image is taller than one without
    assert lay["nodes"]["X1"]["h"] > lay["nodes"]["X2"]["h"]


def test_export_json_is_valid():
    import json

    from wireviz.wv_svg import export_json

    data = json.loads(export_json(harness_of(IMAGED)))
    assert data["metadata"]["connectors"] == 2
    assert "nodes" in data and "wires" in data
    # image src is a plain string, not a Path
    assert isinstance(data["nodes"]["X1"]["image"]["src"], str)


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
    print(f"\n{passed}/{len(tests)} svg tests passed")
    sys.exit(0 if passed == len(tests) else 1)
