# -*- coding: utf-8 -*-
"""WireViz MCP server — build and verify wire harnesses from any agent.

Exposes the WireViz engine as Model Context Protocol tools so an agent can
design a harness (write YAML), validate it, run design-rule checks, compute the
BOM / cut sheet / netlist / weight, recommend a wire gauge, and render a diagram
— getting structured results back to iterate on.

Output location: tools return their result **inline** by default (SVG as text,
BOM/DRC/netlist as JSON), so the server is stateless and works even when the
agent has no shared filesystem. The render tools take an optional ``output_dir``
(or the ``WIREVIZ_MCP_OUTPUT_DIR`` environment variable); when set they also
write the file there and return its path.

Run it with ``python -m wireviz.wv_mcp`` (stdio transport) after installing the
optional dependency: ``pip install "wireviz[mcp]"``.

The tool functions below are plain and importable, so they can be unit-tested
without the MCP runtime; ``build_server`` registers them with FastMCP.
"""

import os
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import List, Optional

import wireviz.wireviz as wv
from wireviz.wv_bom import bom_list


def _default_output_dir() -> Optional[str]:
    return os.environ.get("WIREVIZ_MCP_OUTPUT_DIR")


def _harness(harness_yaml: str):
    """Parse YAML into a harness, applying device/connector/variant preprocessing."""
    import yaml as _yaml

    from wireviz.wv_connectors import apply_connector_types
    from wireviz.wv_devices import expand_devices
    from wireviz.wv_variants import apply_variant, list_variants

    data = _yaml.safe_load(harness_yaml)
    if isinstance(data, dict):
        if list_variants(data):
            data = apply_variant(data, None)  # strip variant tags, keep all
        data = apply_connector_types(expand_devices(data))
        return wv.parse(data, return_types="harness")
    return wv.parse(harness_yaml, return_types="harness")


