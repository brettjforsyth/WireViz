"""Tests for the interactive HTML viewer (wireviz.wv_viewer)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_viewer import render_html  # noqa: E402

BASIC = """
metadata:
  title: My Test Harness
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


def harness_of(yml):
    return wireviz.parse(yml, return_types="harness")


def test_viewer_is_self_contained_html():
    html = render_html(harness_of(BASIC))
    assert html.lstrip().lower().startswith("<!doctype html>")
    low = html.lower()
    # no external resource loads (offline / CSP-safe). XML namespace URIs like
    # http://www.w3.org/... are declarations, not fetches, so they are fine.
    for bad in ("<script src=", "<link ", 'src="//', "@import", "cdn.", "googleapis"):
        assert bad not in low, f"external resource {bad!r} present"


def test_viewer_embeds_svg_and_data():
    html = render_html(harness_of(BASIC))
    assert 'id="harness-svg"' in html
    assert "const DATA =" in html
    assert "addEventListener" in html  # the pan/zoom script


def test_viewer_uses_metadata_title():
    html = render_html(harness_of(BASIC))
    assert "My Test Harness" in html


def test_viewer_wires_carry_identity():
    html = render_html(harness_of(BASIC))
    assert 'data-wire="W1:1"' in html


def test_all_examples_produce_viewers():
    for subdir in ("examples", "tutorial"):
        for y in sorted((REPO_ROOT / subdir).glob("*.yml")):
            h = wireviz.parse(str(y), return_types="harness")
            html = render_html(h)
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
    print(f"\n{passed}/{len(tests)} viewer tests passed")
    sys.exit(0 if passed == len(tests) else 1)
