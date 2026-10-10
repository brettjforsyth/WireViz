"""Tests for the vehicle view (wireviz.wv_carview) and connector faces (wv_faces)."""

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_carview import (  # noqa: E402
    TrunkNet,
    build_carview,
    carview_summary,
    load_layout,
    render_carview,
)
from wireviz.wv_faces import face_for  # noqa: E402


def harness_of(yml):
    return wireviz.parse(yml, return_types="harness")


HARNESS = """
connectors:
  A: {pincount: 2}
  B: {pincount: 2}
  C: {pincount: 3}
  Z: {pincount: 1}
cables:
  W1: {wirecount: 2, colors: [RD, BKWH], gauge: 0.5 mm2, length: 1}
  W2: {wirecount: 1, colors: [YE], gauge: 0.5 mm2, length: 1}
  W3: {wirecount: 1, colors: [GN], gauge: 0.5 mm2, length: 1}
connections:
  - [{A: [1, 2]}, {W1: [1, 2]}, {B: [1, 2]}]
  - [{A: [1]}, {W2: [1]}, {C: [3]}]
  - [{C: [1]}, {W3: [1]}, {Z: [1]}]
"""

# A trunk from x=0 to x=1000 along y=0, a branch down to (500, 400) that
# starts mid-segment (a T-junction), and a detour that is longer than going
# straight, so the router must pick the trunk.
LAYOUT = """
nodes:
  A: [0, 50]
  B: [1000, 50]
  C: [500, 450]
runs:
  - name: MAIN
    path: [[0, 0], [1000, 0]]
  - name: BRANCH
    path: [[500, 0], [500, 400]]
  - name: DETOUR
    path: [[0, 0], [0, -900], [1000, -900], [1000, 0]]
insets:
  - name: Middle
    box: [300, -100, 700, 500]
"""


def layout_file(tmp_path, text=LAYOUT):
    p = tmp_path / "layout.yml"
    p.write_text(text)
    return p


def view_of(tmp_path, text=LAYOUT):
    return build_carview(harness_of(HARNESS), load_layout(layout_file(tmp_path, text)))


def test_shared_waypoints_and_t_junction_join_the_network():
    net = TrunkNet([{"path": [[0, 0], [1000, 0]]}, {"path": [[500, 0], [500, 400]]}])
    # (500, 0) lies inside MAIN's only segment: it must split it
    assert len(net.pts) == 4
    s, t = net.vertex((0, 0)), net.vertex((500, 400))
    path = net.shortest(s, t)
    assert [net.pts[v] for v in path] == [(0.0, 0.0), (500.0, 0.0), (500.0, 400.0)]


def test_wires_follow_the_shortest_trunk_route(tmp_path):
    v = view_of(tmp_path)
    w = next(w for w in v["wires"] if w["cable"] == "W1")
    assert w["route"][0] == [0.0, 50.0] and w["route"][-1] == [1000.0, 50.0]
    # along y=0 (the trunk), never up the 900 mm detour
    assert all(p[1] >= 0 for p in w["route"])
    assert w["trunk"] is True
    assert w["len_mm"] == 50 + 1000 + 50


def test_branch_route_turns_at_the_t_junction(tmp_path):
    v = view_of(tmp_path)
    w = next(w for w in v["wires"] if w["cable"] == "W2")
    assert [500.0, 0.0] in w["route"] and w["route"][-1] == [500.0, 450.0]


def test_colours_and_stripes(tmp_path):
    v = view_of(tmp_path)
    cores = {w["core"]: w for w in v["wires"] if w["cable"] == "W1"}
    assert cores[1]["code"] == "RD" and len(cores[1]["colors"]) == 1
    assert cores[2]["code"] == "BKWH" and cores[2]["colors"][:2] == ["#000000", "#ffffff"]


def test_unplaced_connectors_are_listed_not_drawn(tmp_path):
    v = view_of(tmp_path)
    assert v["unplaced"] == ["Z"]
    w = next(w for w in v["wires"] if w["cable"] == "W3")
    assert w["route"] is None and w["id"] in v["unrouted"]
    assert v["nodes"]["Z"]["x"] is None


def test_layout_names_missing_from_the_model_are_reported(tmp_path):
    v = view_of(tmp_path, LAYOUT.replace("C: [500, 450]", "C: [500, 450]\n  GONE: [1, 1]"))
    assert v["stale"] == ["GONE"]
    assert "GONE" in carview_summary(v)


def test_bundle_is_thicker_where_more_wires_share_a_trunk(tmp_path):
    v = view_of(tmp_path)
    by_n = {t["n"]: t["d"] for t in v["trunks"] if t["n"]}
    # MAIN's left half carries W1 (2 wires) + W2 (1 wire); the right half only W1
    assert by_n[3] > by_n[2] > 0
    assert any(t["n"] == 0 for t in v["trunks"])  # the unused detour


