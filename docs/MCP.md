# WireViz MCP server

The WireViz engine is exposed as a [Model Context Protocol](https://modelcontextprotocol.io)
server so **any agent can build and verify wire harnesses** — design a harness
in YAML, validate it, run design-rule checks, compute the BOM / cut sheet /
netlist / weight, recommend a wire gauge, and render a diagram — iterating on
structured results rather than scraping CLI output.

## Install & run

```sh
pip install "wireviz[mcp]"     # adds the optional `mcp` dependency
wireviz-mcp                     # runs the server over stdio
# or: python -m wireviz.wv_mcp
```

## Register it with an agent

Point any MCP client at the `wireviz-mcp` command. For a Claude Code / Claude
Desktop style config (`.mcp.json` or `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "wireviz": {
      "command": "wireviz-mcp",
      "env": { "WIREVIZ_MCP_OUTPUT_DIR": "/path/to/harness-output" }
    }
  }
}
```

`WIREVIZ_MCP_OUTPUT_DIR` is optional (see *Where the output lives* below).

## Tools

| Tool | Purpose |
|------|---------|
| `validate_harness(harness_yaml)` | parse + summary (or a parse error) — call first |
| `run_drc(harness_yaml)` | design-rule findings ranked by severity |
| `generate_bom(harness_yaml)` | bill of materials rows |
| `generate_cutsheet(harness_yaml)` | per-wire cut list + bulk length by gauge |
| `generate_netlist(harness_yaml)` | electrical nets + floating pins |
| `render_svg(harness_yaml)` | native grid-snapped SVG (inline text) |
| `render_diagram(harness_yaml, fmt, output_dir)` | Graphviz svg/png/html (needs `dot`) |
| `recommend_gauge(current, length_m, max_drop_v)` | minimum AWG for a run |
| `engineering_report(harness_yaml)` | weight, bundle/sleeve, power/voltage-drop |
| `list_connectors()` / `list_devices()` | built-in libraries |
| `import_wirelist(csv_text)` / `import_kicad(netlist_text)` | seed a harness from a wire list / netlist → YAML |
| `generate_formboard(harness_yaml, page, output_dir)` | 1:1 formboard SVG |

Every tool is **stateless** — it takes the full harness YAML each call (harnesses
are small text) — and returns `{ "ok": true, ... }` or `{ "ok": false, "error": ... }`.

## Where the output lives

By default, **nowhere on disk — output is returned inline in the tool result.**
`render_svg` and `generate_formboard` return the SVG as text; `generate_bom`,
`run_drc`, `generate_netlist`, etc. return JSON. The calling agent receives the
data and decides where to save it, so the server works even when the agent has
no shared filesystem (sandboxed or remote).

The file-oriented tools (`render_diagram` for `png`/`html`, and optionally
`generate_formboard`) take an **`output_dir`** argument — or read the
`WIREVIZ_MCP_OUTPUT_DIR` environment variable — and when set they write the file
there and return its `path` instead of the content. So: **inline by default,
on-disk when you ask for it.**

## A typical agent design loop

1. `validate_harness` — confirm the YAML parses.
2. `run_drc` — fix any errors/warnings in the findings.
3. `recommend_gauge` — size power wires for their current/length.
4. `generate_bom` / `generate_cutsheet` / `engineering_report` — costing & build data.
5. `render_svg` (or `render_diagram`) — a diagram to show the human.
