# -*- coding: utf-8 -*-

import os
import sys
from pathlib import Path

import click
import yaml

if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import wireviz.wireviz as wv
from wireviz import APP_NAME, __version__
from wireviz.wv_helper import file_read_text
from wireviz.wv_accessories import accessory_bom, to_tsv as accessories_tsv
from wireviz.wv_assembly import build_traveler, to_text as traveler_text
from wireviz.wv_bundle import bundle_report
from wireviz.wv_connectors import apply_connector_types, list_connectors
from wireviz.wv_diff import diff_harnesses, to_text as diff_text
from wireviz.wv_dossier import render_dossier
from wireviz.wv_editor import render_editor
from wireviz.wv_dxf import formboard_to_dxf
from wireviz.wv_markers import build_markers, to_csv as markers_csv, to_svg_sheet
from wireviz.wv_nets import compute_nets, to_text as nets_text
from wireviz.wv_pinout import to_html as pinout_html
from wireviz.wv_weight import weight_report
from wireviz.wv_cutsheet import build_cut_list, to_csv, to_html, to_tsv
from wireviz.wv_formboard import PAGE_SIZES, FormboardConfig, page_grid, build_formboard, render_formboard
from wireviz.wv_devices import expand_devices, list_devices
from wireviz.wv_import import from_kicad_netlist, from_wirelist
from wireviz.wv_machine import machine_joblist, to_csv as machine_csv
from wireviz.wv_drc import format_report, has_errors, run_drc
from wireviz.wv_sourcing import (
    DigiKeyProvider,
    MouserProvider,
    SourcingCache,
    enrich_bom,
    sourced_to_csv,
)
from wireviz.wv_svg import export_json, render_svg
from wireviz.wv_viewer import render_html, render_html_3d

format_codes = {
    # "c": "csv",
    "g": "gv",
    "h": "html",
    "p": "png",
    # "P": "pdf",
    "s": "svg",
    "t": "tsv",
}

def _wants_preprocess(data: dict) -> bool:
    """True if the harness uses the device library or a connector_type."""
    if "devices" in data:
        return True
    if (data.get("options") or {}).get("connector_type"):
        return True
    for attrs in (data.get("connectors") or {}).values():
        if isinstance(attrs, dict) and attrs.get("connector_type"):
            return True
    return False


epilog = "The -f or --format option accepts a string containing one or more of the "
epilog += "following characters to specify which file types to output:\n"
epilog += ", ".join([f"{key} ({value.upper()})" for key, value in format_codes.items()])


