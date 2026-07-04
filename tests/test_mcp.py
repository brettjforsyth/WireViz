"""Tests for the WireViz MCP tool layer (wireviz.wv_mcp)."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wv_mcp  # noqa: E402

HARNESS = """
metadata:
  title: MCP Test
connectors:
  X1: {pincount: 2}
  X2: {pincount: 2}
cables:
  W1: {wirecount: 2, gauge: 24 AWG, length: 1, colors: [RD, BK]}
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""


def test_validate_ok():
    r = wv_mcp.validate_harness(HARNESS)
    assert r["ok"] and set(r["connectors"]) == {"X1", "X2"}
    assert r["cables"] == ["W1"] and r["wire_segments"] == 2


def test_validate_reports_error():
    r = wv_mcp.validate_harness("connectors: [not, a, dict]\n")
    assert r["ok"] is False and "error" in r


def test_run_drc():
    r = wv_mcp.run_drc(HARNESS)
    assert r["ok"] and "findings" in r
    assert r["errors"] == 0


def test_generate_bom():
    r = wv_mcp.generate_bom(HARNESS)
    assert r["ok"] and isinstance(r["bom"], list) and r["bom"]


def test_generate_cutsheet():
    r = wv_mcp.generate_cutsheet(HARNESS)
    assert r["ok"] and len(r["cutsheet"]) == 2
    assert "bulk_length_by_gauge" in r


def test_generate_netlist():
    r = wv_mcp.generate_netlist(HARNESS)
    assert r["ok"] and len(r["nets"]) == 2


def test_render_svg_inline():
    r = wv_mcp.render_svg(HARNESS)
    assert r["ok"] and r["format"] == "svg"
    assert r["content"].lstrip().startswith("<svg")


def test_recommend_gauge():
    r = wv_mcp.recommend_gauge(30, 1.0)
    assert r["ok"] and r["awg"] == 14


def test_engineering_report():
    r = wv_mcp.engineering_report(HARNESS)
    assert r["ok"] and "weight" in r and "bundles" in r and "power" in r


def test_list_libraries():
    assert any(c["type"] == "deutsch_dt_4" for c in wv_mcp.list_connectors()["connectors"])
    assert any(d["name"] == "relay_iso_5" for d in wv_mcp.list_devices()["devices"])


def test_import_wirelist_roundtrips():
    r = wv_mcp.import_wirelist("from,from_pin,to,to_pin\nA,1,B,1\nA,2,B,2\n")
    assert r["ok"]
    # the produced YAML validates
    v = wv_mcp.validate_harness(r["harness_yaml"])
    assert v["ok"] and set(v["connectors"]) == {"A", "B"}


def test_formboard_inline():
    r = wv_mcp.generate_formboard(HARNESS)
    assert r["ok"] and r["content"].lstrip().startswith("<svg")
    assert r["sheets"] >= 1


def test_formboard_writes_file(tmp_path):
    r = wv_mcp.generate_formboard(HARNESS, output_dir=str(tmp_path))
    assert r["ok"] and Path(r["path"]).exists()


def test_all_results_json_serialisable():
    for r in (
        wv_mcp.validate_harness(HARNESS),
        wv_mcp.run_drc(HARNESS),
        wv_mcp.generate_bom(HARNESS),
        wv_mcp.generate_cutsheet(HARNESS),
        wv_mcp.generate_netlist(HARNESS),
        wv_mcp.render_svg(HARNESS),
        wv_mcp.recommend_gauge(10, 2.0, 0.5),
        wv_mcp.engineering_report(HARNESS),
        wv_mcp.list_connectors(),
        wv_mcp.list_devices(),
    ):
        json.dumps(r)  # must not raise


def test_server_builds_with_all_tools():
    try:
        server = wv_mcp.build_server()
    except ImportError:
        import pytest

        pytest.skip("mcp SDK not installed")
    assert server is not None
    assert len(wv_mcp.TOOLS) == 14


if __name__ == "__main__":
    import tempfile
    import traceback

    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for name, t in tests:
        try:
            kw = {"tmp_path": Path(tempfile.mkdtemp())} if "tmp_path" in t.__code__.co_varnames[: t.__code__.co_argcount] else {}
            t(**kw)
            passed += 1
            print(f"ok   {name}")
        except Exception:
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} mcp tests passed")
    sys.exit(0 if passed == len(tests) else 1)
