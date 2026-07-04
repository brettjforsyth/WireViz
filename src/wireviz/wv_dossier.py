# -*- coding: utf-8 -*-
"""Harness dossier: one self-contained HTML build package.

Combines the outputs a builder actually needs into a single, shareable,
offline HTML document: the grid diagram, the wire cut sheet (with MIL-STD ident
bands), an engineering summary (weight, nets, bundle diameter + sleeve), the
accessory BOM, and the assembly traveler.
"""

from html import escape
from typing import Optional

from wireviz.wv_accessories import accessory_bom
from wireviz.wv_assembly import build_traveler
from wireviz.wv_bundle import bundle_report
from wireviz.wv_cutsheet import build_cut_list, to_html as cutsheet_html
from wireviz.wv_nets import compute_nets, floating_nodes
from wireviz.wv_svg import render_svg
from wireviz.wv_weight import weight_report

_STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { font-family: system-ui, sans-serif; margin: 0; padding: 24px;
       background: #fff; color: #111; }
@media (prefers-color-scheme: dark) {
  body { background: #1b1b1b; color: #eee; }
  table { border-color: #444; }
  th, td { border-color: #383838; }
  thead th { background: #2a2a2a; }
  .card { background: #222; border-color: #383838; }
  .diagram { background: #202020; }
}
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 16px; margin: 28px 0 8px; border-bottom: 1px solid #ccc;
     padding-bottom: 4px; }
.sub { opacity: 0.6; font-size: 13px; margin-bottom: 12px; }
.grid { display: flex; flex-wrap: wrap; gap: 12px; }
.card { border: 1px solid #ddd; border-radius: 8px; padding: 10px 14px;
        min-width: 130px; }
.card .n { font-size: 20px; font-weight: 600; }
.card .l { font-size: 12px; opacity: 0.65; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { border: 1px solid #ddd; padding: 4px 8px; text-align: left; }
thead th { background: #f2f2f2; }
.diagram { overflow: auto; border: 1px solid #ddd; border-radius: 8px;
           padding: 8px; background: #fafafa; }
.diagram svg { max-width: 100%; height: auto; }
ol.traveler { padding-left: 22px; }
ol.traveler li { margin: 4px 0; }
ol.traveler .detail { display: block; opacity: 0.7; font-size: 12px; }
""".strip()


def _summary_cards(harness) -> str:
    wr = weight_report(harness)
    nets = compute_nets(harness)
    floats = floating_nodes(nets)
    cards = [
        ("Connectors", len(harness.connectors)),
        ("Cables", len(harness.cables)),
        ("Nets", len(nets)),
        ("Floating pins", len(floats)),
        ("Conductor length", f"{wr['total_conductor_length_m']} m"),
    ]
    if wr["total_mass_g"] is not None:
        cards.append(("Weight", f"{wr['total_mass_g']} g"))
    return '<div class="grid">' + "".join(
        f'<div class="card"><div class="n">{escape(str(v))}</div>'
        f'<div class="l">{escape(l)}</div></div>'
        for l, v in cards
    ) + "</div>"


def _bundle_table(harness) -> str:
    rows = bundle_report(harness)
    body = "".join(
        f"<tr><td>{escape(b.cable)}</td><td>{b.wire_count}</td>"
        f"<td>{b.wire_od if b.wire_od is not None else '—'}</td>"
        f"<td>{b.bundle_od}</td>"
        f"<td>{b.recommended_sleeve if b.recommended_sleeve else '—'}</td></tr>"
        for b in rows
    )
    return (
        "<table><thead><tr><th>Cable</th><th>Wires</th><th>Wire OD (mm)</th>"
        "<th>Bundle OD (mm)</th><th>Sleeve ≥ (mm)</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def _accessory_table(harness) -> str:
    bom = accessory_bom(harness)
    if not bom:
        return "<p class='sub'>No accessories declared.</p>"
    body = "".join(
        f"<tr><td>{escape(g['category'])}</td><td>{escape(g['type'])}</td>"
        f"<td>{escape(g['mpn'] or '')}</td><td>{g['qty']}</td>"
        f"<td>{escape(g['unit'])}</td><td>{escape(', '.join(g['hosts']))}</td></tr>"
        for g in bom
    )
    return (
        "<table><thead><tr><th>Category</th><th>Type</th><th>MPN</th>"
        "<th>Qty</th><th>Unit</th><th>On</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def _traveler_list(harness) -> str:
    steps = build_traveler(harness)
    items = "".join(
        f"<li><b>[{escape(s.kind)}]</b> {escape(s.title)}"
        + (f'<span class="detail">{escape(s.detail)}</span>' if s.detail else "")
        + "</li>"
        for s in steps
    )
    return f'<ol class="traveler">{items}</ol>'


def render_dossier(harness, config=None, title: Optional[str] = None) -> str:
    """Return a self-contained HTML dossier for the harness."""
    if title is None:
        title = (harness.metadata.get("title") if harness.metadata else None) or "Harness"
    svg = render_svg(harness, config)
    cut = cutsheet_html(build_cut_list(harness))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} — dossier</title>
<style>{_STYLE}</style>
</head>
<body>
<h1>{escape(title)}</h1>
<div class="sub">Harness dossier — diagram, cut sheet, engineering, accessories, assembly.</div>
{_summary_cards(harness)}
<h2>Diagram</h2>
<div class="diagram">{svg}</div>
<h2>Wire cut sheet</h2>
{cut}
<h2>Bundles &amp; sleeves</h2>
{_bundle_table(harness)}
<h2>Accessories</h2>
{_accessory_table(harness)}
<h2>Assembly traveler</h2>
{_traveler_list(harness)}
</body>
</html>
"""
