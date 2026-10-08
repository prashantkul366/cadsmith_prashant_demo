"""The features a projected view shows, and therefore has to dimension.

A drawing is dimensioned from what it draws. The dimensioner before this
measured the outline - the bounding box, the circles, the corner radii -
and that is a drawing of the part's envelope rather than of the part.
Measured across every sheet this app has made: 1554 dimensions declared by
the parts, 610 of them printed, 39%.

What it was missing is everything cut into the outline that is not round.
A slit, a slot, a pocket, a window and a cut-out all project as a closed
loop inside the boundary, and the projector hands them over as a heap of
separate edges, so nothing downstream could see them. On the flexible
strip the senior asked about, the five slits were drawn and the sheet said
nothing about any of them: 0.5 wide and 10 long, nowhere on the page.

Chaining those edges back into loops finds them. What it cannot find is a
feature the view does not show - the enclosed channel in a cold plate is
hidden detail, and dimensioning it wants a section view this sheet does
not have. So `undimensioned()` says which of the part's own declared
numbers never reached the page, rather than the sheet implying that what
it shows is all there is.
"""

from __future__ import annotations

import math
import re
from typing import Iterable, Optional

#: Two endpoints are the same point within this, in millimetres. The
#: projector rounds to 1e-3, so this is a few of those.
JOIN_TOL = 5e-3

#: Two features are the same size within this, in millimetres.
SAME_TOL = 0.01

#: Below this a loop is a sliver of the projector's own making rather than
#: a feature anybody would dimension.
MIN_FEATURE = 0.05


def _key(point) -> tuple:
    return (round(point[0], 3), round(point[1], 3))


def loops(lines: Iterable[list]) -> list[list]:
    """Chain projected edges into closed loops.

    The projector emits one polyline per edge, so a rectangular cut-out
    arrives as four unrelated lines and a slot as two lines and two arcs.
    Joined at their endpoints they are a loop, and a loop is a feature.
    """
    lines = [line for line in lines if len(line) > 1]
    ends: dict[tuple, list] = {}
    for index, line in enumerate(lines):
        ends.setdefault(_key(line[0]), []).append((index, False))
        ends.setdefault(_key(line[-1]), []).append((index, True))

    used: set[int] = set()
    found: list[list] = []
    for start in range(len(lines)):
        if start in used:
            continue
        chain = list(lines[start])
        used.add(start)
        while True:
            here = _key(chain[-1])
            step = next(((i, rev) for i, rev in ends.get(here, [])
                         if i not in used), None)
            if step is None:
                break
            index, reverse = step
            used.add(index)
            piece = lines[index][::-1] if reverse else lines[index]
            chain.extend(piece[1:])
            if _key(chain[-1]) == _key(chain[0]):
                break
        if len(chain) > 3 and _key(chain[-1]) == _key(chain[0]):
            found.append(chain)
    return found


def bbox(loop) -> tuple[float, float, float, float]:
    us = [p[0] for p in loop]
    vs = [p[1] for p in loop]
    return min(us), min(vs), max(us), max(vs)


def _area(loop) -> float:
    """Twice the signed area, by the shoelace formula - sign discarded."""
    total = 0.0
    for (ax, av), (bx, bv) in zip(loop, loop[1:]):
        total += ax * bv - bx * av
    return abs(total) / 2.0


def _straight(loop) -> bool:
    """Whether every segment of this loop is axis-aligned."""
    for (ax, av), (bx, bv) in zip(loop, loop[1:]):
        if abs(ax - bx) > SAME_TOL and abs(av - bv) > SAME_TOL:
            return False
    return True


def classify(loop) -> dict:
    """What this loop is, as far as a dimension is concerned.

    Three answers, because they take three different dimensions. A circle
    takes a diameter and is already called out by the circle pass, so it is
    named here only to be left alone. A rectangle takes a width and a
    height. Anything else takes the size of the box around it, which is
    what a draughtsman writes when a shape is given by its outline.
    """
    umin, vmin, umax, vmax = bbox(loop)
    width, height = umax - umin, vmax - vmin
    out = {"u": (umin + umax) / 2.0, "v": (vmin + vmax) / 2.0,
           "w": width, "h": height, "area": _area(loop),
           "bbox": (umin, vmin, umax, vmax)}
    if width < MIN_FEATURE or height < MIN_FEATURE:
        out["kind"] = "sliver"
        return out
    # A circle fills π/4 of its box; a rectangle fills all of it. Measured
    # rather than assumed, because a projected hole arrives as two
    # half-edges and a rectangle with rounded corners is neither.
    fill = out["area"] / (width * height) if width * height else 0.0
    if abs(width - height) <= SAME_TOL and abs(fill - math.pi / 4) < 0.02:
        out["kind"] = "circle"
    elif _straight(loop):
        out["kind"] = "rectangle"
    elif fill > 0.97:
        out["kind"] = "rectangle"
    else:
        out["kind"] = "shape"
    return out


