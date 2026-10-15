"""What the model may ask NX to do, and what NX says back.

This is the server's half of the NX plugin: the vocabulary of operations,
the shape of a feature tree as the plugin reports it, and the checking
that happens before anything is sent to be performed. Nothing here
imports NX or talks to it. The plugin inside NX performs the operations;
this decides which ones to ask for and refuses the ones that are wrong
before they reach a part.

That split is not tidiness. There is no NX in this development
environment, so code that needs one cannot be run, cannot be tested and
cannot be trusted. Everything on this side of the line can be all three.

**The operations are NX's own.** `extrude` is an NX extrude of a sketch,
`hole` is the NX Hole feature with its own callout, `edit_expression`
changes the expression that drives a feature. Nothing is modelled as a
boolean against a cylinder, because NX has a Hole feature and a hole that
is a feature carries its depth, its thread and its counterbore into the
drawing, while a subtracted cylinder carries none of it.

**An expression is the handle on an existing part.** NX names a feature's
parameters p1, p2 and so on, and each one's description says which
feature and which parameter it drives - `p7 (Simple Hole(12) Diameter)`.
That is what makes "open the mounting holes to 11" a thing the model can
do to a part somebody else designed: it does not need to know how the
part was built, only which expression drives the diameter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

#: Where a sketch is drawn, in the names NX uses for its datum planes.
PLANES = ("XY", "XZ", "YZ")

#: How far an extrude goes, in NX's own terms.
EXTENTS = ("value", "through_all", "to_face", "symmetric")

#: What a hole is for. NX's Hole feature carries this, and the drawing
#: reads it: a tapped M8 is drilled 6.8 and called out M8, and a
#: clearance hole for the same screw is drilled 9 and called out as 9.
HOLE_KINDS = ("simple", "counterbored", "countersunk", "threaded")


class NXToolError(ValueError):
    """An operation that must not be sent to NX.

    Raised before anything reaches the part, so the model is told what
    was wrong with the request rather than NX being told to do it and
    the engineer watching it fail.
    """


@dataclass
class Operation:
    """One thing for the plugin to do, and why it was asked for."""

    name: str
    arguments: dict
    #: What the model expects to be true afterwards, in its own words.
    #: Carried through so a failure can say which intention was not met
    #: rather than only which call returned an error.
    intent: str = ""

    def as_json(self) -> dict:
        return {"name": self.name, "arguments": self.arguments,
                "intent": self.intent}


@dataclass
class Expression:
    """One NX expression, as the plugin reports it.

    `description` is NX's own, and is the only thing that says what the
    expression means: `p7 (Simple Hole(12) Diameter)`. Without it a tree
    of p1..p40 is unreadable by anything, model or person.
    """

    name: str
    value: float
    units: str = "mm"
    description: str = ""
    #: An expression driven by a formula is not a number to set. Writing
    #: a value over `width/2` silently breaks the relationship the
    #: designer put there, which is worse than refusing.
    formula: str = ""

    @property
    def driven(self) -> bool:
        return bool(self.formula) and self.formula.strip() not in (
            "", str(self.value), f"{self.value:g}")

    def means(self) -> str:
        """The feature and parameter this drives, from NX's description."""
        inside = self.description
        if "(" in inside and inside.rstrip().endswith(")"):
            inside = inside[inside.index("(") + 1:inside.rstrip().rindex(")")]
        return inside.strip()


@dataclass
class Feature:
    """One feature of the part, as the plugin reports it."""

    name: str
    kind: str
    #: NX's own timestamp ordering. A part is its features in order, and
    #: an operation that inserts one has to say where.
    timestamp: int = 0
    suppressed: bool = False
    expressions: list = field(default_factory=list)

    def numbers(self) -> dict:
        return {e.name: e.value for e in self.expressions}


