# -*- coding: utf-8 -*-
"""Design-rule checking (DRC) for WireViz harnesses.

Runs a set of independent rules over a fully-parsed :class:`Harness` and
returns a list of :class:`DRCFinding`. Nothing here mutates the harness, so it
is safe to run on a model that is also going to be rendered.

The rule set is intentionally a registry (`@rule`) so new checks can be added
without touching the runner, and so tests can exercise one rule at a time.

Severity levels:
    ERROR    - the harness is electrically/logically invalid or will render wrong
    WARNING  - probably a mistake, but the harness still renders
    INFO     - advisory (e.g. missing part numbers, so the item can't be sourced)
"""

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Dict, List, Optional

from wireviz.DataClasses import MateComponent, MatePin


class Severity(IntEnum):
    INFO = 10
    WARNING = 20
    ERROR = 30

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


@dataclass
class DRCFinding:
    severity: Severity
    code: str
    message: str
    component: Optional[str] = None  # designator this finding is about, if any

    def __str__(self) -> str:
        where = f" [{self.component}]" if self.component else ""
        return f"{self.severity.name:7} {self.code}{where}: {self.message}"


# --- rule registry ---------------------------------------------------------

# A rule is a callable(harness) -> Iterable[DRCFinding].
RULES: Dict[str, Callable] = {}


def rule(code: str):
    """Register a DRC rule under a stable code (e.g. 'E-WIRE-RANGE')."""

    def wrap(fn: Callable) -> Callable:
        fn.drc_code = code
        RULES[code] = fn
        return fn

    return wrap


def _is_shield_ref(via_port) -> bool:
    return isinstance(via_port, str) and via_port.lower() == "s"


def _pin_known(connector, pin) -> bool:
    """True if `pin` is a valid pin identifier on `connector`.

    Pins may be given as the raw pin id (in `connector.pins`) or, once a
    connection has been resolved, as a 1-based index into that list.
    """
    if pin in connector.pins:
        return True
    if isinstance(pin, int) and 1 <= pin <= len(connector.pins):
        return True
    return False


# --- rules -----------------------------------------------------------------


@rule("E-CONN-UNKNOWN")
def _unknown_endpoint(harness):
    """A cable connection names a connector that does not exist."""
    for cable in harness.cables.values():
        for c in cable.connections:
            for name in (c.from_name, c.to_name):
                if name is not None and name not in harness.connectors:
                    yield DRCFinding(
                        Severity.ERROR,
                        "E-CONN-UNKNOWN",
                        f"cable {cable.name} connects to unknown connector "
                        f"'{name}'",
                        cable.name,
                    )


@rule("E-PIN-UNKNOWN")
def _unknown_pin(harness):
    """A connection or mate references a pin that isn't on the connector."""
    for cable in harness.cables.values():
        for c in cable.connections:
            for name, pin in ((c.from_name, c.from_pin), (c.to_name, c.to_pin)):
                if name is None or pin is None:
                    continue
                conn = harness.connectors.get(name)
                if conn is not None and not _pin_known(conn, pin):
                    yield DRCFinding(
                        Severity.ERROR,
                        "E-PIN-UNKNOWN",
                        f"cable {cable.name} references pin '{pin}' on "
                        f"connector {name}, which has no such pin",
                        cable.name,
                    )
    for mate in harness.mates:
        if not isinstance(mate, MatePin):
            continue
        for name, pin in ((mate.from_name, mate.from_pin), (mate.to_name, mate.to_pin)):
            conn = harness.connectors.get(name)
            if conn is not None and not _pin_known(conn, pin):
                yield DRCFinding(
                    Severity.ERROR,
                    "E-PIN-UNKNOWN",
                    f"mate references pin '{pin}' on connector {name}, "
                    f"which has no such pin",
                    name,
                )


@rule("E-WIRE-RANGE")
def _wire_out_of_range(harness):
    """A connection uses a wire number outside 1..wirecount (0, negative, too high)."""
    for cable in harness.cables.values():
        for c in cable.connections:
            vp = c.via_port
            if _is_shield_ref(vp):
                continue
            if not isinstance(vp, int):
                continue  # non-numeric, non-shield -> covered elsewhere
            if vp < 1 or vp > cable.wirecount:
                yield DRCFinding(
                    Severity.ERROR,
                    "E-WIRE-RANGE",
                    f"cable {cable.name} uses wire {vp}, outside the valid "
                    f"range 1..{cable.wirecount}",
                    cable.name,
                )


@rule("E-SHIELD-ABSENT")
def _shield_without_shield(harness):
    """A connection uses shield 's' on a cable that has no shield."""
    for cable in harness.cables.values():
        if cable.shield:
            continue
        for c in cable.connections:
            if _is_shield_ref(c.via_port):
                yield DRCFinding(
                    Severity.ERROR,
                    "E-SHIELD-ABSENT",
                    f"cable {cable.name} connects a shield 's' but the cable "
                    f"has no shield defined",
                    cable.name,
                )
                break


@rule("W-WIRE-UNUSED")
def _unused_wire(harness):
    """A cable wire is never connected at either end."""
    for cable in harness.cables.values():
        used = set()
        for c in cable.connections:
            if isinstance(c.via_port, int):
                used.add(c.via_port)
        missing = [w for w in range(1, (cable.wirecount or 0) + 1) if w not in used]
        if missing:
            pretty = ", ".join(str(w) for w in missing)
            yield DRCFinding(
                Severity.WARNING,
                "W-WIRE-UNUSED",
                f"cable {cable.name} has unconnected wire(s): {pretty}",
                cable.name,
            )


