"""Tests for inspection checklist + traceability (wireviz.wv_inspection)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_inspection import (  # noqa: E402
    inspection_checklist,
    to_csv,
    to_text,
    traceability_code,
)

YML = """
connectors:
  X1: {pincount: 2, gender: pin}
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


def test_checklist_has_expected_categories():
    cats = {c.category for c in inspection_checklist(h())}
    assert {"Connector", "Wire", "Crimp", "Electrical", "Marking"} <= cats


def test_checklist_covers_each_component():
    items = inspection_checklist(h())
    assert any("X1" in c.item for c in items)
    assert any("W1" in c.item and "crimp" in c.item.lower() for c in items)


def test_traceability_is_deterministic():
    assert traceability_code(h()) == traceability_code(h())
    assert len(traceability_code(h())) == 10
    assert traceability_code(h()).isalnum()


def test_traceability_changes_with_harness():
    modified = YML.replace("gauge: 24 AWG", "gauge: 22 AWG")
    assert traceability_code(h()) != traceability_code(h(modified))


def test_gender_check_included():
    assert any("gender" in c.item.lower() for c in inspection_checklist(h()))


def test_text_and_csv():
    code = traceability_code(h())
    t = to_text(h())
    assert code in t and "Continuity" in t
    csv = to_csv(h())
    assert "category,item,reference" in csv and code in csv


def test_all_examples_produce_checklists():
    for subdir in ("examples", "tutorial"):
        for y in sorted((REPO_ROOT / subdir).glob("*.yml")):
            harness = wireviz.parse(str(y), return_types="harness")
            assert inspection_checklist(harness)
            assert len(traceability_code(harness)) == 10


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
    print(f"\n{passed}/{len(tests)} inspection tests passed")
    sys.exit(0 if passed == len(tests) else 1)
