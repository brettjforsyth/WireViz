# -*- coding: utf-8 -*-
"""Electrical net extraction and netlist export.

A *net* is a set of connector pins that are electrically common — joined by
cable wires, through splices, and across mated connectors. Computing nets lets
the tool verify continuity, find floating/single-ended nodes, and export a
netlist for cross-checking against a schematic.

Nodes are ``(connector, pin)`` pairs; a union-find merges them across every
cable wire, mate pin, and whole-component mate.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from wireviz.DataClasses import MateComponent, MatePin

Node = Tuple[str, object]  # (connector name, pin id)


class _UnionFind:
    def __init__(self):
        self.parent: Dict[Node, Node] = {}

    def find(self, x: Node) -> Node:
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: Node, b: Node) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


@dataclass
class Net:
    name: str
    nodes: List[Node] = field(default_factory=list)

    @property
    def pin_count(self) -> int:
        return len(self.nodes)


def compute_nets(harness) -> List[Net]:
    """Return the electrical nets of the harness, sorted by size then name."""
    uf = _UnionFind()

    # every declared connector pin is a node (so isolated pins show as 1-pin nets)
    for cname, conn in harness.connectors.items():
        for pin in conn.pins:
            uf.find((cname, pin))

    # cable wires join their two endpoints
    for cable in harness.cables.values():
        for c in cable.connections:
            if c.from_name is not None and c.to_name is not None:
                uf.union(
                    (c.from_name, c.from_pin), (c.to_name, c.to_pin)
                )

    # mates join pins directly
    for mate in harness.mates:
        if isinstance(mate, MatePin):
            uf.union((mate.from_name, mate.from_pin), (mate.to_name, mate.to_pin))
        elif isinstance(mate, MateComponent):
            a = harness.connectors.get(mate.from_name)
            b = harness.connectors.get(mate.to_name)
            if a and b:
                for pa, pb in zip(a.pins, b.pins):  # 1:1 pin mapping
                    uf.union((mate.from_name, pa), (mate.to_name, pb))

    groups: Dict[Node, List[Node]] = {}
    for node in list(uf.parent.keys()):
        groups.setdefault(uf.find(node), []).append(node)

    nets = []
    for i, nodes in enumerate(
        sorted(groups.values(), key=lambda g: (-len(g), _node_key(g[0]))), start=1
    ):
        nodes.sort(key=_node_key)
        nets.append(Net(name=f"N{i:03d}", nodes=nodes))
    return nets


def _node_key(node: Node):
    return (str(node[0]), str(node[1]))


def floating_nodes(nets: List[Net]) -> List[Node]:
    """Pins that are on a net of size 1 (connected to nothing else)."""
    return [n.nodes[0] for n in nets if n.pin_count == 1]


# --- exporters -------------------------------------------------------------


def to_text(nets: List[Net]) -> str:
    lines = []
    for net in nets:
        pins = "  ".join(f"{c}:{p}" for c, p in net.nodes)
        lines.append(f"{net.name} ({net.pin_count}): {pins}")
    return "\n".join(lines) + "\n"


def to_csv(nets: List[Net]) -> str:
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["net", "connector", "pin"])
    for net in nets:
        for cname, pin in net.nodes:
            w.writerow([net.name, cname, pin])
    return buf.getvalue()


def to_kicad_netlist(nets: List[Net]) -> str:
    """A minimal KiCad-style ``(nets ...)`` s-expression netlist."""
    out = ["(export (version D)", "  (nets"]
    for i, net in enumerate(nets, start=1):
        out.append(f'    (net (code {i}) (name "{net.name}")')
        for cname, pin in net.nodes:
            out.append(f'      (node (ref {cname}) (pin {pin})))'.replace(")))", "))"))
        out.append("    )")
    out.append("  )")
    out.append(")")
    return "\n".join(out) + "\n"