@rule("W-WIRE-OPEN-END")
def _open_wire_end(harness):
    """A wire is terminated on only one end (the other end goes nowhere)."""
    for cable in harness.cables.values():
        for c in cable.connections:
            open_ends = [
                side
                for side, name in (("from", c.from_name), ("to", c.to_name))
                if name is None
            ]
            if len(open_ends) == 1:
                port = "shield" if _is_shield_ref(c.via_port) else c.via_port
                yield DRCFinding(
                    Severity.WARNING,
                    "W-WIRE-OPEN-END",
                    f"cable {cable.name} wire {port} has an open "
                    f"({open_ends[0]}) end",
                    cable.name,
                )


@rule("W-PIN-UNCONNECTED")
def _unconnected_pins(harness):
    """A connector has pins that are never connected to anything."""
    for conn in harness.connectors.values():
        if conn.style == "simple":
            continue
        unconnected = [p for p in conn.pins if p not in conn.visible_pins]
        if unconnected:
            pretty = ", ".join(str(p) for p in unconnected)
            yield DRCFinding(
                Severity.WARNING,
                "W-PIN-UNCONNECTED",
                f"connector {conn.name} has unconnected pin(s): {pretty}",
                conn.name,
            )


@rule("W-LABEL-COUNT")
def _label_count_mismatch(harness):
    """pinlabels / pincolors length disagrees with the pin count."""
    for conn in harness.connectors.values():
        n = len(conn.pins)
        for attr in ("pinlabels", "pincolors"):
            vals = getattr(conn, attr, None) or []
            if vals and len(vals) != n:
                yield DRCFinding(
                    Severity.WARNING,
                    "W-LABEL-COUNT",
                    f"connector {conn.name} has {len(vals)} {attr} for "
                    f"{n} pins (they should match)",
                    conn.name,
                )
    for cable in harness.cables.values():
        wl = cable.wirelabels or []
        if wl and len(wl) != cable.wirecount:
            yield DRCFinding(
                Severity.WARNING,
                "W-LABEL-COUNT",
                f"cable {cable.name} has {len(wl)} wirelabels for "
                f"{cable.wirecount} wires (they should match)",
                cable.name,
            )


@rule("W-NO-GAUGE")
def _missing_gauge(harness):
    """A connected cable has no wire gauge, so cut-sheet/ampacity is incomplete."""
    for cable in harness.cables.values():
        if cable.ignore_in_bom:
            continue
        if not cable.connections:
            continue
        if cable.gauge in (None, "", 0):
            yield DRCFinding(
                Severity.INFO,
                "W-NO-GAUGE",
                f"cable {cable.name} has no gauge; cut sheet and ampacity "
                f"checks will be incomplete",
                cable.name,
            )


@rule("W-ZERO-LENGTH")
def _zero_length(harness):
    """A connected cable has zero length, so the cut sheet can't state a cut length."""
    for cable in harness.cables.values():
        if cable.ignore_in_bom or not cable.connections:
            continue
        if not cable.length:
            yield DRCFinding(
                Severity.INFO,
                "W-ZERO-LENGTH",
                f"cable {cable.name} has zero length; its cut length will "
                f"be reported as 0",
                cable.name,
            )


@rule("I-NO-MPN")
def _missing_part_number(harness):
    """A component has no MPN or internal PN, so it cannot be sourced."""
    for kind, container in (("connector", harness.connectors), ("cable", harness.cables)):
        for comp in container.values():
            if comp.ignore_in_bom:
                continue
            if not comp.mpn and not comp.pn:
                yield DRCFinding(
                    Severity.INFO,
                    "I-NO-MPN",
                    f"{kind} {comp.name} has no MPN or PN; it cannot be "
                    f"looked up at a distributor",
                    comp.name,
                )


# --- runner ----------------------------------------------------------------


def run_drc(harness, min_severity: Severity = Severity.INFO) -> List[DRCFinding]:
    """Run every registered rule over `harness` and return sorted findings.

    Findings are sorted most-severe first, then by rule code, then component.
    Rules that raise are converted into an ERROR finding rather than aborting
    the whole check.
    """
    findings: List[DRCFinding] = []
    for code, fn in RULES.items():
        try:
            findings.extend(fn(harness))
        except Exception as exc:  # noqa: BLE001 - a broken rule must not kill DRC
            findings.append(
                DRCFinding(
                    Severity.ERROR,
                    "E-DRC-INTERNAL",
                    f"rule {code} failed: {type(exc).__name__}: {exc}",
                )
            )
    findings = [f for f in findings if f.severity >= min_severity]
    findings.sort(key=lambda f: (-int(f.severity), f.code, f.component or ""))
    return findings


def format_report(findings: List[DRCFinding]) -> str:
    """Human-readable multi-line report, with a summary count line."""
    counts = {s: 0 for s in Severity}
    for f in findings:
        counts[f.severity] += 1
    lines = [str(f) for f in findings]
    summary = (
        f"DRC: {counts[Severity.ERROR]} error(s), "
        f"{counts[Severity.WARNING]} warning(s), "
        f"{counts[Severity.INFO]} info"
    )
    if lines:
        return "\n".join(lines) + "\n" + summary
    return summary + " — no issues found"


def has_errors(findings: List[DRCFinding]) -> bool:
    return any(f.severity >= Severity.ERROR for f in findings)