@dataclass
class Tree:
    """The part as the plugin found it."""

    part: str = ""
    features: list = field(default_factory=list)
    expressions: list = field(default_factory=list)
    units: str = "mm"

    def feature(self, name: str) -> Optional[Feature]:
        lowered = name.strip().lower()
        for one in self.features:
            if one.name.lower() == lowered:
                return one
        return None

    def expression(self, name: str) -> Optional[Expression]:
        lowered = name.strip().lower()
        for one in self.expressions:
            if one.name.lower() == lowered:
                return one
        return None

    def summary(self) -> str:
        """The part in the fewest words a model can work from.

        Sent at the top of every turn, so it is written to be read by a
        small model as much as a large one: one line per feature, the
        numbers that drive it beside it, and nothing else.
        """
        lines = [f"part {self.part or '(unnamed)'}, {self.units}"]
        for one in sorted(self.features, key=lambda f: f.timestamp):
            numbers = ", ".join(
                f"{e.name}={e.value:g}" + (f" [{e.formula}]" if e.driven else "")
                for e in one.expressions)
            lines.append(
                f"  {one.name} ({one.kind})"
                + (" SUPPRESSED" if one.suppressed else "")
                + (f": {numbers}" if numbers else ""))
        loose = [e for e in self.expressions
                 if not any(e.name == x.name
                            for f in self.features for x in f.expressions)]
        if loose:
            lines.append("  expressions not tied to one feature: "
                         + ", ".join(f"{e.name}={e.value:g}" for e in loose))
        return "\n".join(lines)


def tree_from(raw: dict) -> Tree:
    """The tree the plugin sent, as something to reason about.

    Tolerant on purpose. This arrives over HTTP from code running inside
    somebody's NX, and a missing field should cost that field rather than
    the turn.
    """
    def expressions(items) -> list:
        out = []
        for item in items or []:
            try:
                out.append(Expression(
                    name=str(item.get("name") or ""),
                    value=float(item.get("value") or 0.0),
                    units=str(item.get("units") or "mm"),
                    description=str(item.get("description") or ""),
                    formula=str(item.get("formula") or "")))
            except (TypeError, ValueError):
                continue
        return [e for e in out if e.name]

    features = []
    for item in raw.get("features") or []:
        features.append(Feature(
            name=str(item.get("name") or ""),
            kind=str(item.get("kind") or item.get("type") or "unknown"),
            timestamp=int(item.get("timestamp") or 0),
            suppressed=bool(item.get("suppressed")),
            expressions=expressions(item.get("expressions"))))
    return Tree(part=str(raw.get("part") or ""),
                features=[f for f in features if f.name],
                expressions=expressions(raw.get("expressions")),
                units=str(raw.get("units") or "mm"))


# ---------------------------------------------------------------------------
# The operations, and what has to be true before one is sent
# ---------------------------------------------------------------------------

class _Asked:
    """One operation's arguments, checked without stopping at the first
    thing that is wrong.

    A model that forgets a hole's position and its thread should be told
    both, not told about the position, fix it, and be told about the
    thread on the next turn. Each wrong thing is a turn, and a turn is a
    model call and the engineer waiting through it.
    """

    def __init__(self, arguments: dict, tree: "Tree") -> None:
        self.arguments = arguments if isinstance(arguments, dict) else {}
        self.tree = tree
        self.wrong: list = []

    def complain(self, said: str) -> None:
        if said not in self.wrong:
            self.wrong.append(said)

    def number(self, key: str, *, positive: bool = True,
               required: bool = True, default: float = 0.0) -> float:
        if self.arguments.get(key) is None:
            if required:
                self.complain(f"{key} is required, in millimetres")
            return default
        try:
            value = float(self.arguments[key])
        except (TypeError, ValueError):
            self.complain(f"{key} must be a number, "
                          f"not {self.arguments[key]!r}")
            return default
        if positive and value <= 0:
            self.complain(f"{key} must be greater than zero, not {value:g}")
            return default
        return value

    def one_of(self, key: str, allowed: tuple, default: str = "") -> str:
        value = str(self.arguments.get(key) or default).strip() or default
        for choice in allowed:
            if value.upper() == choice.upper():
                return choice
        self.complain(f"{key} is one of " + ", ".join(allowed)
                      + f"; got {value!r}")
        return default

    def text(self, key: str, why: str) -> str:
        value = str(self.arguments.get(key) or "").strip()
        if not value:
            self.complain(why)
        return value

    def points(self, key: str = "points") -> list:
        raw = self.arguments.get(key)
        if not isinstance(raw, (list, tuple)) or len(raw) < 3:
            self.complain(f"{key} is at least three [x, y] corners")
            return []
        out = []
        for point in raw:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                self.complain(f"each of {key} is [x, y], got {point!r}")
                return []
            try:
                out.append((float(point[0]), float(point[1])))
            except (TypeError, ValueError):
                self.complain(f"{key} must be numbers, got {point!r}")
                return []
        if len(set(out)) != len(out):
            self.complain("the outline repeats a corner, so it crosses itself")
        return out

    def settled(self) -> None:
        if self.wrong:
            raise NXToolError("; ".join(self.wrong))


