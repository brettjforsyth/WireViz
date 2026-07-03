"""Integration tests for the wireviz CLI feature flags (no dot binary needed)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from click.testing import CliRunner  # noqa: E402

from wireviz.wv_cli import wireviz  # noqa: E402

DEMO = str(REPO_ROOT / "examples" / "demo01.yml")


def run(args):
    return CliRunner().invoke(wireviz, args)


def test_cli_grid_cutsheet_and_drc(tmp_path):
    result = run([DEMO, "-f", "", "--drc", "--grid", "--cutsheet", "tsv", "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "demo01.grid.svg").exists()
    assert (tmp_path / "demo01.cutsheet.tsv").exists()
    assert "DRC:" in result.output
    # the grid SVG is well-formed
    import xml.etree.ElementTree as ET

    ET.fromstring((tmp_path / "demo01.grid.svg").read_text())


def test_cli_cutsheet_csv(tmp_path):
    result = run([DEMO, "-f", "", "--no-drc", "--cutsheet", "csv", "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output
    text = (tmp_path / "demo01.cutsheet.csv").read_text()
    assert "Wire,From,To" in text


def test_cli_source_without_credentials_degrades(tmp_path, monkeypatch):
    monkeypatch.delenv("DIGIKEY_CLIENT_ID", raising=False)
    monkeypatch.delenv("DIGIKEY_CLIENT_SECRET", raising=False)
    result = run([DEMO, "-f", "", "--no-drc", "--source", "digikey", "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "demo01.sourced.csv").exists()
    assert "credentials not set" in result.output


def test_cli_strict_exits_nonzero_on_errors(tmp_path):
    bad = tmp_path / "bad.yml"
    bad.write_text(
        """
connectors:
  X1: {pincount: 1}
  X2: {pincount: 1}
cables:
  W1: {wirecount: 1}
connections:
  -
    - X1: [1]
    - W1: [5]
    - X2: [1]
"""
    )
    result = run([str(bad), "-f", "", "--drc", "--strict", "-o", str(tmp_path)])
    assert result.exit_code == 1
    assert "E-WIRE-RANGE" in result.output


def test_cli_no_features_still_runs(tmp_path):
    # with --no-drc and no feature flags and no graphviz formats, it should
    # still complete cleanly (nothing to do)
    result = run([DEMO, "-f", "", "--no-drc", "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output


if __name__ == "__main__":
    import tempfile
    import traceback

    tests = [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for name, t in tests:
        try:
            argcount = t.__code__.co_argcount
            names = t.__code__.co_varnames[:argcount]
            kwargs = {}
            if "tmp_path" in names:
                kwargs["tmp_path"] = Path(tempfile.mkdtemp())
            if "monkeypatch" in names:
                import os

                class _MP:
                    def delenv(self, k, raising=True):
                        os.environ.pop(k, None)

                kwargs["monkeypatch"] = _MP()
            t(**kwargs)
            passed += 1
            print(f"ok   {name}")
        except Exception:
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"\n{passed}/{len(tests)} cli tests passed")
    sys.exit(0 if passed == len(tests) else 1)
