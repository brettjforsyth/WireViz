"""Tests for per-connector pinout cards (wireviz.wv_pinout)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_pinout import pinout_tables, to_html  # noqa: E402

YML = """
connectors:
  X1:
    pincount: 3
    pinlabels: [SIG, GND, NC]
    type: Header
  X2: {pincount: 2}
cables:
  W1: {wirecount: 2}
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""


def h(yml=YML):
    return wireviz.parse(yml, return_types="harness")


def test_row_per_pin():
    tables = pinout_tables(h())
    assert len(tables["X1"]) == 3  # all pins, connected or not


def test_pin_shows_label_wire_and_destination():
    x1 = pinout_tables(h())["X1"]
    p1 = next(r for r in x1 if r["pin"] == 1)
    assert p1["label"] == "SIG"
    assert p1["wire"] == "W1:1"
    assert p1["to"] == "X2:1"


def test_unconnected_pin_is_blank():
    x1 = pinout_tables(h())["X1"]
    p3 = next(r for r in x1 if r["pin"] == 3)  # NC, unconnected
    assert p3["wire"] == "" and p3["to"] == ""


def test_html_has_a_card_per_connector():
    html = to_html(h())
    assert html.count('class="card"') == 2
    assert "Header" in html  # connector type shown
    assert "<!doctype html>" in html.lower()


def test_all_examples_render_cards():
    for subdir in ("examples", "tutorial"):
        for y in sorted((REPO_ROOT / subdir).glob("*.yml")):
            html = to_html(wireviz.parse(str(y), return_types="harness"))
            assert "class=\"cards\"" in html


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
    print(f"\n{passed}/{len(tests)} pinout tests passed")
    sys.exit(0 if passed == len(tests) else 1)
