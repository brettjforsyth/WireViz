"""Tests for the connector-type library and CAD asset resolution."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from wireviz import wireviz  # noqa: E402
from wireviz.wv_connectors import (  # noqa: E402
    apply_connector_types,
    get_connector,
    library_defaults,
    list_connectors,
    normalize_type,
    register_connector,
    resolve_connector_assets,
)


def test_normalize_type_variants():
    for raw in ("Deutsch DT-4", "deutsch_dt_4", "DEUTSCH DT 4", "deutsch.dt/4"):
        assert normalize_type(raw) == "deutsch_dt_4"


def test_library_lookup():
    assert "deutsch_dt_4" in dict(list_connectors())
    entry = get_connector("Deutsch DT 4")
    assert entry["pincount"] == 4
    assert entry["manufacturer"] == "TE Connectivity"


def test_library_defaults():
    d = library_defaults("molex_microfit_4")
    assert d["pincount"] == 4
    assert d["gender"] == "receptacle"


def test_apply_connector_types_backfills():
    data = {"connectors": {"X1": {"connector_type": "deutsch_dt_4"}}}
    out = apply_connector_types(data)
    assert out["connectors"]["X1"]["pincount"] == 4
    assert out["connectors"]["X1"]["manufacturer"] == "TE Connectivity"


def test_explicit_values_win():
    data = {"connectors": {"X1": {"connector_type": "deutsch_dt_4", "pincount": 2}}}
    out = apply_connector_types(data)
    assert out["connectors"]["X1"]["pincount"] == 2  # explicit not overwritten


def test_global_default_type_from_options():
    data = {
        "options": {"connector_type": "jst_ph_3"},
        "connectors": {"X1": {}},
    }
    out = apply_connector_types(data)
    assert out["connectors"]["X1"]["pincount"] == 3


def test_apply_does_not_mutate_input():
    data = {"connectors": {"X1": {"connector_type": "dsub_9"}}}
    apply_connector_types(data)
    assert "pincount" not in data["connectors"]["X1"]


def test_resolve_local_assets(tmp_path):
    (tmp_path / "deutsch_dt_4.png").write_bytes(b"fake")
    (tmp_path / "deutsch_dt_4.glb").write_bytes(b"fake")
    assets = resolve_connector_assets("Deutsch DT 4", cad_dir=str(tmp_path))
    assert assets.image_2d.endswith("deutsch_dt_4.png")
    assert assets.model_3d.endswith("deutsch_dt_4.glb")
    assert assets.source_2d == "local"
    assert assets.source_3d == "local"


def test_resolve_provider_fallback_for_image():
    calls = {}

    def provider(ctype, entry):
        calls["ctype"] = ctype
        return "https://example.com/photo.jpg"

    assets = resolve_connector_assets("deutsch_dt_4", image_provider=provider)
    assert assets.image_2d == "https://example.com/photo.jpg"
    assert assets.source_2d == "provider"
    assert calls["ctype"] == "deutsch_dt_4"


def test_resolve_none_type_returns_empty():
    assets = resolve_connector_assets(None)
    assert assets.image_2d is None and assets.model_3d is None


def test_register_and_parse_into_harness():
    register_connector("test_conn_2", description="unit test", pincount=2, gender="pin")
    data = {
        "connectors": {"X1": {"connector_type": "test_conn_2"}, "X2": {"pincount": 2}},
        "cables": {"W1": {"wirecount": 2}},
        "connections": [[{"X1": [1, 2]}, {"W1": [1, 2]}, {"X2": [1, 2]}]],
    }
    expanded = apply_connector_types(data)
    harness = wireviz.parse(expanded, return_types="harness")
    assert harness.connectors["X1"].pincount == 2
    assert harness.connectors["X1"].connector_type == "test_conn_2"


if __name__ == "__main__":
    import tempfile
    import traceback

    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for name, t in tests:
        try:
            names = t.__code__.co_varnames[: t.__code__.co_argcount]
            kwargs = {"tmp_path": Path(tempfile.mkdtemp())} if "tmp_path" in names else {}
            t(**kwargs)
            passed += 1
            print(f"ok   {name}")
        except Exception:
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} connector tests passed")
    sys.exit(0 if passed == len(tests) else 1)