def _check_sketch_extrude(asked: "_Asked") -> dict:
    points = asked.points()
    extent = asked.one_of("extent", EXTENTS, "value")
    checked = {"points": [list(p) for p in points],
               "plane": asked.one_of("plane", PLANES, "XY"),
               "extent": extent,
               "offset": asked.number("offset", positive=False,
                                      required=False)}
    if extent in ("value", "symmetric"):
        checked["distance"] = asked.number("distance")
    if asked.arguments.get("subtract"):
        checked["subtract"] = True
    return checked


def _check_hole(asked: "_Asked") -> dict:
    kind = asked.one_of("kind", HOLE_KINDS, "simple")
    checked = {
        "kind": kind,
        "diameter": asked.number("diameter"),
        "at": [asked.number("x", positive=False),
               asked.number("y", positive=False),
               asked.number("z", positive=False)],
        "direction": asked.one_of("direction",
                                  ("+X", "-X", "+Y", "-Y", "+Z", "-Z"), "-Z"),
        "through_all": bool(asked.arguments.get("through_all")),
    }
    if not checked["through_all"]:
        checked["depth"] = asked.number("depth")
    if kind == "counterbored":
        checked["counterbore_diameter"] = asked.number("counterbore_diameter")
        checked["counterbore_depth"] = asked.number("counterbore_depth")
        if 0 < checked["counterbore_diameter"] <= checked["diameter"]:
            asked.complain(
                "a counterbore is wider than the hole it sits over: "
                f'{checked["counterbore_diameter"]:g} is not wider than '
                f'{checked["diameter"]:g}')
    if kind == "countersunk":
        checked["countersink_diameter"] = asked.number("countersink_diameter")
        checked["countersink_angle"] = asked.number("countersink_angle")
        if checked["countersink_angle"] and not (
                60 <= checked["countersink_angle"] <= 120):
            asked.complain("countersink_angle is the included angle in "
                           "degrees, usually 90 for a metric screw")
    if kind == "threaded":
        checked["thread"] = asked.text(
            "thread", "a threaded hole needs thread, e.g. M8x1.25")
    return checked


def _check_edit_expression(asked: "_Asked") -> dict:
    name = asked.text("name", "name is the expression to change, e.g. p7")
    value = asked.number("value", positive=False)
    if not name:
        return {}
    found = asked.tree.expression(name)
    if found is None:
        # The names it does have, because a model told only "no such
        # expression" guesses again, and one told what there is picks.
        known = ", ".join(
            f"{e.name} ({e.means()})" if e.means() else e.name
            for e in asked.tree.expressions[:12]) or "none were reported"
        asked.complain(f"this part has no expression called {name!r}. "
                       f"It has: {known}")
        return {}
    if found.driven:
        asked.complain(
            f"{name} is driven by the formula {found.formula!r}, so a value "
            "written over it would break the relation the designer put "
            "there. Change what the formula depends on, or say that the "
            "relation should go.")
        return {}
    return {"name": found.name, "value": value}


