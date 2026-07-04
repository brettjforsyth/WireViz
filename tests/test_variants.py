"""Tests for harness variants (wireviz.wv_variants)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import yaml  # noqa: E402

from wireviz import wireviz  # noqa: E402
from wireviz.wv_variants import apply_variant, list_variants  # noqa: E402

SRC_YAML = """
variants: [base, sport]
connectors:
  X1: {pincount: 4}
  X2: {pincount: 2}
  FOG: {pincount: 2, variants: [sport]}
cables:
  W1: {wirecount: 2}
  WF: {wirecount: 2, variants: [sport]}
connections:
  -
    - X1: [1, 2]
    - W1: [1, 2]
    - X2: [1, 2]
  -
    - X1: [3, 4]
    - WF: [1, 2]
    - FOG: [1, 2]
"""


def data():
    return yaml.safe_load(SRC_YAML)


def test_list_variants():
    assert list_variants(data()) == ["base", "sport"]


def test_base_drops_sport_components():
    d = apply_variant(data(), "base")
    assert "FOG" not in d["connectors"]
    assert "WF" not in d["cables"]
    # the connection set referencing WF/FOG is dropped
    assert len(d["connections"]) == 1


def test_sport_keeps_everything():
    d = apply_variant(data(), "sport")
    assert "FOG" in d["connectors"] and "WF" in d["cables"]
    assert len(d["connections"]) == 2


def test_variants_keys_stripped_and_parseable():
    d = apply_variant(data(), "base")
    assert "variants" not in d
    assert "variants" not in d["connectors"]["X1"]
    h = wireviz.parse(d, return_types="harness")  # must parse cleanly
    assert set(h.connectors) == {"X1", "X2"}


def test_no_variant_keeps_all():
    d = apply_variant(data(), None)
    assert "FOG" in d["connectors"] and len(d["connections"]) == 2
    assert "variants" not in d  # still stripped so it parses
    wireviz.parse(d, return_types="harness")


def test_sport_variant_parses_with_fog():
    h = wireviz.parse(apply_variant(data(), "sport"), return_types="harness")
    assert "FOG" in h.connectors


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
    print(f"\n{passed}/{len(tests)} variant tests passed")
    sys.exit(0 if passed == len(tests) else 1)
