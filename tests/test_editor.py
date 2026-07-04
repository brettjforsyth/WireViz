"""Tests for the drag-to-edit editor (wireviz.wv_editor)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_editor import editor_data, render_editor  # noqa: E402

YML = """
metadata:
  title: Edit Me
connectors:
  X1: {pincount: 2}
  X2: {pincount: 2}
cables:
  W1: {wirecount: 2, colors: [RD, BK]}
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""


def h(yml=YML):
    return wireviz.parse(yml, return_types="harness")


def test_nodes_have_geometry_and_pin_offsets():
    d = editor_data(h())
    x1 = d["nodes"]["X1"]
    assert {"x", "y", "w", "h", "pins"} <= set(x1)
    for p in x1["pins"]:
        assert "dy" in p and isinstance(p["dy"], int)


def test_wires_reference_endpoints_by_index():
    d = editor_data(h())
    assert d["wires"], "expected wire segments"
    for w in d["wires"]:
        a, b = w["a"], w["b"]
        assert a["node"] in d["nodes"] and b["node"] in d["nodes"]
        # pin index is valid for its node
        assert 0 <= a["pin"] < len(d["nodes"][a["node"]]["pins"])
        assert 0 <= b["pin"] < len(d["nodes"][b["node"]]["pins"])


def test_wire_count_matches_segments():
    d = editor_data(h())
    # 2 wires, each a from-seg (X1->W1) and to-seg (W1->X2) = 4 segments
    assert len(d["wires"]) == 4


def test_json_serialisable():
    import json

    json.dumps(editor_data(h()))  # must not raise


def test_render_is_self_contained_html():
    html = render_editor(h())
    assert html.lstrip().lower().startswith("<!doctype html>")
    low = html.lower()
    for bad in ("<script src=", "<link ", "cdn.", 'src="//'):
        assert bad not in low
    assert "const DATA =" in html
    assert "Edit Me" in html
    # the editor behaviours are present
    assert "pointerdown" in html  # dragging
    assert "Export layout" in html  # export button


def test_all_examples_produce_editor():
    for subdir in ("examples", "tutorial"):
        for y in sorted((REPO_ROOT / subdir).glob("*.yml")):
            html = render_editor(wireviz.parse(str(y), return_types="harness"))
            assert html.count("<!doctype html>") == 1


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
    print(f"\n{passed}/{len(tests)} editor tests passed")
    sys.exit(0 if passed == len(tests) else 1)