def test_ends_with_no_trunk_between_them_are_drawn_straight(tmp_path):
    v = view_of(tmp_path, "nodes:\n  A: [0, 0]\n  B: [100, 0]\n  C: [50, 50]\nruns: []\n")
    w = next(w for w in v["wires"] if w["cable"] == "W1")
    assert w["trunk"] is False and w["route"] == [[0.0, 0.0], [100.0, 0.0]]


def test_one_ended_conductors_are_kept_but_not_routed(tmp_path):
    h = harness_of(HARNESS + "  - [{A: [2]}, {W2: [1]}]\n")
    v = build_carview(h, load_layout(layout_file(tmp_path)))
    assert v["one_ended"]


def test_backdrop_origin_aliases_and_relative_image(tmp_path):
    from PIL import Image

    (tmp_path / "pics").mkdir()
    Image.new("L", (200, 100), 255).save(tmp_path / "pics" / "car.png")
    text = LAYOUT + "backdrop:\n  image: pics/car.png\n  nose_px: 10\n  center_py: 50\n  mm_per_px: 2\n"
    v = view_of(tmp_path, text)
    bd = v["backdrop"]
    assert bd["href"].startswith("data:image/png;base64,")
    assert (bd["x"], bd["y"], bd["w"], bd["h"]) == (-20, -100, 400, 200)
    assert v["bounds"][0] <= -20 and v["bounds"][2] >= 1000


def test_page_embeds_parseable_data(tmp_path):
    html = render_carview(harness_of(HARNESS), layout_file(tmp_path), title="Test car")
    m = re.search(r'<script id="cv-data" type="application/json">(.*?)</script>', html, re.S)
    data = json.loads(m.group(1))
    assert data["title"] == "Test car"
    assert set(data["nodes"]) == {"A", "B", "C", "Z"}
    assert data["insets"] == [{"name": "Middle", "box": [300.0, -100.0, 700.0, 500.0]}]
    assert "<title>Test car</title>" in html


def test_cli_writes_the_page(tmp_path):
    from click.testing import CliRunner

    from wireviz.wv_cli import wireviz as cli

    yml = tmp_path / "h.yml"
    yml.write_text(HARNESS)
    res = CliRunner().invoke(
        cli, [str(yml), "-f", "s", "-o", str(tmp_path), "--carview", str(layout_file(tmp_path))])
    assert res.exit_code == 0, res.output
    assert (tmp_path / "h.carview.html").exists()
    assert "connectors placed" in res.output


def test_generic_faces_match_pin_count_and_say_so():
    h = harness_of(HARNESS)
    f = face_for(h.connectors["C"])
    assert [c["id"] for c in f["cavities"]] == [1, 2, 3]
    assert f["verified"] is False and "not the housing" in f["view"]
    assert face_for(h.connectors["Z"])["shape"] == "round"
    for c in f["cavities"]:
        assert 0 <= c["x"] <= 1 and 0 <= c["y"] <= 1


def test_verified_family_needs_matching_part_and_pin_count(monkeypatch):
    from wireviz import wv_faces

    monkeypatch.setitem(wv_faces.FAMILIES, "TEST-2", {
        "match": [(r"^TEST2", "main")], "shape": "rect", "aspect": 2.0, "source": "drawing X",
        "main": {"view": "wire side", "cavities": [(1, 0.25, 0.5, 16), (2, 0.75, 0.5, 16)]}})
    h = harness_of("connectors:\n  P: {pincount: 2, mpn: TEST2-S}\n  Q: {pincount: 3, mpn: TEST2-S}\n"
                   "cables:\n  W: {wirecount: 2}\n"
                   "connections:\n  - [{P: [1, 2]}, {W: [1, 2]}, {Q: [1, 2]}]\n")
    assert face_for(h.connectors["P"])["verified"] is True
    assert face_for(h.connectors["Q"])["verified"] is False  # pin count differs


def test_splices_are_placed_automatically_on_the_trunk(tmp_path):
    base = HARNESS.replace("  Z: {pincount: 1}", "  Z: {pincount: 1}\n  SP_X: {pincount: 1}")
    text = LAYOUT + "auto_place: ['SP_*']\n"
    # a two-way joint (B and C) sits halfway along the trunk route between them:
    # B joins at (1000, 0), C at (500, 400); the route is 900 mm, so 450 mm in
    two = base + "  - [{B: [1]}, {W3: [1]}, {SP_X: [1]}]\n  - [{SP_X: [1]}, {W2: [1]}, {C: [2]}]\n"
    v = build_carview(harness_of(two), load_layout(layout_file(tmp_path, text)))
    sp = v["nodes"]["SP_X"]
    assert sp["auto"] is True and (sp["x"], sp["y"]) == (550.0, 0.0)
    assert "automatically" in carview_summary(v)
    # a feed-and-branches splice (A, B, C) sits where the routes part: (500, 0)
    three = two + "  - [{A: [2]}, {W1: [1]}, {SP_X: [1]}]\n"
    v = build_carview(harness_of(three), load_layout(layout_file(tmp_path, text)))
    sp = v["nodes"]["SP_X"]
    assert (sp["x"], sp["y"]) == (500.0, 0.0)


