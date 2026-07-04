"""Tests for MIL-STD-681F wire ident bands (wireviz.wv_idents)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_cutsheet import build_cut_list, to_html, to_tsv  # noqa: E402
from wireviz.wv_idents import bands_html, ident_string, to_bands  # noqa: E402


def test_digit_to_band():
    bands = to_bands("245")
    assert [b["abbr"] for b in bands] == ["RD", "YE", "GN"]
    assert bands[0]["hex"] == "#ff0000"


def test_ident_string():
    assert ident_string(245) == "RD-YE-GN"
    assert ident_string("07") == "BK-VT"


def test_non_numeric_has_no_bands():
    assert to_bands("SIG") == []
    assert ident_string("SIG") == ""


def test_bands_html_swatches():
    html = bands_html("12")
    assert html.count("<span") >= 2  # one wrapper + one per band
    assert "#8b4513" in html and "#ff0000" in html  # brown, red


def test_all_ten_digits_map():
    for d in "0123456789":
        assert len(to_bands(d)) == 1


# --- cut-sheet integration -------------------------------------------------

CS = """
connectors:
  X1: {pincount: 3}
  X2: {pincount: 3}
cables:
  W1: {wirecount: 3, colors: [RD, GN, BU]}
connections:
  -
    - X1: [1, 2, 3]
    - W1: [1, 2, 3]
    - X2: [1, 2, 3]
"""


def test_cutsheet_has_ident_column():
    rows = build_cut_list(wireviz.parse(CS, return_types="harness"))
    tsv = to_tsv(rows)
    assert "Ident" in tsv.splitlines()[0]
    # wire 1 -> single band brown (1) -> "BN"
    assert any(r["ident"] == "BN" for r in rows)


def test_cutsheet_html_renders_bands():
    rows = build_cut_list(wireviz.parse(CS, return_types="harness"))
    html = to_html(rows)
    assert "ident-bands" in html  # visual swatches present


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
    print(f"\n{passed}/{len(tests)} ident tests passed")
    sys.exit(0 if passed == len(tests) else 1)
