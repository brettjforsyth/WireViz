# -*- coding: utf-8 -*-
"""Per-connector pinout cards.

For each connector, a card listing every pin with its label, the wire landing on
it, and where that wire goes — the reference an assembler uses when populating a
housing. Renders as a printable grid of HTML cards.
"""

from html import escape
from typing import Dict, List


def _is_shield(vp):
    return isinstance(vp, str) and vp.lower() == "s"


def _cavity_map(harness):
    """connector -> {pin: [(cable:wire, other_endpoint), ...]}."""
    out: Dict[str, Dict[object, list]] = {n: {} for n in harness.connectors}
    for cname, cable in harness.cables.items():
        for c in cable.connections:
            wid = "s" if _is_shield(c.via_port) else c.via_port
            wire = f"{cname}:{wid}"
            if c.from_name in out:
                other = f"{c.to_name}:{c.to_pin}" if c.to_name else "open"
                out[c.from_name].setdefault(c.from_pin, []).append((wire, other))
            if c.to_name in out:
                other = f"{c.from_name}:{c.from_pin}" if c.from_name else "open"
                out[c.to_name].setdefault(c.to_pin, []).append((wire, other))
    return out


def pinout_tables(harness) -> Dict[str, List[dict]]:
    """One row per pin per connector: pin, label, wire(s), destination(s)."""
    cav = _cavity_map(harness)
    tables: Dict[str, List[dict]] = {}
    for name, conn in harness.connectors.items():
        labels = conn.pinlabels or []
        rows = []
        for i, pin in enumerate(conn.pins):
            label = labels[i] if i < len(labels) and labels[i] else ""
            entries = cav.get(name, {}).get(pin, [])
            rows.append(
                {
                    "pin": pin,
                    "label": label,
                    "wire": ", ".join(w for w, _ in entries),
                    "to": ", ".join(o for _, o in entries),
                }
            )
        tables[name] = rows
    return tables


def to_html(harness, title: str = "Pinout Cards") -> str:
    tables = pinout_tables(harness)
    style = (
        ":root{color-scheme:light dark}*{box-sizing:border-box}"
        "body{font-family:system-ui,sans-serif;margin:16px}"
        ".cards{display:flex;flex-wrap:wrap;gap:12px}"
        ".card{border:1px solid #bbb;border-radius:8px;padding:8px 10px;"
        "min-width:230px;break-inside:avoid}"
        ".card h3{margin:0 0 6px;font-size:15px}"
        "table{border-collapse:collapse;width:100%;font-size:12px}"
        "th,td{border:1px solid #ddd;padding:2px 6px;text-align:left}"
        "th{background:#f2f2f2}"
        "@media(prefers-color-scheme:dark){body{background:#1b1b1b;color:#eee}"
        ".card{border-color:#444}th,td{border-color:#383838}th{background:#2a2a2a}}"
    )
    cards = []
    for name, rows in tables.items():
        conn = harness.connectors[name]
        subtitle = escape(str(conn.type)) if getattr(conn, "type", None) else ""
        body = "".join(
            f"<tr><td>{escape(str(r['pin']))}</td><td>{escape(r['label'])}</td>"
            f"<td>{escape(r['wire'])}</td><td>{escape(r['to'])}</td></tr>"
            for r in rows
        )
        cards.append(
            f'<div class="card"><h3>{escape(name)} '
            f'<small>{subtitle}</small></h3>'
            "<table><thead><tr><th>Pin</th><th>Label</th><th>Wire</th>"
            f"<th>To</th></tr></thead><tbody>{body}</tbody></table></div>"
        )
    return (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{escape(title)}</title><style>{style}</style></head>"
        f"<body><h1>{escape(title)}</h1>"
        f'<div class="cards">{"".join(cards)}</div></body></html>\n'
    )