@click.command(
    epilog=epilog,
    no_args_is_help=True,
    context_settings=dict(help_option_names=["-h", "--help"]),
)
@click.argument("file", nargs=-1)
@click.option(
    "-f",
    "--format",
    default="hpst",
    type=str,
    show_default=True,
    help="Output formats (see below).",
)
@click.option(
    "-p",
    "--prepend",
    default=[],
    multiple=True,
    type=Path,
    help="YAML file to prepend to the input file (optional).",
)
@click.option(
    "-o",
    "--output-dir",
    default=None,
    type=Path,
    help="Directory to use for output files, if different from input file directory.",
)
@click.option(
    "-O",
    "--output-name",
    default=None,
    type=str,
    help="File name (without extension) to use for output files, if different from input file name.",
)
@click.option(
    "--drc/--no-drc",
    "drc",
    default=True,
    show_default=True,
    help="Run design-rule checks and print a report.",
)
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Exit with a non-zero status if DRC finds any errors.",
)
@click.option(
    "--grid",
    is_flag=True,
    default=False,
    help="Also write a native grid-snapped SVG (<name>.grid.svg).",
)
@click.option(
    "--viewer",
    is_flag=True,
    default=False,
    help="Write a self-contained interactive HTML viewer (<name>.viewer.html).",
)
@click.option(
    "--viewer3d",
    is_flag=True,
    default=False,
    help="Write an interactive 3D viewer (<name>.viewer3d.html; needs internet "
    "for three.js).",
)
@click.option(
    "--json",
    "json_out",
    is_flag=True,
    default=False,
    help="Write the harness layout as JSON (<name>.layout.json).",
)
@click.option(
    "--formboard",
    "formboard",
    default=None,
    type=click.Choice(sorted(PAGE_SIZES.keys())),
    help="Write a 1:1 formboard SVG tiled for the given sheet size "
    "(<name>.formboard.svg).",
)
@click.option(
    "--dxf", is_flag=True, default=False,
    help="Write the formboard as DXF for CAD (<name>.formboard.dxf).",
)
@click.option(
    "--netlist", is_flag=True, default=False,
    help="Write the electrical netlist (<name>.netlist.txt).",
)
@click.option(
    "--accessories", "accessories_out", is_flag=True, default=False,
    help="Write the accessory/covering BOM (<name>.accessories.tsv).",
)
@click.option(
    "--cutmachine", is_flag=True, default=False,
    help="Write a wire-processing machine job CSV (<name>.cutmachine.csv).",
)
@click.option(
    "--markers", is_flag=True, default=False,
    help="Write wire markers: CSV + label sheet (<name>.markers.csv/.svg).",
)
@click.option(
    "--traveler", is_flag=True, default=False,
    help="Write the assembly traveler (<name>.traveler.txt).",
)
@click.option(
    "--report", is_flag=True, default=False,
    help="Print an engineering report (weight, bundles, nets) to the console.",
)
@click.option(
    "--dossier", is_flag=True, default=False,
    help="Write a self-contained HTML build dossier (<name>.dossier.html).",
)
@click.option(
    "--pinout", is_flag=True, default=False,
    help="Write per-connector pinout cards (<name>.pinout.html).",
)
@click.option(
    "--editor", is_flag=True, default=False,
    help="Write an interactive drag-to-edit HTML viewer (<name>.editor.html).",
)
@click.option(
    "--diff", "diff_file", default=None, type=Path,
    help="Print a revision diff of this harness against another YAML file.",
)
@click.option(
    "--cutsheet",
    "cutsheet",
    default=None,
    type=click.Choice(["tsv", "csv", "html"]),
    help="Write a wire cut sheet in the given format (<name>.cutsheet.<ext>).",
)
@click.option(
    "--source",
    "source",
    default=None,
    type=click.Choice(["digikey", "mouser"]),
    help="Enrich the BOM with distributor pricing/stock (<name>.sourced.csv). "
    "Needs DIGIKEY_CLIENT_ID/SECRET or MOUSER_API_KEY in the environment.",
)
@click.option(
    "--import",
    "import_fmt",
    default=None,
    type=click.Choice(["wirelist", "kicad"]),
    help="Treat FILE as an import source: a from/to wire-list CSV or a KiCad "
    "netlist, converted to a harness before generating outputs.",
)
@click.option(
    "--cad-dir",
    "cad_dir",
    default=None,
    type=click.Path(exists=True, file_okay=False),
    help="Directory of connector CAD assets (<connector_type>.png/.glb, ...) "
    "used by the grid/viewer/3D outputs.",
)
@click.option(
    "--list-devices",
    "list_devices_flag",
    is_flag=True,
    default=False,
    help="List the built-in device library and exit.",
)
@click.option(
    "--list-connectors",
    "list_connectors_flag",
    is_flag=True,
    default=False,
    help="List the built-in connector-type library and exit.",
)
@click.option(
    "-V",
    "--version",
    is_flag=True,
    default=False,
    help=f"Output {APP_NAME} version and exit.",
)
def wireviz(
    file,
    format,
    prepend,
    output_dir,
    output_name,
    drc,
    strict,
    grid,
    viewer,
    viewer3d,
    json_out,
    formboard,
    dxf,
    netlist,
    accessories_out,
    cutmachine,
    markers,
    traveler,
    report,
    dossier,
    pinout,
    editor,
    diff_file,
    cutsheet,
    source,
    import_fmt,
    cad_dir,
    list_devices_flag,
    list_connectors_flag,
    version,
):
    """
    Parses the provided FILE and generates the specified outputs.
    """
    print()
    print(f"{APP_NAME} {__version__}")
    if version:
        return  # print version number only and exit
    if list_devices_flag:
        print("\nAvailable devices (reference under a 'devices:' section):")
        for name, desc in list_devices():
            print(f"  {name:20} {desc}")
        return
    if list_connectors_flag:
        print("\nConnector types (set 'connector_type:' on a connector):")
        for name, desc in list_connectors():
            print(f"  {name:22} {desc}")
        return

    # get list of files
    try:
        _ = iter(file)
    except TypeError:
        filepaths = [file]
    else:
        filepaths = list(file)

    # determine output formats
    output_formats = []
    for code in format:
        if code in format_codes:
            output_formats.append(format_codes[code])
        else:
            raise Exception(f"Unknown output format: {code}")
    output_formats = tuple(sorted(set(output_formats)))
    if len(output_formats) > 1:
        output_formats_str = f'[{"|".join(output_formats)}]'
    elif len(output_formats) == 1:
        output_formats_str = output_formats[0]
    else:
        output_formats_str = ""  # no Graphviz outputs; only feature outputs

    # check prepend file
    if len(prepend) > 0:
        prepend_input = ""
        for prepend_file in prepend:
            prepend_file = Path(prepend_file)
            if not prepend_file.exists():
                raise Exception(f"File does not exist:\n{prepend_file}")
            print("Prepend file:", prepend_file)

            prepend_input += file_read_text(prepend_file) + "\n"
    else:
        prepend_input = ""

    # run WireVIz on each input file
    any_errors = False
    for file in filepaths:
        file = Path(file)
        if not file.exists():
            raise Exception(f"File does not exist:\n{file}")

        # file_out = file.with_suffix("") if not output_file else output_file
        _output_dir = file.parent if not output_dir else output_dir
        _output_name = file.stem if not output_name else output_name

        print("Input file:  ", file)
        if output_formats_str:
            print(
                "Output file: ",
                f"{Path(_output_dir / _output_name)}.{output_formats_str}",
            )

        yaml_input = file_read_text(file)
        file_dir = file.parent

        yaml_input = prepend_input + yaml_input
        image_paths = {file_dir}
        for p in prepend:
            image_paths.add(Path(p).parent)

        # If importing, convert the source (wire-list CSV or KiCad netlist) into
        # a WireViz data dict first.
        if import_fmt:
            harness_input = (
                from_wirelist(yaml_input)
                if import_fmt == "wirelist"
                else from_kicad_netlist(yaml_input)
            )
        else:
            # Expand device-library references and back-fill connector-type
            # metadata before parsing. Only switch to the dict path when one of
            # those features is used, so behaviour is identical otherwise.
            harness_input = yaml_input
            try:
                probe = yaml.safe_load(yaml_input)
            except Exception:  # noqa: BLE001 - let parse report YAML errors
                probe = None
            if isinstance(probe, dict) and _wants_preprocess(probe):
                harness_input = apply_connector_types(expand_devices(probe))

        # Parse once to the model; the extra features below run on it directly
        # and need no `dot` binary, so a missing Graphviz can't block them.
        harness = wv.parse(
            harness_input,
            return_types="harness",
            image_paths=list(image_paths),
            source_path=file,
        )
        output_base = Path(_output_dir) / _output_name

        # Design-rule checks
        if drc:
            findings = run_drc(harness)
            print(format_report(findings))
            if strict and has_errors(findings):
                any_errors = True

        # Wire cut sheet
        if cutsheet:
            rows = build_cut_list(harness)
            renderer = {"tsv": to_tsv, "csv": to_csv, "html": to_html}[cutsheet]
            ext = cutsheet
            out = output_base.with_suffix(f".cutsheet.{ext}")
            out.write_text(renderer(rows))
            print("Cut sheet:   ", out)

        # Distributor sourcing
        if source:
            provider = (
                DigiKeyProvider() if source == "digikey" else MouserProvider()
            )
            if not provider.available():
                print(
                    f"Warning: {source} credentials not set; writing an "
                    f"un-priced BOM. Set the required environment variables "
                    f"to enable live pricing."
                )
            cache = SourcingCache(output_base.with_suffix(".sourcing-cache.json"))
            lines = enrich_bom(harness.bom(), provider, cache=cache)
            out = output_base.with_suffix(".sourced.csv")
            out.write_text(sourced_to_csv(lines))
            print("Sourced BOM: ", out)

        _cad = str(cad_dir) if cad_dir else None

        # Native grid-snapped SVG (independent of Graphviz)
        if grid:
            out = output_base.with_suffix(".grid.svg")
            out.write_text(render_svg(harness, cad_dir=_cad))
            print("Grid SVG:    ", out)

        # Interactive HTML viewer (self-contained)
        if viewer:
            out = output_base.with_suffix(".viewer.html")
            out.write_text(render_html(harness, cad_dir=_cad))
            print("Viewer:      ", out)

        # Interactive 3D viewer (three.js from CDN)
        if viewer3d:
            out = output_base.with_suffix(".viewer3d.html")
            out.write_text(render_html_3d(harness, cad_dir=_cad))
            print("3D viewer:   ", out)

        # Layout JSON
        if json_out:
            out = output_base.with_suffix(".layout.json")
            out.write_text(export_json(harness, cad_dir=_cad))
            print("Layout JSON: ", out)

        # 1:1 formboard (nail-board) SVG
        if formboard:
            fb_cfg = FormboardConfig(page=formboard)
            out = output_base.with_suffix(".formboard.svg")
            out.write_text(render_formboard(harness, fb_cfg))
            grid = page_grid(build_formboard(harness, fb_cfg), fb_cfg)
            print(
                f"Formboard:    {out}  ({grid['cols']}×{grid['rows']} "
                f"{formboard} sheets)"
            )

        # Formboard DXF for CAD
        if dxf:
            out = output_base.with_suffix(".formboard.dxf")
            out.write_text(formboard_to_dxf(harness))
            print("DXF:         ", out)

        # Electrical netlist
        if netlist:
            out = output_base.with_suffix(".netlist.txt")
            out.write_text(nets_text(compute_nets(harness)))
            print("Netlist:     ", out)

        # Accessory / covering BOM
        if accessories_out:
            out = output_base.with_suffix(".accessories.tsv")
            out.write_text(accessories_tsv(accessory_bom(harness)))
            print("Accessories: ", out)

        # Combined HTML build dossier
        if dossier:
            out = output_base.with_suffix(".dossier.html")
            out.write_text(render_dossier(harness))
            print("Dossier:     ", out)

        # Wire-processing machine job
        if cutmachine:
            out = output_base.with_suffix(".cutmachine.csv")
            out.write_text(machine_csv(machine_joblist(harness)))
            print("Cut machine: ", out)

        # Per-connector pinout cards
        if pinout:
            out = output_base.with_suffix(".pinout.html")
            out.write_text(pinout_html(harness))
            print("Pinout:      ", out)

        # Interactive drag-to-edit viewer
        if editor:
            out = output_base.with_suffix(".editor.html")
            out.write_text(render_editor(harness))
            print("Editor:      ", out)

        # Wire markers (CSV + label sheet)
        if markers:
            mk = build_markers(harness)
            output_base.with_suffix(".markers.csv").write_text(markers_csv(mk))
            output_base.with_suffix(".markers.svg").write_text(to_svg_sheet(mk))
            print("Markers:     ", output_base.with_suffix(".markers.csv"))

        # Assembly traveler
        if traveler:
            out = output_base.with_suffix(".traveler.txt")
            out.write_text(traveler_text(build_traveler(harness)))
            print("Traveler:    ", out)

        # Engineering report to console
        if report:
            wr = weight_report(harness)
            print("\n--- Engineering report ---")
            print(
                f"Conductor length: {wr['total_conductor_length_m']} m"
                + (f"   Weight: {wr['total_mass_g']} g" if wr["total_mass_g"] else "")
            )
            print(f"Nets: {len(compute_nets(harness))}")
            for b in bundle_report(harness):
                sleeve = (
                    f"  sleeve ≥ {b.recommended_sleeve} mm"
                    if b.recommended_sleeve
                    else ""
                )
                print(
                    f"  {b.cable}: {b.wire_count} wires, bundle ~{b.bundle_od} mm"
                    + sleeve
                )

        # Revision diff against another harness
        if diff_file:
            other = wv.parse(
                file_read_text(Path(diff_file)), return_types="harness"
            )
            print(f"\n--- Diff vs {diff_file} ---")
            print(diff_text(diff_harnesses(other, harness)))

        # Standard Graphviz-backed outputs last (these need the `dot` binary)
        if output_formats:
            try:
                harness.output(
                    filename=str(output_base), fmt=output_formats, view=False
                )
            except Exception as e:  # noqa: BLE001
                print(f"Warning: could not generate {output_formats_str}: {e}")

    print()
    if any_errors:
        sys.exit(1)


if __name__ == "__main__":
    wireviz()
