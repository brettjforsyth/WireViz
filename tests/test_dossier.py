"""Tests for the harness dossier (wireviz.wv_dossier)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_dossier import render_dossier  # noqa: E402

YML = """
metadata:
  title: Test Harness
connectors:
  X1:
    pincount: 2
    accessories:
      - {type: backshell, qty: 1, mpn: BS-1}
  X2: {pincount: 2}
cables:
  W1: {wirecount: 2, gauge: 24 AWG, length: 1, colors: [RD, BK]}
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""


def h(yml=YML):
    return wireviz.parse(yml, return_types="harness")


def test_is_doctype_html():
    html = render_dossier(h())
    assert html.lstrip().lower().startswith("<!doctype html>")


def test_has_all_sections():
    html = render_dossier(h())
    for section in ("Diagram", "Wire cut sheet", "Bundles", "Accessories", "Assembly traveler"):
        assert section in html


def test_embeds_diagram_and_cutsheet():
    html = render_dossier(h())
    assert "<svg" in html  # the grid diagram
    assert "cutsheet" in html  # the cut-sheet table class
    assert "backshell" in html  # accessory shown
    assert "Cut W1" in html  # traveler step


def test_self_contained_no_external_loads():
    html = render_dossier(h())
    low = html.lower()
    for bad in ("<script src=", "<link ", "cdn.", "googleapis", 'src="//'):
        assert bad not in low


def test_uses_metadata_title():
    assert "Test Harness" in render_dossier(h())


def test_all_examples_produce_dossier():
    for subdir in ("examples", "tutorial"):
        for y in sorted((REPO_ROOT / subdir).glob("*.yml")):
            html = render_dossier(wireviz.parse(str(y), return_types="harness"))
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
    print(f"\n{passed}/{len(tests)} dossier tests passed")
    sys.exit(0 if passed == len(tests) else 1)
