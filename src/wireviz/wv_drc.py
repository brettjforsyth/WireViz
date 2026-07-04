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
from wireviz.wv_electrical import (
    ampacity_for,
    ampacity_margin,
    bundle_derating,
    voltage_drop,
)

# Warn when a wire's current exceeds this fraction of its ampacity.
AMPACITY_WARN_FRACTION = 0.9
# Warn when voltage drop exceeds this percentage of the circuit voltage.
DEFAULT_VDROP_PCT = 5.0


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


@rule("E-AMPACITY")
def _ampacity_exceeded(harness):
    """A wire carries more current than its gauge's ampacity allows.

    Only active when the cable declares a `current`; conservative chassis-
    wiring ampacity is used unless the user overrides the table upstream.
    """
    for cable in harness.cables.values():
        if not cable.current or not cable.gauge:
            continue
        margin = ampacity_margin(cable.current, cable.gauge, cable.gauge_unit)
        amp = ampacity_for(cable.gauge, cable.gauge_unit)
        if margin is None or amp is None:
            continue
        if margin > 1.0:
            yield DRCFinding(
                Severity.ERROR,
                "E-AMPACITY",
                f"cable {cable.name} carries {cable.current} A on "
                f"{cable.gauge} {cable.gauge_unit or ''}".rstrip()
                + f" wire, above its ~{amp} A ampacity",
                cable.name,
            )
        elif margin >= AMPACITY_WARN_FRACTION:
            yield DRCFinding(
                Severity.WARNING,
                "W-AMPACITY-MARGIN",
                f"cable {cable.name} carries {cable.current} A, within "
                f"{round(margin * 100)}% of its ~{amp} A ampacity",
                cable.name,
            )


@rule("W-BUNDLE-DERATE")
def _bundle_derate(harness):
    """A cable's current exceeds its bundle-derated ampacity.

    When many current-carrying wires share a bundle they can't shed heat, so
    ampacity is derated by conductor count. Active only when `current` is set.
    """
    for cable in harness.cables.values():
        if not cable.current or not cable.gauge:
            continue
        amp = ampacity_for(cable.gauge, cable.gauge_unit)
        if amp is None:
            continue
        factor = bundle_derating((cable.wirecount or 1) + (1 if cable.shield else 0))
        if factor < 1.0 and cable.current > amp * factor:
            yield DRCFinding(
                Severity.WARNING,
                "W-BUNDLE-DERATE",
                f"cable {cable.name} carries {cable.current} A, above its "
                f"bundle-derated ampacity ~{round(amp * factor, 1)} A "
                f"(x{factor} for {cable.wirecount} wires)",
                cable.name,
            )


@rule("W-VDROP")
def _voltage_drop(harness):
    """Voltage drop over a wire exceeds the allowed percentage of circuit voltage.

    Only active when the cable declares both `current` and `voltage`.
    """
    for cable in harness.cables.values():
        if not (cable.current and cable.voltage and cable.gauge and cable.length):
            continue
        drop = voltage_drop(
            cable.current, cable.gauge, cable.gauge_unit, float(cable.length)
        )
        if drop is None:
            continue
        pct = drop / cable.voltage * 100
        if pct > DEFAULT_VDROP_PCT:
            yield DRCFinding(
                Severity.WARNING,
                "W-VDROP",
                f"cable {cable.name} drops {drop:.2f} V "
                f"({pct:.1f}% of {cable.voltage} V) over {cable.length} "
                f"{cable.length_unit or 'm'}, above the "
                f"{DEFAULT_VDROP_PCT:.0f}% limit",
                cable.name,
            )


_MALE = {"pin", "plug", "male", "m"}
_FEMALE = {"socket", "receptacle", "female", "f", "jack"}


def _gender_class(g):
    g = (g or "").strip().lower()
    if g in _MALE:
        return "male"
    if g in _FEMALE:
        return "female"
    return None


@rule("E-MATE-PINCOUNT")
def _mate_pincount(harness):
    """Two whole-component-mated connectors must have equal pin counts."""
    for mate in harness.mates:
        if not isinstance(mate, MateComponent):
            continue
        a = harness.connectors.get(mate.from_name)
        b = harness.connectors.get(mate.to_name)
        if a and b and a.pincount != b.pincount:
            yield DRCFinding(
                Severity.ERROR,
                "E-MATE-PINCOUNT",
                f"mated connectors {mate.from_name} ({a.pincount}p) and "
                f"{mate.to_name} ({b.pincount}p) have different pin counts",
                mate.from_name,
            )


@rule("W-MATE-GENDER")
def _mate_gender(harness):
    """Mated connectors should have opposing genders (one male, one female).

    Only active when both connectors declare a gender.
    """
    for mate in harness.mates:
        a = harness.connectors.get(getattr(mate, "from_name", None))
        b = harness.connectors.get(getattr(mate, "to_name", None))
        if not a or not b:
            continue
        ga, gb = _gender_class(a.gender), _gender_class(b.gender)
        if ga and gb and ga == gb:
            yield DRCFinding(
                Severity.WARNING,
                "W-MATE-GENDER",
                f"mated connectors {a.name} and {b.name} are both {ga}; "
                f"mating faces should have opposing genders",
                a.name,
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
