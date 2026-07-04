# WireViz Harness Agent — Guide

You (the agent) have a **WireViz MCP server** connected. It lets you design,
verify, and document real wire harnesses from a text description: you author a
harness in WireViz YAML, then call tools to validate it, run engineering checks,
and produce manufacturing outputs. This guide is your reference for what the
tools do, how they're set up, and — importantly — **where each output goes.**

---

## 1. Overview

A harness is described in **WireViz YAML**: connectors (with pins), cables (with
wires), and the connections between them. Your job is to turn a human's request
into that YAML, verify it with the tools, and hand back results.

Minimal harness shape:

```yaml
metadata:
  title: Example Harness
connectors:
  X1: {pincount: 3, pinlabels: [SIG, GND, PWR]}
  X2: {pincount: 3}
cables:
  W1: {wirecount: 3, gauge: 20 AWG, length: 1.5, colors: [WH, BK, RD]}
connections:
  -
    - X1: [1, 2, 3]
    - W1: [1, 2, 3]
    - X2: [1, 2, 3]
```

Connectors can also be defined by type (`connector_type: deutsch_dt_4`) or as
devices (a `devices:` section), and you can tag components with `variants:` for
option families. Use `list_connectors` / `list_devices` to see what's built in.

### The recommended loop

1. **`validate_harness`** — always call first; confirm the YAML parses.
2. **`run_drc`** — fix every `ERROR` in the findings before continuing; review warnings.
3. **`recommend_gauge`** — size any power/high-current wires for their current & length.
4. **`generate_bom` / `generate_cutsheet` / `engineering_report`** — costing & build data.
5. **`render_svg`** (or `render_diagram`) — a diagram to show the human.

Every tool returns `{"ok": true, ...}` or `{"ok": false, "error": "..."}` — check
`ok` and surface the error text if it's false.

---

## 2. Tools

| Tool | Input | Returns |
|------|-------|---------|
| `validate_harness` | `harness_yaml` | summary (connectors, cables, wire count) or parse error |
| `run_drc` | `harness_yaml` | design-rule `findings` + error/warning/info counts |
| `generate_bom` | `harness_yaml` | bill of materials rows |
| `generate_cutsheet` | `harness_yaml` | per-wire cut list + bulk length by gauge |
| `generate_netlist` | `harness_yaml` | electrical nets + floating pins |
| `render_svg` | `harness_yaml` | native grid-snapped SVG (text) |
| `render_diagram` | `harness_yaml`, `fmt`, `output_dir` | Graphviz `svg`/`png`/`html` |
| `recommend_gauge` | `current`, `length_m`, `max_drop_v` | thinnest AWG that fits |
| `engineering_report` | `harness_yaml` | weight, bundle/sleeve, power/voltage-drop |
| `list_connectors` / `list_devices` | — | built-in libraries |
| `import_wirelist` | `csv_text` | a from/to wire list → harness YAML |
| `import_kicad` | `netlist_text` | a KiCad netlist → harness YAML |
| `generate_formboard` | `harness_yaml`, `page`, `output_dir` | 1:1 formboard SVG |

The tools are **stateless**: each call takes the full harness YAML (harnesses are
small text). There is no open document — keep the authoritative YAML in the
conversation and pass it each time.

---

## 3. Where the output goes (save-location decisions)

This is deliberate, so you know what to expect and can tell the human.

**Default: inline.** Almost every tool returns its result *in the tool response*,
not to disk. Data comes back as JSON; diagrams as SVG text. Nothing is written
to the filesystem unless a tool is specifically a file writer (below). This keeps
the server stateless and working even with no shared filesystem.

These are **always inline**, never written to disk:
`validate_harness`, `run_drc`, `generate_bom`, `generate_cutsheet`,
`generate_netlist`, `render_svg`, `recommend_gauge`, `engineering_report`,
`list_connectors`, `list_devices`, `import_wirelist`, `import_kicad`.

**File writers** — controlled by an `output_dir` argument, or the
`WIREVIZ_MCP_OUTPUT_DIR` environment variable set at install time:

- **`render_diagram`** — `fmt: svg` is returned inline; `fmt: png` or `fmt: html`
  is **written to the output directory** and the tool returns its `path`.
- **`generate_formboard`** — if an output directory is configured it **writes the
  SVG there** and returns `path` + `sheets`; otherwise it returns the SVG inline.

### With this installation

`WIREVIZ_MCP_OUTPUT_DIR` is set to **`~/wireviz-output`**. So, concretely:

- Diagrams you want to *show inline in the chat* → use **`render_svg`** (SVG text,
  never touches disk).
- A saved **PNG/HTML** diagram or a **formboard** file → those land in
  **`~/wireviz-output`**, and the tool gives you the `path`. **Tell the human the
  file path** so they can open it.
- All engineering data (BOM, cut sheet, DRC, netlist, weight/power) is inline —
  present it directly; save it yourself only if the human asks.

If you pass an explicit `output_dir` to `render_diagram` / `generate_formboard`,
it overrides the environment default for that call.

---

## 4. Setup (how it's connected)

The server is installed in an isolated venv and registered in Claude Desktop:

- Installed via `pip install "wireviz[mcp] @ git+https://github.com/brettjforsyth/WireViz.git"`
  into `~/.wireviz-mcp`.
- Registered in `claude_desktop_config.json` under `mcpServers.wireviz`, pointing
  at the absolute path `~/.wireviz-mcp/bin/wireviz-mcp`, with
  `WIREVIZ_MCP_OUTPUT_DIR=~/wireviz-output`.
- Runs over **stdio** — Claude Desktop launches the process locally on the same
  Mac, so it shares that filesystem (which is why `~/wireviz-output` is reachable).

Notes:
- Needs **Python 3.10+** (for the `mcp` SDK).
- `render_diagram` with `png`/`html` needs **Graphviz `dot`** installed
  (`brew install graphviz`). `render_svg`, the formboard, and all data tools work
  without it.
- A code change to WireViz requires **quitting and relaunching Claude Desktop**
  (MCP servers load only at launch).

---

## 5. Tips for authoring good harnesses

- Pins can be numbers or labels; keep `pincount` consistent with `pins`/`pinlabels`.
- Declare `current:` (amps) and `voltage:` on a cable to unlock ampacity,
  voltage-drop, bundle-derating, and power checks in `run_drc` /
  `engineering_report`.
- Wire `1` refers to the first wire of a cable; `s` is a shield.
- Prefer `connector_type:` / `devices:` for known parts so metadata (pincount,
  gender, manufacturer) fills in automatically.
- Run `run_drc` after every edit — it catches unconnected pins, out-of-range
  wires, shield/gauge/mate problems, and current overloads before they reach the
  bench.