def cutouts(view: dict) -> list[dict]:
    """Every feature cut into this view's outline, largest first.

    The outline itself is the loop of greatest area and is excluded: it is
    the part's envelope, which the overall dimensions already carry.
    Circles are excluded too - the circle pass calls those out with a
    diameter and a centre line, and a second dimension across the same hole
    is the sheet contradicting itself.
    """
    found = [classify(loop) for loop in loops(view.get("visible") or [])]
    found = [f for f in found if f["kind"] not in ("sliver", "circle")]
    if not found:
        return []
    found.sort(key=lambda f: f["area"], reverse=True)
    return found[1:] if len(found) > 1 else []


def groups(found: Iterable[dict]) -> list[dict]:
    """Features of the same size, counted and spaced.

    Five identical slits are one dimension and a count, not five
    dimensions: that is both what ISO 129-1 asks for and the difference
    between a sheet somebody reads and a sheet covered in the same number.
    """
    out: list[dict] = []
    for feature in found:
        for group in out:
            if (abs(group["w"] - feature["w"]) <= SAME_TOL
                    and abs(group["h"] - feature["h"]) <= SAME_TOL
                    and group["kind"] == feature["kind"]):
                group["members"].append(feature)
                break
        else:
            out.append({**feature, "members": [feature]})
    for group in out:
        group["count"] = len(group["members"])
        group["pitch_u"] = _pitch([m["u"] for m in group["members"]])
        group["pitch_v"] = _pitch([m["v"] for m in group["members"]])
    return out


def _pitch(values: list[float]) -> float:
    """The spacing of an evenly spaced row, or 0 if it is not one."""
    ordered = sorted(round(v, 3) for v in values)
    if len(ordered) < 2:
        return 0.0
    steps = [b - a for a, b in zip(ordered, ordered[1:])]
    if min(steps) < MIN_FEATURE:
        return 0.0
    return round(steps[0], 3) if max(steps) - min(steps) <= SAME_TOL else 0.0


def printed(sheet: dict) -> list[float]:
    """Every number this sheet actually prints, and only those.

    Literally what is on the page. An earlier version also counted half of
    every diameter, on the reasoning that a part declaring a radius is
    answered by a sheet printing the diameter of the same feature - which
    is true, and still not worth it: it also meant a Ø10 anywhere made
    every declared 5 look covered, so a 5 mm pocket depth went unreported
    against a hole it had nothing to do with. Reporting something as
    missing that is arguably shown is a line somebody reads and dismisses;
    the other way round is a check that quietly passes everything.
    """
    out: list[float] = []
    for view in sheet.get("views", []):
        for dimension in view.get("dimensions", []):
            out.append(float(dimension["measure"]))
            out.extend(_in_text(dimension.get("label")))
        for call in view.get("callouts", []):
            out.append(float(call["measure"]))
            # And every number inside the leader's own text. A hole's
            # callout reads "4x O6.6 THRU (cbore) O11 x 6.5", and its
            # `measure` is only the 6.6 - so the depth and the counterbore
            # it also prints were invisible to this. Which is how adding
            # both to the sheet made the coverage figure go *down*: the
            # Ø11 leader they replaced had been counted and the richer
            # callout that replaced it was not.
            out.extend(_in_text(call.get("label")))
    return out


#: A number in a callout, which is where a depth or a counterbore is
#: written. Not preceded by a digit, so the 25 of M8x1.25 is one number
#: rather than two, and not the count in "4x".
_NUMBER = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)(?!\s*\u00d7)")


def _in_text(label) -> list[float]:
    """Every number a piece of annotation prints."""
    if not isinstance(label, str) or not label:
        return []
    return [float(found) for found in _NUMBER.findall(label)]


def undimensioned(sheet: dict, parameters: Iterable[dict],
                  tol: float = 0.02) -> list[str]:
    """Which of the part's declared lengths never reached the page.

    Not a fault list. Some of these should not be on a sheet at all: a
    tapping drill diameter is implied by the thread callout beside it, and
    a clearance is a number the model used rather than one a machinist
    works to. It is the honest answer to "is this drawing enough to make
    the part from", which is a question the sheet could not previously be
    asked.
    """
    numbers = printed(sheet)

    def shown(value: float) -> bool:
        return any(abs(value - n) <= max(tol, abs(value) * 0.005)
                   for n in numbers)

    return [p["name"] for p in parameters
            if p.get("kind") == "length" and not shown(float(p["value"]))]