def test_model_lengths_steer_where_a_splice_sits(tmp_path):
    # P-to-splice is 0.3 m and splice-to-Q 0.6 m in the model, so the joint
    # sits a third of the way along the 900 mm trunk route from P to Q
    yml = """
connectors:
  P: {pincount: 1}
  Q: {pincount: 1}
  SP_J: {pincount: 1}
cables:
  WA: {wirecount: 1, length: 0.3}
  WB: {wirecount: 1, length: 600, length_unit: mm}
connections:
  - [{P: [1]}, {WA: [1]}, {SP_J: [1]}]
  - [{SP_J: [1]}, {WB: [1]}, {Q: [1]}]
"""
    text = "nodes:\n  P: [0, 0]\n  Q: [900, 0]\nruns:\n  - path: [[0, 0], [900, 0]]\nauto_place: ['SP_*']\n"
    v = build_carview(harness_of(yml), load_layout(layout_file(tmp_path, text)))
    assert (v["nodes"]["SP_J"]["x"], v["nodes"]["SP_J"]["y"]) == (300.0, 0.0)


def test_page_carries_the_layout_source_for_export(tmp_path):
    text = ("# my car\n# second line\n\nnodes:\n  # ---- front\n  A: [0, 50]   # left lamp\n"
            "  B: [1000, 50]\n  C: [500, 450]\n  GONE: [9, 9]  # renamed\nruns:\n  # main\n"
            "  - {name: MAIN, path: [[0, 0], [1000, 0]]}\n  - {name: BRANCH, path: [[500, 0], [500, 400]]}\n")
    html = render_carview(harness_of(HARNESS), layout_file(tmp_path, text))
    data = json.loads(re.search(r'<script id="cv-data" type="application/json">(.*?)</script>', html, re.S).group(1))
    src = data["source"]
    assert src["header"] == ["# my car", "# second line"]
    assert src["file"] == "layout.yml" and src["order"] == ["nodes", "runs"]
    assert src["nodes"][0] == {"name": "A", "note": "left lamp", "pre": ["# ---- front"]}
    assert [n["name"] for n in src["nodes"]] == ["A", "B", "C", "GONE"]
    assert src["pos"]["GONE"] == [9, 9]
    assert src["runs_pre"] == {"0": ["# main"]} or src["runs_pre"] == {0: ["# main"]}
    assert 'id="editbtn"' in html and "function layoutYaml" in html


def _conn(yml, name):
    return harness_of(yml).connectors[name]


FACE_YML = """
connectors:
  P: {pincount: 4, mpn: DT06-4S-C015 / DT04-4P-C015}
  R: {pincount: 4, mpn: DT04-4P-C015 / DT06-4S-C015}
  T: {pincount: 3, mpn: DT06-3S-C015 / DT04-3P-C015}
  H: {pincount: 29, mpn: bulkhead plug}
cables:
  W: {wirecount: 3}
connections:
  - [{P: [1, 2, 3]}, {W: [1, 2, 3]}, {R: [1, 2, 3]}]
  - [{T: [1, 2, 3]}, {W: [1, 2, 3]}, {H: [1, 2, 3]}]
"""


def test_dt_faces_come_from_the_maker_drawing_and_pick_the_half_named_first():
    p = face_for(_conn(FACE_YML, "P"))
    assert p["verified"] and p["family"] == "DT-4" and "DT06-4S" in p["view"]
    pos = {c["id"]: (c["x"], c["y"]) for c in p["cavities"]}
    # TE DT06-4S wire side, latch up: 1 top-right, 2 bottom-right, 3 bottom-left, 4 top-left
    assert pos[1][0] > 0.5 > pos[4][0] and pos[1][1] < 0.5 < pos[2][1]
    r = face_for(_conn(FACE_YML, "R"))  # receptacle named first: the mirror image
    rpos = {c["id"]: (c["x"], c["y"]) for c in r["cavities"]}
    assert r["verified"] and rpos[1][0] < 0.5


def test_lettered_cavities_do_not_verify_numbered_pins():
    t = face_for(_conn(FACE_YML, "T"))
    assert t["verified"] is False and "A, B, C" in t["view"]


def test_layout_can_name_the_family_for_a_non_maker_part_number():
    h = _conn(FACE_YML, "H")
    assert face_for(h)["verified"] is False
    f = face_for(h, "HD30-24-29")
    assert f["verified"] and f["shape"] == "round" and len(f["cavities"]) == 29
    sizes = {c["id"]: c["size"] for c in f["cavities"]}
    assert [i for i in range(1, 30) if sizes[i] == 12] == [1, 2, 3, 4]
    mate = face_for(h, "HD30-24-29 mate")
    assert mate["verified"] and mate["view"] != f["view"]
