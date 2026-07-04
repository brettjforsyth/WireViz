"""Tests for the cost/quote rollup (wireviz.wv_quote)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_quote import QuoteConfig, crimp_count, quote, to_text  # noqa: E402

YML = """
connectors:
  X1: {pincount: 2}
  X2: {pincount: 2}
cables:
  W1: {wirecount: 2, length: 1}
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
"""


def h():
    return wireviz.parse(YML, return_types="harness")


def test_crimp_count():
    # 2 connections, each terminated at both ends -> 4 crimps
    assert crimp_count(h()) == 4


def test_quote_totals_with_prices():
    prices = {"W1": 0.50, "X1": 2.00, "X2": 3.00}  # W1 $/cable-m, connectors ea
    cfg = QuoteConfig(labor_per_crimp=0.10, labor_per_connector=1.00, markup=0.0)
    q = quote(h(), prices, cfg)
    # wire: 1 m of cable * 0.50 = 0.50 ; connectors 2+3 = 5.00 ; material = 5.50
    assert abs(q["material_cost"] - 5.50) < 1e-6
    # labor: 4 crimps * 0.10 + 2 connectors * 1.00 = 2.40
    assert abs(q["labor_cost"] - 2.40) < 1e-6
    assert abs(q["total"] - 7.90) < 1e-6  # markup 0


def test_markup_applied():
    cfg = QuoteConfig(markup=0.25)
    q = quote(h(), {"W1": 1.0, "X1": 1.0, "X2": 1.0}, cfg)
    assert abs(q["total"] - q["subtotal"] * 1.25) < 1e-6


def test_unpriced_tracked():
    q = quote(h(), {})  # no prices at all
    assert any("W1" in u for u in q["unpriced"])
    assert any("X1" in u for u in q["unpriced"])
    assert q["material_cost"] == 0.0
    assert q["labor_cost"] > 0  # labour still computed


def test_to_text_renders():
    q = quote(h(), {"W1": 1.0})
    t = to_text(q)
    assert "TOTAL" in t and "Labor" in t


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
    print(f"\n{passed}/{len(tests)} quote tests passed")
    sys.exit(0 if passed == len(tests) else 1)
