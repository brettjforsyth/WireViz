# -*- coding: utf-8 -*-

import os
import sys
from pathlib import Path

import click

if __name__ == "__main__":
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import wireviz.wireviz as wv
from wireviz import APP_NAME, __version__
from wireviz.wv_helper import file_read_text
from wireviz.wv_cutsheet import build_cut_list, to_csv, to_html, to_tsv
from wireviz.wv_drc import format_report, has_errors, run_drc
from wireviz.wv_sourcing import (
    DigiKeyProvider,
    MouserProvider,
    SourcingCache,
    enrich_bom,
    sourced_to_csv,
)
from wireviz.wv_svg import render_svg

format_codes = {
    # "c": "csv",
    "g": "gv",
    "h": "html",
    "p": "png",
    # "P": "pdf",
    "s": "svg",
    "t": "tsv",
}

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
    cutsheet,
    source,
    version,
):
    """
    Parses the provided FILE and generates the specified outputs.
    """
    print()
    print(f"{APP_NAME} {__version__}")
    if version:
        return  # print version number only and exit

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

        # Parse once to the model; the extra features below run on it directly
        # and need no `dot` binary, so a missing Graphviz can't block them.
        harness = wv.parse(
            yaml_input,
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

        # Native grid-snapped SVG (independent of Graphviz)
        if grid:
            out = output_base.with_suffix(".grid.svg")
            out.write_text(render_svg(harness))
            print("Grid SVG:    ", out)

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