def _check_named(asked: "_Asked") -> dict:
    name = asked.text("name", "name is the feature to act on")
    if not name:
        return {}
    if asked.tree.features and asked.tree.feature(name) is None:
        known = ", ".join(f.name for f in asked.tree.features[:12])
        asked.complain(f"this part has no feature called {name!r}. "
                       f"It has: {known}")
        return {}
    found = asked.tree.feature(name)
    return {"name": found.name if found else name}


def _check_suppress(asked: "_Asked") -> dict:
    checked = _check_named(asked)
    checked["suppressed"] = bool(asked.arguments.get("suppressed", True))
    return checked


def _check_edge_blend(asked: "_Asked") -> dict:
    return {"radius": asked.number("radius"),
            "where": asked.one_of("where",
                                  ("all", "top", "bottom", "vertical"), "all")}


def _check_chamfer(asked: "_Asked") -> dict:
    return {"distance": asked.number("distance"),
            "where": asked.one_of("where",
                                  ("all", "top", "bottom", "vertical"), "all")}


#: Every operation the plugin knows how to perform, what it is for, and
#: what has to be true of its arguments. The description is what a model
#: reads, so it says when to reach for the operation rather than only
#: what it does.
OPERATIONS: dict = {
    "read_part": {
        "describes": "Report the feature tree and expressions again. Only "
                     "needed after something outside this conversation "
                     "changed the part; the tree is sent at the start of "
                     "every turn.",
        "check": lambda asked: {},
    },
    "sketch_extrude": {
        "describes": "Draw a closed outline on a datum plane and extrude "
                     "it. How most parts start, and how a boss or a pocket "
                     "is added to one. points are [x, y] corners in order; "
                     "subtract removes the material instead of adding it.",
        "check": _check_sketch_extrude,
    },
    "hole": {
        "describes": "An NX Hole feature - not a cylinder subtracted from "
                     "the solid. The feature carries the thread, the "
                     "counterbore and the depth, and the drawing reads "
                     "them; a subtracted cylinder carries none of it and "
                     "the drawing has to guess.",
        "check": _check_hole,
    },
    "edit_expression": {
        "describes": "Change the number that drives a feature. This is how "
                     "an existing part is changed: find the expression "
                     "whose description names the feature and parameter - "
                     "'p7 (Simple Hole(12) Diameter)' - and set it. Works "
                     "on parts this app did not build.",
        "check": _check_edit_expression,
    },
    "suppress_feature": {
        "describes": "Take a feature out of the part without deleting it, "
                     "or put it back - what a person does to ask what the "
                     "part would be like without it.",
        "check": _check_suppress,
    },
    "delete_feature": {
        "describes": "Remove a feature from the part for good. Prefer "
                     "suppressing it unless the engineer asked for it to "
                     "go.",
        "check": _check_named,
    },
    "edge_blend": {
        "describes": "Round edges - NX's Edge Blend. where picks which "
                     "edges: all of them, or only the top, bottom or "
                     "vertical ones.",
        "check": _check_edge_blend,
    },
    "chamfer": {
        "describes": "Break edges at 45 degrees - NX's Chamfer.",
        "check": _check_chamfer,
    },
}


def definitions() -> list:
    """The operations as a model is told about them."""
    return [{"name": name, "description": entry["describes"]}
            for name, entry in OPERATIONS.items()]


def checked(name: str, arguments: dict, tree: Optional[Tree] = None
            ) -> Operation:
    """One operation, refused here if it is wrong rather than by NX.

    A refusal that reaches the model as a sentence costs a turn. A
    refusal that reaches NX costs the engineer's part, or their
    confidence in it, which is dearer.
    """
    entry = OPERATIONS.get(name)
    if entry is None:
        raise NXToolError(f"there is no operation called {name!r}. There is: "
                          + ", ".join(OPERATIONS))
    if not isinstance(arguments, dict):
        raise NXToolError(f"{name} takes named arguments, not {arguments!r}")
    asked = _Asked(arguments, tree or Tree())
    checked_arguments = entry["check"](asked)
    asked.settled()
    return Operation(name=name, arguments=checked_arguments,
                     intent=str(arguments.get("intent") or "").strip())