def _clean(obj):
    """JSON-safe conversion of dataclasses / tuples for tool results."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return _clean(asdict(obj))
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items() if k != "key"}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, Path):
        return str(obj)
    return obj


# --- tools -----------------------------------------------------------------


def validate_harness(harness_yaml: str) -> dict:
    """Parse and validate a WireViz harness YAML.

    Returns a summary (connector/cable/wire counts and names) or a parse error.
    Call this first when authoring a harness.
    """
    try:
        h = _harness(harness_yaml)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    wires = sum(len(c.connections) for c in h.cables.values())
    return {
        "ok": True,
        "connectors": sorted(h.connectors),
        "cables": sorted(h.cables),
        "wire_segments": wires,
        "metadata": dict(h.metadata) if h.metadata else {},
    }


def run_drc(harness_yaml: str) -> dict:
    """Run design-rule checks (structural + electrical + mate) on a harness.

    Returns findings ranked by severity plus error/warning/info counts.
    """
    from wireviz.wv_drc import Severity, run_drc as _run

    try:
        findings = _run(_harness(harness_yaml))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    out = [
        {"severity": f.severity.name, "code": f.code, "component": f.component, "message": f.message}
        for f in findings
    ]
    return {
        "ok": True,
        "errors": sum(1 for f in findings if f.severity >= Severity.ERROR),
        "warnings": sum(1 for f in findings if f.severity == Severity.WARNING),
        "info": sum(1 for f in findings if f.severity == Severity.INFO),
        "findings": out,
    }


def generate_bom(harness_yaml: str) -> dict:
    """Return the bill of materials as a list of rows."""
    try:
        h = _harness(harness_yaml)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": True, "bom": _clean(h.bom())}


def generate_cutsheet(harness_yaml: str) -> dict:
    """Return the per-wire cut list (from/to, colour, gauge, length, ident)."""
    from wireviz.wv_cutsheet import build_cut_list, total_length_by_gauge

    try:
        h = _harness(harness_yaml)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    rows = build_cut_list(h)
    return {"ok": True, "cutsheet": _clean(rows), "bulk_length_by_gauge": total_length_by_gauge(rows)}


def generate_netlist(harness_yaml: str) -> dict:
    """Return the electrical nets (connected pin groups) of the harness."""
    from wireviz.wv_nets import compute_nets, floating_nodes

    try:
        h = _harness(harness_yaml)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    nets = compute_nets(h)
    return {
        "ok": True,
        "nets": [{"name": n.name, "pins": [f"{c}:{p}" for c, p in n.nodes]} for n in nets],
        "floating_pins": [f"{c}:{p}" for c, p in floating_nodes(nets)],
    }


def render_svg(harness_yaml: str) -> dict:
    """Render the harness to a native grid-snapped SVG (returned as text)."""
    from wireviz.wv_svg import render_svg as _render

    try:
        svg = _render(_harness(harness_yaml))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": True, "format": "svg", "content": svg}


def render_diagram(harness_yaml: str, fmt: str = "svg", output_dir: Optional[str] = None) -> dict:
    """Render the Graphviz harness diagram (needs the `dot` binary).

    fmt: 'svg' (returned inline), or 'png'/'html' (written to output_dir, which
    defaults to WIREVIZ_MCP_OUTPUT_DIR; a path is returned).
    """
    try:
        h = _harness(harness_yaml)
        if fmt == "svg":
            return {"ok": True, "format": "svg", "content": h.svg}
        outdir = output_dir or _default_output_dir()
        if not outdir:
            return {"ok": False, "error": f"fmt '{fmt}' needs output_dir or WIREVIZ_MCP_OUTPUT_DIR"}
        base = Path(outdir) / (h.metadata.get("title", "harness") if h.metadata else "harness")
        base.parent.mkdir(parents=True, exist_ok=True)
        h.output(filename=str(base), fmt=(fmt,), view=False)
        return {"ok": True, "format": fmt, "path": f"{base}.{fmt}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def recommend_gauge(current: float, length_m: float, max_drop_v: Optional[float] = None) -> dict:
    """Recommend the thinnest AWG for a current over a length within a drop budget."""
    from wireviz.wv_electrical import recommend_gauge as _rec

    return {"ok": True, **_rec(current, length_m, max_drop_v)}


def engineering_report(harness_yaml: str) -> dict:
    """Weight, conductor length, bundle diameter/sleeve, and power/voltage-drop."""
    from wireviz.wv_bundle import bundle_report
    from wireviz.wv_power import power_report
    from wireviz.wv_weight import weight_report

    try:
        h = _harness(harness_yaml)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {
        "ok": True,
        "weight": _clean(weight_report(h)),
        "bundles": _clean(bundle_report(h)),
        "power": _clean(power_report(h)),
    }


def list_connectors() -> dict:
    """List the built-in connector-type library (type -> description)."""
    from wireviz.wv_connectors import list_connectors as _lc

    return {"ok": True, "connectors": [{"type": t, "description": d} for t, d in _lc()]}


def list_devices() -> dict:
    """List the built-in device library (ECU/relay/sensor templates)."""
    from wireviz.wv_devices import list_devices as _ld

    return {"ok": True, "devices": [{"name": n, "description": d} for n, d in _ld()]}


def import_wirelist(csv_text: str) -> dict:
    """Convert a from/to wire-list CSV into WireViz harness YAML."""
    import yaml as _yaml

    from wireviz.wv_import import from_wirelist

    try:
        data = from_wirelist(csv_text)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": True, "harness_yaml": _yaml.safe_dump(data, sort_keys=False)}


def import_kicad(netlist_text: str) -> dict:
    """Convert a KiCad netlist into WireViz harness YAML."""
    import yaml as _yaml

    from wireviz.wv_import import from_kicad_netlist

    try:
        data = from_kicad_netlist(netlist_text)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    return {"ok": True, "harness_yaml": _yaml.safe_dump(data, sort_keys=False)}


def generate_formboard(harness_yaml: str, page: str = "A3", output_dir: Optional[str] = None) -> dict:
    """Render a 1:1 formboard SVG (returned inline, or written to output_dir)."""
    from wireviz.wv_formboard import FormboardConfig, build_formboard, page_grid, render_formboard

    try:
        h = _harness(harness_yaml)
        cfg = FormboardConfig(page=page)
        svg = render_formboard(h, cfg)
        grid = page_grid(build_formboard(h, cfg), cfg)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    outdir = output_dir or _default_output_dir()
    if outdir:
        p = Path(outdir) / "formboard.svg"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(svg)
        return {"ok": True, "path": str(p), "sheets": grid["total"]}
    return {"ok": True, "format": "svg", "content": svg, "sheets": grid["total"]}


TOOLS = [
    validate_harness,
    run_drc,
    generate_bom,
    generate_cutsheet,
    generate_netlist,
    render_svg,
    render_diagram,
    recommend_gauge,
    engineering_report,
    list_connectors,
    list_devices,
    import_wirelist,
    import_kicad,
    generate_formboard,
]


def build_server():
    """Create the FastMCP server with all tools registered."""
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("wireviz")
    for fn in TOOLS:
        mcp.tool()(fn)
    return mcp


def main():
    build_server().run()


if __name__ == "__main__":
    main()
