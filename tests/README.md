# WireViz tests

Golden-master regression tests. Until now WireViz had no test suite — CI only
checked that `build_examples.py` did not crash. These tests lock the **rendered
graph structure** so refactors (and the planned grid-snap / 2D-3D renderer work)
have a safety net.

## What is covered

`test_examples_golden.py` renders every `.yml` under `examples/` and `tutorial/`
through the pure-Python parse → data-model → Graphviz-DOT path
(`Harness.graph.source`) and compares it byte-for-byte against the committed
`.gv` baseline. Version-string headers and machine-specific absolute image
paths are normalized out so the snapshots are portable and survive version bumps.

It deliberately does **not** compare PNG/SVG output — that depends on the
installed Graphviz binary version and is not suitable for byte-exact snapshots.

## Requirements

The `wireviz` package and its Python dependencies (`graphviz`, `pyyaml`,
`click`, `Pillow`). The `dot` binary is **not** required. `pytest` is optional.

## Running

```sh
pytest tests/                       # via pytest
python tests/test_examples_golden.py  # standalone, prints an N/N summary
```

## Updating the baselines

If a change intentionally alters rendered output, regenerate the examples
(`python -m wireviz.build_examples build`) and re-commit the updated `.gv`
files. A diff in these tests that you did **not** intend is a regression.
