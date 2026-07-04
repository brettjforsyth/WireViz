# -*- coding: utf-8 -*-
"""Continuity / isolation test-program generation.

From the harness's electrical nets, emit the two test types an automated tester
(bed-of-nails, harness tester) runs:

- **continuity**: pins on the same net must read connected (low resistance);
- **isolation**: pins on different nets must read open (high resistance).

A net of N pins is proven by N-1 continuity checks (a spanning chain). Isolation
is checked between one representative pin per net, pairwise, so the program size
stays manageable on large harnesses.
"""

from dataclasses import dataclass
from typing import List, Tuple

from wireviz.wv_nets import Node, compute_nets


@dataclass
class TestStep:
    kind: str  # 'continuity' | 'isolation'
    a: Node
    b: Node
    expect: str  # 'closed' | 'open'
    net_a: str
    net_b: str


def _fmt(node: Node) -> str:
    return f"{node[0]}:{node[1]}"


def continuity_tests(harness) -> List[TestStep]:
    """N-1 continuity checks per net (a chain proving every pin is common)."""
    steps = []
    for net in compute_nets(harness):
        for i in range(1, len(net.nodes)):
            steps.append(
                TestStep("continuity", net.nodes[0], net.nodes[i], "closed", net.name, net.name)
            )
    return steps


def isolation_tests(harness) -> List[TestStep]:
    """Pairwise isolation between one representative pin of each multi-pin net.

    Single-pin (floating) nets are skipped — there's nothing to isolate a bare
    open pin against meaningfully.
    """
    nets = [n for n in compute_nets(harness) if n.pin_count >= 1]
    reps = [(n.name, n.nodes[0]) for n in nets]
    steps = []
    for i in range(len(reps)):
        for j in range(i + 1, len(reps)):
            steps.append(
                TestStep("isolation", reps[i][1], reps[j][1], "open", reps[i][0], reps[j][0])
            )
    return steps


def build_test_program(harness, include_isolation: bool = True) -> List[TestStep]:
    steps = continuity_tests(harness)
    if include_isolation:
        steps += isolation_tests(harness)
    return steps


def to_csv(steps: List[TestStep]) -> str:
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["step", "kind", "point_a", "point_b", "expect", "net_a", "net_b"])
    for i, s in enumerate(steps, start=1):
        w.writerow([i, s.kind, _fmt(s.a), _fmt(s.b), s.expect, s.net_a, s.net_b])
    return buf.getvalue()


def summary(steps: List[TestStep]) -> Tuple[int, int]:
    c = sum(1 for s in steps if s.kind == "continuity")
    return c, len(steps) - c
