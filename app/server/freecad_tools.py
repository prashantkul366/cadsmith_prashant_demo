"""The tools a model may use to build a part in FreeCAD.

Three layers, and the ordering is the design.

**The catalogue, at the top.** ``place_standard_part`` reaches the same
router that answers "a drag bar" with no model call at all - except here the
part lands *inside* a FreeCAD document, so an agent can build around
something already verified. That is the one capability neither system has
alone: today "a drag bar" short-circuits the agents entirely and "a mounting
bracket for a drag bar" cannot be helped at all.

**Features in the middle.** ``find_features`` and ``resize_hole`` reach
``direct.py``, which names things the way a drawing does - "4x Ø8.5 through
hole, rectangular pattern 90 x 50" - rather than the way FreeCAD does. A
model that can say "the mounting holes" does not have to guess an object
name, and a selector resolved against the current solid cannot go stale.

**FreeCAD primitives at the bottom**, as the escape hatch. Reached when the
layers above do not cover it, which for a genuinely new shape is often.

Every tool answers with what it measured. Not ``{"ok": true}`` but the
bounding box, the volume, the hole that actually got made. That is what lets
a model correct itself at step two instead of failing at step eight, and it
costs nothing because FreeCAD knows the numbers anyway.

``run_python`` is the widest door and is offered deliberately: FreeCAD's API
is far larger than any vocabulary worth writing out, and a sketch-driven pad
or a loft has no primitive to call. It is last in the list because a model
reaches for the first thing that fits, and the narrow tools are the ones
whose results can be trusted without reading the code.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from app.server import freecad
from app.server.toolbox import Tool, ToolError, Toolbox

#: FreeCAD types worth naming. Not a limit - ``run_python`` reaches the rest -
#: but the ones a part is usually made of, with the properties each needs.
PRIMITIVES = {
    "Part::Box": ("Length", "Width", "Height"),
    "Part::Cylinder": ("Radius", "Height"),
    "Part::Sphere": ("Radius",),
    "Part::Cone": ("Radius1", "Radius2", "Height"),
    "Part::Torus": ("Radius1", "Radius2"),
}
# Part::Tube was offered here and FreeCAD has no such object type: every
# call to it came back "'Part::Tube' is not a document object type", which
# reads as the model making something up when it was the list that was
# wrong. A tube is a revolved half-section anyway - revolve_profile draws
# one from four corners, and keeps the Angle adjustable while it does.

#: The three principal planes, oriented as FreeCAD orients its own origin
#: planes, with the direction a pad grows in. A profile drawn on XZ reads
#: X across and Y up the page and comes towards you, which is what somebody
#: sketching a side elevation means.
PLANES = {
    "XY": {"rotation": (0.0, 0.0, 0.0, 1.0), "reversed": False},
    "XZ": {"rotation": (0.7071067811865476, 0.0, 0.0, 0.7071067811865476),
           "reversed": True},
    "YZ": {"rotation": (0.5, 0.5, 0.5, 0.5), "reversed": False},
}

#: Tapping drill and clearance drill for the coarse metric threads a part
#: actually uses, from ISO 262 and ISO 273 (medium fit). A tapped M8 hole is
#: drilled 6.8 and a clearance M8 hole is drilled 9: the geometry of the two
#: is nothing alike, and neither is the callout, and a model that is handed
#: "M8" and left to guess picks 8 - which is the one size it is never.
THREADS = {
    "M3": {"tap": 2.5, "clear": 3.4, "pitch": 0.5},
    "M4": {"tap": 3.3, "clear": 4.5, "pitch": 0.7},
    "M5": {"tap": 4.2, "clear": 5.5, "pitch": 0.8},
    "M6": {"tap": 5.0, "clear": 6.6, "pitch": 1.0},
    "M8": {"tap": 6.8, "clear": 9.0, "pitch": 1.25},
    "M10": {"tap": 8.5, "clear": 11.0, "pitch": 1.5},
    "M12": {"tap": 10.2, "clear": 13.5, "pitch": 1.75},
    "M16": {"tap": 14.0, "clear": 17.5, "pitch": 2.0},
    "M20": {"tap": 17.5, "clear": 22.0, "pitch": 2.5},
    "M24": {"tap": 21.0, "clear": 26.0, "pitch": 3.0},
}

#: A thread written the way a drawing writes it: M8, M8x1.25, M8 x 1.25,
#: M8-1.25, M8×1.25. The table above is keyed on the diameter alone, and a
#: tool that answers only to "M8" is a tool nothing can hit: every one of
#: the sixty-one library prompts quotes the pitch, so a model asked to tap
#: an "M5x0.8" hole passes exactly that and is told it is not a thread.
_THREAD_CALL = re.compile(
    r"^\s*M\s*(\d+(?:\.\d+)?)\s*(?:[x\u00d7*\-]\s*(\d+(?:\.\d+)?))?\s*$",
    re.I)


def thread_drills(designation: str) -> Optional[dict]:
    """The tapping and clearance drills for a thread, pitch and all.

    The pitch is not thrown away. The tapping drill is the major diameter
    less the pitch - which is what the ISO 262 table in ``THREADS`` is,
    checked row by row - so reading the quoted pitch costs nothing on a
    coarse thread and is the difference between right and wrong on a fine
    one: M20x1.5 taps 18.5, where its coarse row would say 17.5.

    Clearance is by diameter alone, because a screw's shank does not care
    what pitch is on it.

    None for anything that is not an ISO metric thread; the caller says so
    in its own words, with the list.
    """
    found = _THREAD_CALL.match(designation or "")
    if not found:
        return None
    major = float(found.group(1))
    row = THREADS.get("M%g" % major)
    if row is None:
        return None
    pitch = float(found.group(2)) if found.group(2) else float(row["pitch"])
    # A pitch nothing in the standard range would be is a typo, not a
    # thread: refuse it rather than drilling whatever it works out to.
    if not 0.2 <= pitch <= 0.4 * major:
        return None
    # The standard's own row wins where the quoted pitch is the coarse one:
    # D - P gives 6.75 for an M8 and a shop drills 6.8, which is the row.
    # Off the coarse pitch there is no row, so D - P it is, to a tenth -
    # which is a stock drill for every fine pitch in this range.
    tap = (float(row["tap"]) if abs(pitch - float(row["pitch"])) < 1e-9
           else round(major - pitch, 1))
    return {"tap": tap, "clear": float(row["clear"]), "pitch": pitch,
            "name": "M%g" % major if not found.group(2)
                    else "M%gx%g" % (major, pitch)}


#: Booleans, by the name a person uses rather than the FreeCAD class.
BOOLEANS = {"cut": "Part::Cut", "union": "Part::MultiFuse",
            "intersect": "Part::MultiCommon"}


import math


def _rounded(points: list) -> list:
    # A corner with a radius becomes a tangent arc between two shortened
    # sides. Worked out here rather than asked of the Sketcher, because a
    # sketch fillet wants constraints and a solved sketch, and what is
    # wanted is one deterministic outline.
    #
    # This is also what gives a full-round end: two 90 degree corners whose
    # radius is half the width have coincident tangent points, so the side
    # between them vanishes and the two arcs meet as a semicircle. An
    # obround, a radiused plate corner and a rounded tab are all the same
    # operation at different radii.
    n = len(points)
    out = []                       # ("line", a, b) or ("arc", c, r, a0, a1)
    ends = []                      # where each corner starts and finishes
    for i in range(n):
        prev = points[i - 1]
        here = points[i]
        nxt = points[(i + 1) % n]
        # A radius marked "next" belongs to the side leaving this corner,
        # not to the corner itself. Rounding the corner as well moved the
        # arc's own endpoints, so the circle it was asked for no longer
        # passed through them and the outline came apart.
        on_the_side = len(here) > 3 and str(here[3]).lower() == "next"
        r = float(here[2]) if len(here) > 2 and not on_the_side else 0.0
        bx, by = float(here[0]), float(here[1])
        if r <= 0:
            ends.append(((bx, by), (bx, by), None))
            continue
        ax, ay = float(prev[0]) - bx, float(prev[1]) - by
        cx, cy = float(nxt[0]) - bx, float(nxt[1]) - by
        la, lc = math.hypot(ax, ay), math.hypot(cx, cy)
        if la < 1e-9 or lc < 1e-9:
            ends.append(((bx, by), (bx, by), None))
            continue
        ax, ay, cx, cy = ax / la, ay / la, cx / lc, cy / lc
        cosang = max(-1.0, min(1.0, ax * cx + ay * cy))
        half = math.acos(cosang) / 2.0
        if half < 1e-6 or abs(half - math.pi / 2.0) < 1e-9:
            ends.append(((bx, by), (bx, by), None))   # straight through
            continue
        reach = r / math.tan(half)
        # Equality is allowed: an arc that eats a whole side leaves a
        # zero-length line, which is dropped below. That is a knuckle
        # ending in a semicircle, or a tab whose round reaches the corner
        # it starts from - ordinary shapes, and they were being refused
        # for needing exactly as much room as they had.
        if reach > la + 1e-9 or reach > lc + 1e-9:
            raise ToolError(
                "R%g will not fit on the corner at (%g, %g): it needs %.2f mm "
                "of each side and has %.2f. Use a smaller radius."
                % (r, bx, by, reach, min(la, lc)))
        t1 = (bx + ax * reach, by + ay * reach)
        t2 = (bx + cx * reach, by + cy * reach)
        mx, my = ax + cx, ay + cy
        ml = math.hypot(mx, my)
        span = r / math.sin(half)
        centre = (bx + mx / ml * span, by + my / ml * span)
        ends.append((t1, t2, (centre, r)))

    for i in range(n):
        _, leave, corner = ends[i]
        arrive, _, _ = ends[(i + 1) % n]
        bulge = (float(points[i][2])
                 if len(points[i]) > 3 and str(points[i][3]).lower() == "next"
                 else 0.0)
        if corner is not None and not bulge:
            (ccx, ccy), r = corner
            t1, t2, _ = ends[i]
            a0 = math.atan2(t1[1] - ccy, t1[0] - ccx)
            a1 = math.atan2(t2[1] - ccy, t2[0] - ccx)
            # FreeCAD sweeps an arc anticlockwise from the first angle, and
            # a corner never turns more than a half circle - so if going
            # that way is the long way round, the ends are the other way up.
            if (a1 - a0) % (2.0 * math.pi) > math.pi:
                a0, a1 = a1, a0
            out.append(("arc", (ccx, ccy), r, a0, a1))
        gap = math.hypot(arrive[0] - leave[0], arrive[1] - leave[1])
        if bulge:
            # The side to the next corner is an arc rather than a straight
            # line. A corner radius can only round where two sides meet;
            # this is the other thing a drawing asks for - the tangent
            # transition on a tensile specimen, the bottom of a stator
            # slot, the U-turn of a cooling channel. The sign says which
            # way it bows: positive to the left of the direction of
            # travel, negative to the right.
            r = abs(bulge)
            if gap < 1e-9:
                continue
            if r < gap / 2.0 - 1e-9:
                raise ToolError(
                    "R%g cannot reach from (%g, %g) to (%g, %g): those are "
                    "%.2f mm apart, and an arc between them needs a radius "
                    "of at least half that." % (r, leave[0], leave[1],
                                                arrive[0], arrive[1], gap))
            mx, my = (leave[0] + arrive[0]) / 2.0, (leave[1] + arrive[1]) / 2.0
            dx, dy = (arrive[0] - leave[0]) / gap, (arrive[1] - leave[1]) / gap
            off = math.sqrt(max(0.0, r * r - (gap / 2.0) ** 2))
            side = 1.0 if bulge > 0 else -1.0
            ccx, ccy = mx - dy * off * side, my + dx * off * side
            a0 = math.atan2(leave[1] - ccy, leave[0] - ccx)
            a1 = math.atan2(arrive[1] - ccy, arrive[0] - ccx)
            if side < 0:
                a0, a1 = a1, a0
            out.append(("arc", (ccx, ccy), r, a0, a1))
        elif gap > 1e-7:
            out.append(("line", leave, arrive))
    return out


def _crosses_itself(points: list) -> Optional[tuple]:
    """The first pair of sides of a closed outline that intersect.

    A crossing outline is the one mistake FreeCAD does not refuse: it pads a
    bow-tie into a solid that measures, exports and draws, and is not the
    part anybody asked for. Cheap to check here - a few dozen sides at
    worst - and the refusal can say which two sides to look at.
    """
    count = len(points)

    def sides(i):
        return points[i], points[(i + 1) % count]

    def turn(o, a, b):
        return ((a[0] - o[0]) * (b[1] - o[1])
                - (a[1] - o[1]) * (b[0] - o[0]))

    for i in range(count):
        a1, a2 = sides(i)
        for j in range(i + 1, count):
            # Sides that share a corner meet there and that is not a crossing.
            if j == i or (j + 1) % count == i or (i + 1) % count == j:
                continue
            b1, b2 = sides(j)
            d1, d2 = turn(a1, a2, b1), turn(a1, a2, b2)
            d3, d4 = turn(b1, b2, a1), turn(b1, b2, a2)
            if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
                return (i, j)
    return None


def properties_of(described: dict) -> dict:
    """The properties in an object as the addon describes it."""
    return described.get("Properties") or {}


#: The helpers every modelling script opens with. Flush left and
#: concatenated rather than interpolated into an indented template - see
#: freecad._TIPS for what happens otherwise.
_PARTDESIGN = """
import FreeCAD, Part, Sketcher, json

_PLANES = {
    "XY": ((0.0, 0.0, 0.0, 1.0), False),
    "XZ": ((0.7071067811865476, 0.0, 0.0, 0.7071067811865476), True),
    "YZ": ((0.5, 0.5, 0.5, 0.5), False),
}


def _placement(plane, offset):
    quaternion, _ = _PLANES[plane]
    rotation = FreeCAD.Rotation(*quaternion)
    along = rotation.multVec(FreeCAD.Vector(0, 0, 1)) * float(offset)
    return FreeCAD.Placement(along, rotation)


def _reversed(plane):
    return _PLANES[plane][1]


def _outline(sketch, pieces):
    # Handed lines and arcs already worked out, so the only thing done in
    # FreeCAD is the drawing. The corner maths lives in Python where it can
    # be checked against arithmetic without a FreeCAD to run it.
    for piece in pieces:
        if piece[0] == "line":
            (ax, ay), (bx, by) = piece[1], piece[2]
            sketch.addGeometry(Part.LineSegment(
                FreeCAD.Vector(ax, ay, 0), FreeCAD.Vector(bx, by, 0)), False)
        else:
            _, (ccx, ccy), r, a0, a1 = piece
            sketch.addGeometry(Part.ArcOfCircle(
                Part.Circle(FreeCAD.Vector(ccx, ccy, 0),
                            FreeCAD.Vector(0, 0, 1), r), a0, a1), False)


def _check(feature, complaint):
    shape = getattr(feature, "Shape", None)
    if shape is None or shape.isNull() or shape.Volume <= 1e-9:
        # Take the half-made feature out before complaining. Left in, it is
        # an object with a null shape sitting on top of the part, which
        # makes the real part no longer a tip of the tree - and then what
        # gets measured, exported and drawn is every intermediate cut and
        # every cutter, because nothing is left that looks like an answer.
        # One refused chamfer turned a 120 x 120 x 205 pedestal into eight
        # overlapping solids.
        try:
            doc.removeObject(feature.Name)
            doc.recompute()
        except Exception:
            pass
        raise RuntimeError(complaint)


def _upright_edges(feature, radius):
    # The corners of a padded outline are the edges running along the pad,
    # which are the only ones a corner radius means.
    shape = feature.Shape
    direction = None
    lengths = {}
    for n, edge in enumerate(shape.Edges, start=1):
        if not isinstance(edge.Curve, Part.Line):
            continue
        lengths.setdefault(round(edge.Length, 4), []).append(n)
    if not lengths:
        return []
    # The corners of a pad are the edges running along it, and they all
    # share one length: the pad depth. FreeCAD wants their names.
    for size in sorted(lengths, reverse=True):
        found = lengths[size]
        if len(found) >= 3:
            return ["Edge%d" % n for n in found]
    return []


def _axis(name):
    # Signed, because a hole is drilled INTO a face. "M6 from the top face
    # at Z=30, 14 deep" goes down; with +Z only, that cutter left the part
    # and the hole was never made - and the cut still succeeded, because
    # cutting nothing is a valid boolean.
    sign = -1.0 if str(name).startswith("-") else 1.0
    bare = str(name).lstrip("+-").upper()
    base = {"X": FreeCAD.Vector(1, 0, 0), "Y": FreeCAD.Vector(0, 1, 0),
            "Z": FreeCAD.Vector(0, 0, 1)}[bare]
    return base * sign


def _consume(doc, obj):
    # Remove an object AND whatever only existed to feed it.
    #
    # Deleting just the object leaves its operands behind, and what the app
    # calls the part is "every shape nothing else depends on" - so a fused
    # blade and boss, drilled, came back as THREE overlapping solids: the
    # drilled result and the two halves that had made it, suddenly tips of
    # the tree again. The gate caught it, the mass was 119 g instead of 72,
    # and nothing said why. A padded body leaves its sketch and pad the same
    # way, which is the other half of this: the pad kept its Length, so the
    # slider panel went on offering a dimension that no longer drove
    # anything, and dragging it moved a ghost.
    doomed, queue = [], [obj]
    while queue:
        node = queue.pop()
        if any(node is seen for seen in doomed):
            continue
        doomed.append(node)
        for child in (getattr(node, "OutList", None) or []):
            # Only if nothing outside this subtree still needs it.
            needed = [p for p in (getattr(child, "InList", None) or [])
                      if not any(p is seen for seen in doomed)
                      and p is not node]
            if not needed:
                queue.append(child)
    for node in doomed:
        try:
            doc.removeObject(node.Name)
        except Exception:
            pass


def _face_towards(shape, where):
    # The outermost flat face looking the way asked. "top" is +Z, and a
    # shell opens the face somebody would reach into.
    wanted = {"top": (0, 0, 1), "bottom": (0, 0, -1), "front": (0, -1, 0),
              "back": (0, 1, 0), "left": (-1, 0, 0), "right": (1, 0, 0)}
    direction = FreeCAD.Vector(*wanted.get(str(where).lower(), (0, 0, 1)))
    best, best_reach = None, None
    for face in shape.Faces:
        try:
            surface = face.Surface
            if not isinstance(surface, Part.Plane):
                continue
            normal = face.normalAt(0, 0)
        except Exception:
            continue
        if normal.dot(direction) < 0.99:
            continue
        reach = face.CenterOfMass.dot(direction)
        if best_reach is None or reach > best_reach:
            best, best_reach = face, reach
    return best
"""


class Session:
    """One document in FreeCAD, and the tools that work on it.

    Holds the document name so the model never has to carry it, which is one
    fewer argument to get wrong and one fewer way to edit the wrong part.
    """

    def __init__(self, bridge: freecad.Bridge, document: str = "") -> None:
        self.bridge = bridge
        self.document = document or bridge.new_document("CADSmith")
        #: Names FreeCAD actually assigned, in the order they were made, so
        #: a report can say what was built without asking FreeCAD again.
        self.built: list[str] = []
        #: The handful of numbers that become sliders. Declared while
        #: building rather than summarised afterwards: a model that has just
        #: made the base plate knows that its Length is the one a person
        #: would want to drag, and asking it again at the end invites a
        #: tidy-sounding answer that does not match what it built.
        self.declared: list[dict] = []
        #: What the part is made of, once something has said. Nothing by
        #: default: a part reported as aluminium because nobody said
        #: otherwise is a number presented as a fact.
        self.material: Optional[dict] = None
        #: Every hole as it was meant, not as it measures. A tapped M8 hole
        #: and a 6.8 clearance hole are the same cylinder afterwards and a
        #: different line on the drawing.
        self.holes: list[dict] = []

    # -- what every tool returns --------------------------------------------

    def _measured(self, **extra: Any) -> dict:
        """The state of the part after a change, as numbers.

        Returned by every tool that alters the document. A model that is
        told the box it just asked for is 60 x 40 x 12 can check that
        against what it meant; a model told "ok" cannot.
        """
        try:
            solids = self.bridge.measure(self.document).get("solids", [])
        except freecad.FreeCADError as error:
            return {**extra, "warning": f"could not measure: {error}"}
        finished = [
            {"name": s["name"], "label": s["label"],
             "size_mm": [round(v, 3) for v in s["bbox"]],
             "volume_mm3": round(s["volume"], 1),
             "faces": s["faces"],
             "watertight": s["valid"]}
            for s in solids]
        return {**extra, "part_now": finished}

    # -- the bottom layer: FreeCAD's own primitives -------------------------

    def add_shape(self, kind: str, name: str = "",
                  position: Optional[list] = None, **sizes: Any) -> dict:
        if kind not in PRIMITIVES:
            raise ToolError(
                f"{kind!r} is not one of the shapes offered here. There is: "
                + ", ".join(PRIMITIVES)
                + ". For anything else use run_python.")
        # FreeCAD spells these Length, Width, Height; a model writing from
        # memory spells them length, width, height, and a cube refused for
        # the case of its own letters is a round trip spent on nothing.
        wanted = {p.lower(): p for p in PRIMITIVES[kind]}
        sizes = {wanted.get(str(k).lower(), k): v for k, v in sizes.items()}
        needed = [p for p in PRIMITIVES[kind] if p not in sizes]
        if needed:
            raise ToolError(f"{kind} needs {', '.join(needed)}")

        made = self.bridge.add(self.document, kind, name or kind.split("::")[-1],
                               **sizes)
        self.built.append(made)
        if position:
            self.move(made, position)
        # FreeCAD may have renamed it; the model is told, because every
        # later call keys on the name that exists rather than the one asked
        # for.
        return self._measured(added=made,
                              renamed=(made != name if name else False))

    def move(self, name: str, position: list) -> dict:
        """Put an object somewhere. Placement is not a plain property, so it
        goes through the one door that takes arbitrary Python."""
        if len(position) != 3:
            raise ToolError("position is [x, y, z] in millimetres")
        x, y, z = (float(v) for v in position)
        self.bridge.run(f"""
import FreeCAD
doc = FreeCAD.getDocument({self.document!r})
obj = doc.getObject({name!r})
if obj is None:
    raise RuntimeError("no object called {name}")
obj.Placement = FreeCAD.Placement(
    FreeCAD.Vector({x}, {y}, {z}), obj.Placement.Rotation)
doc.recompute()
""")
        return self._measured(moved=name, to=[x, y, z])

    def rotate(self, name: str, axis: list, degrees: float) -> dict:
        if len(axis) != 3:
            raise ToolError("axis is [x, y, z]")
        ax, ay, az = (float(v) for v in axis)
        self.bridge.run(f"""
import FreeCAD
doc = FreeCAD.getDocument({self.document!r})
obj = doc.getObject({name!r})
if obj is None:
    raise RuntimeError("no object called {name}")
obj.Placement = FreeCAD.Placement(
    obj.Placement.Base,
    FreeCAD.Rotation(FreeCAD.Vector({ax}, {ay}, {az}), {float(degrees)}))
doc.recompute()
""")
        return self._measured(rotated=name, degrees=float(degrees))

    def set_size(self, name: str, **sizes: Any) -> dict:
        """Change a property and let the tree recompute.

        The reason for going through FreeCAD at all. One changed number
        re-runs everything built on it, which a STEP file can never do.

        Checked here before it reaches FreeCAD, because FreeCAD's own answer
        is not one a model can act on. Measured on an 8B asked to make a
        plate thicker, where the plate was a plain solid with no tree:
        nineteen calls, every one refused with "'Part.Feature' object has no
        attribute 'Height'", which says what went wrong and nothing about
        what to do instead. The run spent fifty-nine seconds on it.
        """
        if not sizes:
            raise ToolError("say which property to change, e.g. Length=75")
        found = self.bridge.object(self.document, name)
        if found is None:
            raise ToolError(f"there is no object called {name!r}. "
                            "Call list_objects to see what there is.")
        properties = found.get("Properties") or {}
        missing = [p for p in sizes if p not in properties]
        if missing:
            raise ToolError(self._cannot_resize(name, found, missing))
        self.bridge.edit(self.document, name, **sizes)
        return self._measured(edited=name, set=sizes)

    @staticmethod
    def _cannot_resize(name: str, found: dict, missing: list) -> str:
        """Why that property cannot be set, and what to do instead."""
        kind = found.get("TypeId") or found.get("Type") or "?"
        # The case worth naming. A solid handed to the document whole - by a
        # feature edit, an import, or a script that built it outside the
        # tree - is a Part::Feature, and it has no dimensions to set because
        # there is no tree behind it to recompute. Saying "no attribute
        # Height" leaves a model guessing at spellings; saying what the
        # object *is* sends it to the tools that work on geometry.
        if kind == "Part::Feature":
            return (f"{name} is a plain solid ({kind}) - it has no parametric "
                    f"dimensions to set, because nothing built it that could "
                    f"be re-run. Change it with the tools that work on "
                    f"geometry rather than on a tree: find_features, then "
                    f"resize_hole, remove_feature or add_fillet. To change an "
                    f"overall size you have to rebuild the shape.")
        sizeable = sorted(p for p in properties_of(found)
                          if p in {"Length", "Width", "Height", "Radius",
                                   "Radius1", "Radius2", "InnerRadius",
                                   "OuterRadius", "Angle"})
        return (f"{name} ({kind}) has no property called "
                f"{', '.join(repr(m) for m in missing)}. "
                + (f"It can be given: {', '.join(sizeable)}."
                   if sizeable else "It has no dimensions that can be set."))

    def combine(self, operation: str, base: str, tools: list) -> dict:
        """Cut, fuse or intersect. One call, because a boolean left half
        done is a document the next step cannot read."""
        kind = BOOLEANS.get(operation.lower())
        if kind is None:
            raise ToolError(f"operation is one of: {', '.join(BOOLEANS)}")
        if not tools:
            raise ToolError("name at least one object to combine with")

        names = json.dumps(list(tools))
        if operation.lower() == "cut":
            script = f"""
import FreeCAD
doc = FreeCAD.getDocument({self.document!r})
tools = [doc.getObject(n) for n in {names}]
missing = [n for n, o in zip({names}, tools) if o is None]
if missing:
    raise RuntimeError("no object called " + ", ".join(missing))
tool = tools[0]
if len(tools) > 1:
    tool = doc.addObject("Part::MultiFuse", "CutTools")
    tool.Shapes = tools
    doc.recompute()
result = doc.addObject("Part::Cut", "Result")
result.Base = doc.getObject({base!r})
result.Tool = tool
doc.recompute()
print(result.Name)
"""
        else:
            script = f"""
import FreeCAD
doc = FreeCAD.getDocument({self.document!r})
parts = [doc.getObject(n) for n in [{base!r}] + {names}]
missing = [n for n, o in zip([{base!r}] + {names}, parts) if o is None]
if missing:
    raise RuntimeError("no object called " + ", ".join(missing))
result = doc.addObject({kind!r}, "Result")
result.Shapes = parts
doc.recompute()
print(result.Name)
"""
        made = self.bridge.run(script).strip().splitlines()
        name = made[-1].strip() if made else "Result"
        self.built.append(name)
        return self._measured(combined=operation, result=name)

    def remove(self, name: str) -> dict:
        self.bridge.remove(self.document, name)
        return self._measured(deleted=name)

    def list_objects(self) -> dict:
        """What is in the document, with the names later calls must use."""
        return {"objects": [
            {"name": o.get("Name"), "type": o.get("TypeId") or o.get("Type"),
             "label": o.get("Label")}
            for o in self.bridge.objects(self.document)]}

    def declare_parameter(self, name: str, label: str, object_name: str,
                          property_name: str, scale: float = 1.0) -> dict:
        """Name a number a person should be able to drag.

        FreeCAD stores a cylinder's Radius; a person drags a diameter. The
        scale carries that, so the panel can say "Hole diameter 6" over a
        property holding 3 and the two never drift apart.
        """
        found = self.bridge.object(self.document, object_name)
        if found is None:
            raise ToolError(f"there is no object called {object_name!r}")
        if property_name not in (found.get("Properties") or found):
            # The stand-in and FreeCAD describe an object slightly
            # differently; either way a property that is not there is worth
            # catching now rather than when somebody drags it.
            properties = found.get("Properties") or {}
            if properties and property_name not in properties:
                raise ToolError(
                    f"{object_name} has no property called {property_name!r}. "
                    f"It has: {', '.join(sorted(properties)) or 'none'}")
        if scale == 0:
            raise ToolError("scale cannot be zero")

        self.declared = [d for d in self.declared if d["name"] != name]
        self.declared.append({"name": name, "label": label,
                              "object": object_name,
                              "property": property_name,
                              "scale": float(scale)})
        return {"declared": name, "reads": f"{object_name}.{property_name}",
                "parameters_so_far": [d["name"] for d in self.declared]}

    #: Which way a circular pattern turns, by the name a person uses.
    AXES = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}

    def pattern_circular(self, name: str, count: int,
                         centre: Optional[list] = None, axis: str = "Z",
                         angle: float = 360.0) -> dict:
        """Repeat an object evenly around a circle - a bolt circle.

        The one thing a part like a flange needs and no primitive provides.
        Without it a model computes six placements in a script, which is
        about 1,200 output tokens against the 40 a tool call costs, and the
        script is where the arithmetic goes wrong unseen.
        """
        if count < 2:
            raise ToolError("count is how many there are in all, so at least 2")
        if axis.upper() not in self.AXES:
            raise ToolError("axis is one of X, Y, Z")
        if self.bridge.object(self.document, name) is None:
            raise ToolError(f"there is no object called {name!r}")
        centre = [float(v) for v in (centre or [0, 0, 0])]
        if len(centre) != 3:
            raise ToolError("centre is [x, y, z] in millimetres")

        made = self._copies(f"""
import FreeCAD, json
doc = FreeCAD.getDocument({self.document!r})
src = doc.getObject({name!r})
centre = FreeCAD.Vector({centre[0]}, {centre[1]}, {centre[2]})
spindle = FreeCAD.Vector{self.AXES[axis.upper()]}
made = []
for i in range(1, {int(count)}):
    turn = FreeCAD.Rotation(spindle, {float(angle)} * i / {int(count)})
    copy = doc.copyObject(src, False)
    copy.Placement = FreeCAD.Placement(
        centre + turn.multVec(src.Placement.Base - centre),
        turn.multiply(src.Placement.Rotation))
    made.append(copy.Name)
doc.recompute()
{freecad.marked("json.dumps(made)")}
""")
        return self._measured(patterned=name, copies=made,
                              all_of_them=[name] + made)

    def pattern_linear(self, name: str, count: int, spacing: list) -> dict:
        """Repeat an object along a line - a row of holes."""
        if count < 2:
            raise ToolError("count is how many there are in all, so at least 2")
        if len(spacing) != 3:
            raise ToolError("spacing is [dx, dy, dz] in millimetres, "
                            "the step from one to the next")
        if self.bridge.object(self.document, name) is None:
            raise ToolError(f"there is no object called {name!r}")
        step = [float(v) for v in spacing]

        made = self._copies(f"""
import FreeCAD, json
doc = FreeCAD.getDocument({self.document!r})
src = doc.getObject({name!r})
step = FreeCAD.Vector({step[0]}, {step[1]}, {step[2]})
made = []
for i in range(1, {int(count)}):
    copy = doc.copyObject(src, False)
    copy.Placement = FreeCAD.Placement(
        src.Placement.Base + step * i, src.Placement.Rotation)
    made.append(copy.Name)
doc.recompute()
{freecad.marked("json.dumps(made)")}
""")
        return self._measured(patterned=name, copies=made,
                              all_of_them=[name] + made)

    def _copies(self, code: str) -> list:
        """Run a pattern script and return the names FreeCAD gave the copies."""
        made = json.loads(self.bridge.value(code))
        self.built.extend(made)
        return made

    def drill(self, target: str, at: list, diameter: float = 0.0,
              depth: float = 0.0, axis: str = "Z", thread: str = "",
              clearance_for: str = "", counterbore: Optional[list] = None,
              countersink: float = 0.0) -> dict:
        """Put a hole in a part, as a hole rather than as a subtracted cylinder.

        A hole carries more than its diameter, and none of the rest survives
        being cut with a cylinder. A tapped M8 hole is drilled 6.8 and called
        out M8; a clearance hole for the same screw is drilled 9 and called
        out Ø9. A counterbore is two diameters and a depth. Measured off the
        finished solid afterwards, all of them are just round holes, and the
        drawing has to guess.

        So the intent is recorded as the hole is made, and the drawing reads
        it. The geometry is still measured - the callout says what was meant,
        the measurement says what is there, and the two are checked against
        each other rather than one being trusted.
        """
        if self.bridge.object(self.document, target) is None:
            raise ToolError(f"there is no object called {target!r} to drill")
        if len(at) != 3:
            raise ToolError("at is [x, y, z] in millimetres, where the hole goes")
        if axis.upper().lstrip("+-") not in ("X", "Y", "Z"):
            raise ToolError(
                "axis is the way the drill points: X, Y or Z, or -X, -Y, -Z "
                "to go the other way. A hole in a top face is drilled -Z.")

        size, callout, kind = self._hole_size(diameter, thread, clearance_for)
        cb = self._counterbore(counterbore, size)
        if countersink and not 60 <= countersink <= 120:
            raise ToolError("countersink is the included angle in degrees, "
                            "usually 90 for a metric screw")

        made = self._build(f"""
import Part
target = doc.getObject({target!r})
box = target.Shape.BoundBox
reach = 2.0 * max(box.XLength, box.YLength, box.ZLength, 1.0)
at = FreeCAD.Vector({float(at[0])}, {float(at[1])}, {float(at[2])})
towards = _axis({axis.upper()!r})
deep = {float(depth)}
cutters = []
start = at if deep > 0 else at - towards * reach
length = deep if deep > 0 else 2.0 * reach
cutters.append(Part.makeCylinder({size / 2.0}, length, start, towards))
{self._counterbore_script(cb)}
{self._countersink_script(countersink, size)}
tool = cutters[0]
for extra in cutters[1:]:
    tool = tool.fuse(extra)
# A parametric cut, not a baked one. Replacing the solid with a plain
# feature and deleting what made it threw the tree away, and with it
# every slider: a padded plate whose thickness a person could drag
# stopped moving the moment it had a hole in it, while the panel went
# on showing the control. Base still points at what it cut, so the pad
# above still drives, and part.FCStd still opens with a tree an
# engineer can carry on from - which is the whole reason to build in
# FreeCAD rather than hand over a dead solid.
was = target.Shape.Volume
cutter = doc.addObject("Part::Feature", {self._clean(target) + "Cutter"!r})
cutter.Shape = tool
cutter.Visibility = False
out = doc.addObject("Part::Cut", {self._clean(target) + "Drilled"!r})
out.Base = target
out.Tool = cutter
doc.recompute()
_check(out, "that hole would remove the whole part")
# Cutting nothing is a perfectly valid boolean, so without this a cutter
# that missed the part - pointing the wrong way, or placed off it -
# reported a hole it had not made, and the drawing then called it out.
if was - out.Shape.Volume < 1e-6:
    doc.removeObject(out.Name)
    doc.removeObject(cutter.Name)
    doc.recompute()
    raise RuntimeError(
        "that hole removed no material: the cutter never met the part. "
        "Check the point it starts from and the way the axis points - a "
        "hole going into a top face is drilled -Z, not Z.")
made = [out.Name]
""")
        self.holes.append({
            "at": [float(v) for v in at], "axis": axis.upper(),
            "diameter": size, "depth": float(depth) or None,
            "through": not depth, "kind": kind, "thread": thread.upper(),
            "counterbore": cb, "countersink": float(countersink) or None,
            "label": callout + self._extra_callout(cb, countersink, depth),
        })
        self.built.append(made[0])
        return self._measured(drilled=self.holes[-1]["label"],
                              cut_at=size, in_part=made[0],
                              note=("drilled at the tapping size; the drawing "
                                    "calls it out as the thread"
                                    if kind == "tapped" else None))

    @staticmethod
    def _hole_size(diameter: float, thread: str, clearance_for: str):
        """What to drill, and what the drawing will call it."""
        if thread:
            spec = thread_drills(thread)
            if spec is None:
                raise ToolError(
                    f"{thread!r} is not a thread this knows. It has: "
                    + ", ".join(THREADS)
                    + ", with or without the pitch: 'M8' or 'M8x1.25'.")
            return spec["tap"], spec["name"], "tapped"
        if clearance_for:
            spec = thread_drills(clearance_for)
            if spec is None:
                raise ToolError(
                    f"{clearance_for!r} is not a thread this knows. It has: "
                    + ", ".join(THREADS)
                    + ", with or without the pitch: 'M8' or 'M8x1.25'.")
            return spec["clear"], f"Ø{spec['clear']:g}", "clearance"
        if diameter <= 0:
            raise ToolError(
                "say how big: diameter for a plain hole, thread='M8' for a "
                "tapped one, or clearance_for='M8' for a hole an M8 passes "
                "through")
        return float(diameter), f"Ø{float(diameter):g}", "plain"

    @staticmethod
    def _counterbore(spec: Optional[list], hole: float) -> Optional[dict]:
        if not spec:
            return None
        if len(spec) != 2:
            raise ToolError("counterbore is [diameter, depth] in millimetres")
        wide, deep = float(spec[0]), float(spec[1])
        if wide <= hole:
            raise ToolError(
                f"a counterbore has to be wider than the hole it sits over "
                f"- {wide:g} against {hole:g}")
        if deep <= 0:
            raise ToolError("a counterbore needs a depth")
        return {"diameter": wide, "depth": deep}

    @staticmethod
    def _counterbore_script(cb: Optional[dict]) -> str:
        if not cb:
            return ""
        return (f"cutters.append(Part.makeCylinder({cb['diameter'] / 2.0}, "
                f"{cb['depth']}, at - towards * {cb['depth']}, towards))")

    @staticmethod
    def _countersink_script(angle: float, hole: float) -> str:
        if not angle:
            return ""
        import math as _m
        # The cone a countersink leaves: wide at the face, down to the hole.
        wide = hole * 2.0
        deep = (wide - hole) / 2.0 / _m.tan(_m.radians(angle) / 2.0)
        return (f"cutters.append(Part.makeCone({wide / 2.0}, {hole / 2.0}, "
                f"{deep}, at - towards * {deep}, towards))")

    @staticmethod
    def _extra_callout(cb: Optional[dict], countersink: float,
                       depth: float) -> str:
        # ISO 129-1 has a glyph for depth, U+21A7, and the technical fonts a
        # drawing is lettered in do not carry it - it came out as "I8" on a
        # sheet, which is a dimension somebody could read and act on. The
        # counterbore and countersink symbols do render, so they stay; depth
        # is written in the word every drawing office also accepts.
        parts = []
        parts.append(f" {depth:g} DEEP" if depth else " THRU")
        if cb:
            parts.append(f", \u2334\u00d8{cb['diameter']:g} {cb['depth']:g} DEEP")
        if countersink:
            parts.append(f", \u2335{countersink:g}\u00b0")
        return "".join(parts)

    # -- the middle layer a real part is actually made of --------------------

    def extrude_profile(self, points: list, depth: float, name: str = "",
                        plane: str = "XY", offset: float = 0.0,
                        fillet: float = 0.0, midplane: bool = False) -> dict:
        """Draw a closed outline and pad it into a solid.

        The operation nearly every real part starts from, and the one this
        app could not do: a bracket is an L, a lever is a shape with two
        radiused ends, a gusset is a triangle. None of them is a box, and
        building them out of boxes and booleans is how a simple part becomes
        eleven tool calls and a wrong answer.

        What comes back is a parametric feature, not a lump: the pad's
        Length is a property, so set_size changes the thickness and the
        solid recomputes - and a slider can be declared on it.
        """
        profile = self._profile(points)
        if depth <= 0:
            raise ToolError("depth is how far to pad the outline, in "
                            "millimetres, and must be more than nothing")
        if plane.upper() not in PLANES:
            raise ToolError("plane is one of " + ", ".join(PLANES))
        made = self._build(f"""
body = doc.addObject("PartDesign::Body", {self._clean(name) + "Body"!r})
sketch = doc.addObject("Sketcher::SketchObject", {self._clean(name) + "Profile"!r})
body.addObject(sketch)
sketch.Placement = _placement({plane.upper()!r}, {float(offset)})
_outline(sketch, {profile!r})
doc.recompute()
pad = doc.addObject("PartDesign::Pad", {self._clean(name) + "Pad"!r})
body.addObject(pad)
pad.Profile = sketch
pad.Length = {float(depth)}
pad.Reversed = _reversed({plane.upper()!r})
pad.Midplane = {bool(midplane)}
doc.recompute()
_check(pad, "the outline would not pad - it may cross itself or not close")
made = [body.Name, sketch.Name, pad.Name]
{self._fillet_corners("pad", fillet)}
""")
        self.built.append(made[0])
        return self._measured(added=made[0], profile=made[1], pad=made[2],
                              adjustable=f"{made[2]}.Length is the depth")

    def revolve_profile(self, points: list, name: str = "", plane: str = "XZ",
                        angle: float = 360.0, axis: str = "Z") -> dict:
        """Draw a half-section and spin it about an axis.

        Every turned part: a boss, a hub, a spigot, a pulley, a shaft with
        steps in it. Built out of stacked cylinders instead, a stepped shaft
        is five primitives and five placements to get wrong; as a profile it
        is one outline.

        The outline is the half-section on one side of the axis, as a
        draughtsman draws it.
        """
        profile = self._profile(points)
        if not 0 < angle <= 360:
            raise ToolError("angle is how far round to spin it, 0 to 360 degrees")
        if plane.upper() not in PLANES:
            raise ToolError("plane is one of " + ", ".join(PLANES))
        if axis.upper() not in ("X", "Y", "Z"):
            raise ToolError("axis is X, Y or Z - the one the outline spins about")
        made = self._build(f"""
body = doc.addObject("PartDesign::Body", {self._clean(name) + "Body"!r})
sketch = doc.addObject("Sketcher::SketchObject", {self._clean(name) + "Profile"!r})
body.addObject(sketch)
sketch.Placement = _placement({plane.upper()!r}, 0.0)
_outline(sketch, {profile!r})
doc.recompute()
rev = doc.addObject("PartDesign::Revolution", {self._clean(name) + "Revolution"!r})
body.addObject(rev)
rev.Profile = sketch
rev.Angle = {float(angle)}
rev.ReferenceAxis = (doc.getObject({("Y_Axis" if axis.upper() == "Y" else
                                      "X_Axis" if axis.upper() == "X"
                                      else "Z_Axis")!r}), [""])
doc.recompute()
_check(rev, "the outline would not revolve - it may cross the axis or itself")
made = [body.Name, sketch.Name, rev.Name]
""")
        self.built.append(made[0])
        return self._measured(added=made[0], profile=made[1], revolution=made[2],
                              adjustable=f"{made[2]}.Angle is how far round")

    def loft(self, sections: list, name: str = "", solid: bool = True,
             ruled: bool = False) -> dict:
        """Blend one outline into another along the part.

        The operation a cable lug's barrel-to-palm transition is, and a
        turbine blade, and a venturi: two or more profiles at different
        stations, skinned. Built out of a pad it is not approximable - a
        round section becoming a rectangular one has no prismatic answer.

        Each section is {"points": [...], "plane": "XY", "offset": 0.0},
        drawn the way extrude_profile draws one, and they are skinned in
        the order given.
        """
        if not isinstance(sections, (list, tuple)) or len(sections) < 2:
            raise ToolError(
                "sections is at least two outlines to blend between, each "
                '{"points": [[x, y], ...], "plane": "XY", "offset": 0}')
        stem = self._clean(name or "Loft")
        drawn = []
        for index, section in enumerate(sections):
            if not isinstance(section, dict) or not section.get("points"):
                raise ToolError(f"section {index} has no points")
            plane = str(section.get("plane", "XY")).upper()
            if plane not in PLANES:
                raise ToolError("plane is one of " + ", ".join(PLANES))
            drawn.append((self._profile(section["points"]), plane,
                          float(section.get("offset", 0.0))))
        lines = []
        for index, (profile, plane, offset) in enumerate(drawn):
            lines.append(
                f"sk{index} = doc.addObject('Sketcher::SketchObject', "
                f"{stem + 'Sec' + str(index)!r})\n"
                f"sk{index}.Placement = _placement({plane!r}, {offset})\n"
                f"_outline(sk{index}, {profile!r})")
        made = self._build("\n".join(lines) + f"""
doc.recompute()
out = doc.addObject("Part::Loft", {stem + "Loft"!r})
out.Sections = [{", ".join("sk%d" % i for i in range(len(drawn)))}]
out.Solid = {bool(solid)}
out.Ruled = {bool(ruled)}
doc.recompute()
_check(out, "those outlines would not blend - they may cross, or be in "
            "the wrong order along the part")
made = [out.Name]
""")
        self.built.append(made[0])
        return self._measured(added=made[0], sections=len(drawn))

    def shell(self, name: str, thickness: float, open_face: str = "top") -> dict:
        """Hollow a solid out, leaving a wall and an opening.

        A housing, an enclosure, a cover, a tank. There is no way to make one
        by cutting a smaller box out of a bigger one that gets the corners
        right, and this is the operation every CAD has for it.
        """
        if thickness <= 0:
            raise ToolError("thickness is the wall left behind, in millimetres")
        if self.bridge.object(self.document, name) is None:
            raise ToolError(f"there is no object called {name!r}")
        made = self._build(f"""
import Part
target = doc.getObject({name!r})
shape = target.Shape
face = _face_towards(shape, {open_face!r})
if face is None:
    raise RuntimeError("no face on the {open_face} of that part to open")
try:
    hollow = shape.makeThickness([face], -abs({float(thickness)}), 1e-3)
except Exception as why:
    # OCCT throws here rather than returning nothing, and what came back
    # was "BRep_API: command not done", which names no part, no wall and
    # no way forward.
    raise RuntimeError(
        "a {float(thickness):g} mm wall will not stand in that part: the "
        "kernel could not build it. It is usually thicker than the part is "
        "somewhere - a rim as thin as the wall leaves nothing behind. "
        "(" + type(why).__name__ + ")")
if hollow is None or hollow.isNull() or hollow.Volume <= 0:
    raise RuntimeError(
        "a {float(thickness):g} mm wall would leave nothing of that part")
out = doc.addObject("Part::Feature", {self._clean(name) + "Shell"!r})
out.Shape = hollow
target.Visibility = False
_consume(doc, target)
doc.recompute()
made = [out.Name]
""")
        self.built.append(made[0])
        return self._measured(shelled=name, wall_mm=float(thickness),
                              opened=open_face, now=made[0])

    # -- building it, and the Python that does -------------------------------

    @staticmethod
    def _clean(name: str) -> str:
        """A FreeCAD-safe stem for the objects one operation creates."""
        kept = "".join(c for c in (name or "Part") if c.isalnum()) or "Part"
        return kept[:24]

    @staticmethod
    def _profile(points: Any) -> list:
        """A closed outline, checked before FreeCAD is asked to pad it."""
        if not isinstance(points, (list, tuple)) or len(points) < 3:
            raise ToolError(
                "points is the outline, at least three [x, y] pairs in the "
                "plane you are drawing on. It closes itself, so do not "
                "repeat the first point at the end.")
        out = []
        for point in points:
            tail = tuple(point[3:]) if isinstance(point, (list, tuple)) else ()
            if (not isinstance(point, (list, tuple))
                    or len(point) not in (2, 3, 4)
                    or not all(isinstance(v, (int, float)) for v in point[:3])
                    or (tail and str(tail[0]).lower() != "next")):
                raise ToolError(
                    f"{point!r} is not an [x, y] pair in millimetres, or an "
                    f"[x, y, radius] corner. A radius rounds that corner - "
                    f"it is how a plate gets R15 corners, and how a slot or "
                    f"a tab gets a full-round end (radius = half the width "
                    f"on the two corners at that end). "
                    f"[x, y, radius, 'next'] instead makes the SIDE from "
                    f"here to the next corner an arc of that radius, which "
                    f"is how a tangent transition or a U-turn is drawn; a "
                    f"negative radius bows it the other way.")
            if len(point) == 3 and float(point[2]) < 0:
                raise ToolError("a corner radius cannot be negative")
            out.append([float(v) for v in point[:3]] + list(tail))
        if out[0][:2] == out[-1][:2]:
            out.pop()
        if len(out) < 3:
            raise ToolError("an outline needs at least three distinct corners")
        crossing = _crosses_itself([p[:2] for p in out])
        if crossing:
            a, b = crossing
            raise ToolError(
                f"that outline crosses itself - the side from {out[a]} and "
                f"the side from {out[b]} intersect. FreeCAD will pad it into "
                f"something, and the something is not the part. List the "
                f"corners in order round the shape, clockwise or anti, "
                f"without jumping across.")
        return _rounded(out)

    @staticmethod
    def _fillet_corners(target: str, radius: float) -> str:
        """Round the corners of a pad, which is what a radiused outline is."""
        if not radius or radius <= 0:
            return ""
        return f"""
corners = _upright_edges({target}, {float(radius)})
if corners:
    rounded = doc.addObject("PartDesign::Fillet", "Corners")
    body.addObject(rounded)
    rounded.Base = ({target}, corners)
    rounded.Radius = {float(radius)}
    doc.recompute()
    _check(rounded, "the corner radius will not fit - it may be too big")
    made.append(rounded.Name)
"""

    def _build(self, body: str) -> list:
        """Run one modelling script in FreeCAD and report what it created."""
        names = json.loads(self.bridge.value(
            _PARTDESIGN
            + f"\ndoc = FreeCAD.getDocument({self.document!r})\n"
            + body
            + freecad.marked("json.dumps(made)")))
        if not names:
            raise ToolError("FreeCAD built nothing from that")
        return names

    def set_material(self, name: str) -> dict:
        """Say what the part is made of, and what that makes it weigh.

        Read out of FreeCAD's own material library - 145 cards with density,
        yield and tensile strength - rather than a table written here, which
        would be a guess at numbers somebody else maintains properly.
        """
        from app.server import materials

        card = materials.find(name, self.bridge)
        if card is None:
            known = ", ".join(c["name"] for c in
                              materials.library(self.bridge)[:8])
            raise ToolError(
                f"{name!r} is not a material this FreeCAD knows. It has "
                f"{len(materials.library(self.bridge))} of them, among them: "
                f"{known}. Name an alloy or a family - '6061', 'mild steel', "
                f"'ABS'.")
        self.material = card
        measured = self._measured(material=card["name"])
        for solid in measured.get("part_now") or []:
            weighed = materials.weigh(solid.get("volume_mm3"), card)
            if weighed:
                solid["mass_g"] = weighed["mass_g"]
        return measured

    def run_python(self, code: str) -> dict:
        """Anything FreeCAD can do that the tools above cannot.

        Offered on purpose: FreeCAD's API is far wider than a vocabulary
        worth writing out, and a sketch-driven pad or a loft has no
        primitive to call. The result is still measured, so code that runs
        and builds the wrong thing is caught the same way as everything else.
        """
        printed = self.bridge.run(code)
        return self._measured(printed=printed.strip()[:1000] or None)

    # -- the top layer: parts this app already knows are right ---------------

    def place_standard_part(self, description: str,
                            position: Optional[list] = None) -> dict:
        """Put a catalogue part into the document, exactly.

        The router that answers this is the same one that serves "a drag
        bar" with no model call at all. Reaching it from inside a build is
        the thing neither half does alone: a verified part becomes a
        component of a new design rather than the whole answer.

        The geometry is built here by this app's own kernel and handed to
        FreeCAD as a solid, because the catalogue speaks CadQuery and
        re-deriving every part in FreeCAD's vocabulary would be a second
        implementation to keep honest.
        """
        from app.catalog import router

        routed = router.select(description)
        if routed is None:
            offered = router.options(description)
            if offered:
                raise ToolError(
                    f"{description!r} names more than one standard part: "
                    + "; ".join(r.part.title for r in offered)
                    + ". Ask for one of them by name.")
            raise ToolError(
                f"{description!r} is not a standard part this app knows. "
                f"Build it from shapes instead.")

        import tempfile
        from pathlib import Path
        import cadquery as cq
        from app.catalog import verify

        solid, _ = verify.build(routed.part.code)
        step = Path(tempfile.mkdtemp(prefix="cadsmith_part_")) / "part.step"
        cq.exporters.export(cq.Workplane(obj=solid), str(step))

        # Imported through FreeCAD's own reader rather than rebuilt, so what
        # lands is the solid this app verified and not an approximation of
        # it.
        name = self.bridge.run(f"""
import FreeCAD, Part
doc = FreeCAD.getDocument({self.document!r})
shape = Part.Shape()
shape.read({str(step)!r})
obj = doc.addObject("Part::Feature", "StandardPart")
obj.Shape = shape
obj.Label = {routed.part.title[:60]!r}
doc.recompute()
print(obj.Name)
""").strip().splitlines()
        made = name[-1].strip() if name else "StandardPart"
        self.built.append(made)
        if position:
            self.move(made, position)
        return self._measured(placed=made, part=routed.part.title,
                              standard=routed.part.standard,
                              verified=routed.report.summary())

    # -- the middle layer: features, named the way a drawing names them ------

    def find_features(self) -> dict:
        """What the finished solid is made of, read off its own topology.

        Names things the way a drawing does - "4x Ø8.5 through hole,
        rectangular pattern 90 x 50" - so the next call can say "the
        mounting holes" without guessing a FreeCAD object name. Resolved
        afresh every time, so a selector cannot go stale after an edit.
        """
        from app.server import direct

        step = self._export_shape()
        found = direct.recognise(step)
        return {"features": [f.summary() for f in found],
                "how_to_use": "pass an id to resize_hole or remove_feature"}

    def resize_hole(self, feature_id: str, diameter: float) -> dict:
        return self._edit_feature({"op": "resize_hole", "select": feature_id,
                                   "diameter": float(diameter)})

    def remove_feature(self, feature_id: str) -> dict:
        return self._edit_feature({"op": "remove", "select": feature_id})

    def add_fillet(self, radius: float, where: str = "all") -> dict:
        if where == "all":
            return self._break_edges("Fillet", float(radius))
        return self._edit_feature({"op": "add_fillet", "radius": float(radius),
                                   "where": where})

    def add_chamfer(self, size: float, where: str = "all") -> dict:
        """Break the edges flat. The last line of almost every drawing."""
        if where == "all":
            return self._break_edges("Chamfer", float(size))
        return self._edit_feature({"op": "add_chamfer", "size": float(size),
                                   "where": where})

    def _break_edges(self, kind: str, size: float) -> dict:
        """Chamfer or fillet every edge, as a feature rather than a bake.

        Done in FreeCAD rather than in this app's own kernel because
        Part::Chamfer and Part::Fillet keep their Base, so the tree above
        them survives and so do the sliders. Breaking the edges is the last
        thing almost every prompt asks for, and doing it by exporting the
        solid, editing it here and importing a plain lump put the part back
        with no tree at all - which undid, on the very last call, the thing
        that makes building in FreeCAD worth doing.
        """
        if size <= 0:
            raise ToolError(f"a {kind.lower()} needs a positive size")
        if not self.built:
            raise ToolError("there is nothing built yet to break the edges of")
        target = self.built[-1]
        made = self._build(f"""
target = doc.getObject({target!r})
if target is None:
    raise RuntimeError("there is no object called {target} any more")
count = len(target.Shape.Edges)
if not count:
    raise RuntimeError("that solid has no edges to break")
out = doc.addObject("Part::{kind}", {self._clean(target) + kind!r})
out.Base = target
size = {float(size)}
every = [(i + 1, size, size) for i in range(count)]
out.Edges = every
target.Visibility = False
doc.recompute()


def _ok(feature):
    shape = getattr(feature, "Shape", None)
    return shape is not None and not shape.isNull() and shape.Volume > 1e-9


if not _ok(out):
    # Every edge at once is what a drawing asks for and not always what
    # the kernel can do: one pocket too narrow for the break refuses the
    # whole set, and the part comes back with no broken edges at all.
    # A person selects them all and deselects what will not take, so
    # that is what happens here - the edges are accumulated and any that
    # refuses is left sharp, which is the honest answer and is what the
    # part would be made as.
    kept = []
    for edge in every:
        out.Edges = kept + [edge]
        doc.recompute()
        if _ok(out):
            kept.append(edge)
    out.Edges = kept
    doc.recompute()
    if not kept or not _ok(out):
        raise RuntimeError(
            "a {kind.lower()} of %g will not fit on any edge of that part"
            % size)
    skipped = len(every) - len(kept)
else:
    skipped = 0
print("SKIPPED " + str(skipped) + " OF " + str(count))
made = [out.Name]
""")
        self.built.append(made[0])
        return self._measured(broke=kind.lower(), size=size,
                              edges=f"every edge of {target}",
                              in_part=made[0])

    def _export_shape(self):
        """The finished solid, here, as a file direct.py can read."""
        import tempfile
        from pathlib import Path
        step = Path(tempfile.mkdtemp(prefix="cadsmith_feat_")) / "part.step"
        step.write_bytes(self.bridge.fetch(self.document, "step"))
        return __import__("cadquery").importers.importStep(str(step)).val().wrapped

    def _edit_feature(self, recipe: dict) -> dict:
        """Edit a recognised feature, then put the result back in FreeCAD.

        The edit happens here, in this app's kernel, because that is where
        the feature recognition lives. What goes back is a plain solid: a
        direct edit has no tree to preserve, which is the same trade NX
        makes when synchronous technology touches an imported body.
        """
        from app.server import direct

        shape = self._export_shape()
        try:
            edited = direct.apply(shape, recipe)
        except KeyError as unknown:
            raise ToolError(str(unknown)) from None
        changed = direct.changed(shape, edited)

        import tempfile
        from pathlib import Path
        import cadquery as cq
        out = Path(tempfile.mkdtemp(prefix="cadsmith_edit_")) / "edited.step"
        cq.exporters.export(cq.Workplane(obj=cq.Shape.cast(edited)), str(out))

        self.bridge.run(f"""
import FreeCAD, Part
doc = FreeCAD.getDocument({self.document!r})
# Tips first. Removing a parent invalidates its children's handles, so
# walking doc.Objects in order and deleting as you go reaches an object
# that has already gone - "Cannot access attribute 'Name' of deleted
# object", which only showed up once there was a real tree to delete.
while doc.Objects:
    loose = [o for o in doc.Objects if not o.InList]
    if not loose:
        break
    for obj in loose:
        doc.removeObject(obj.Name)
shape = Part.Shape()
shape.read({str(out)!r})
obj = doc.addObject("Part::Feature", "Edited")
obj.Shape = shape
doc.recompute()
print(obj.Name)
""")
        self.built = ["Edited"]
        return self._measured(edit=recipe.get("op"),
                              volume_before=changed["volume"][0],
                              volume_after=changed["volume"][1],
                              features_now=changed["after"])


def toolbox_for(session: Session, allow_python: bool = True) -> Toolbox:
    """The tools, in the order a model should reach for them."""
    number = {"type": "number"}
    text = {"type": "string"}
    point = {"type": "array", "items": {"type": "number"},
             "description": "[x, y, z] in millimetres"}

    tools = [
        Tool(name="place_standard_part",
             description=(
                 "Put a part this app already knows is correct into the "
                 "document - a bearing, a washer, a spur gear, a named "
                 "handlebar bend. Try this before building a standard part "
                 "out of shapes. Give it the part in words, e.g. 'an M8x30 "
                 "socket head cap screw' or 'a drag bar'."),
             parameters={"type": "object", "properties": {
                 "description": text, "position": point},
                 "required": ["description"]},
             run=session.place_standard_part),
        Tool(name="extrude_profile",
             description=(
                 "Draw a closed outline and pad it into a solid. This is how "
                 "most real parts start - a bracket is an L, a lever has two "
                 "radiused ends, a gusset is a triangle - and it beats "
                 "building the same shape out of boxes and cuts. points are "
                 "[x, y] corners in the plane you draw on, in order, closing "
                 "themselves. A corner can be [x, y, radius] to round just "
                 "that one - that is how a plate gets R12 corners, and how a "
                 "slot or a tab gets a full-round end (put radius = half the "
                 "width on the two corners at that end). fillet rounds every "
                 "corner instead. The pad's Length stays adjustable "
                 "afterwards."),
             parameters={"type": "object", "properties": {
                 "points": {"type": "array",
                            "items": {"type": "array",
                                      "items": {"type": "number"}},
                            "description": "the outline, [[x, y], ...], or "
                                           "[x, y, radius] to round a corner"},
                 "depth": {**number, "description": "how far to pad it, mm"},
                 "name": text,
                 "plane": {**text, "enum": ["XY", "XZ", "YZ"]},
                 "offset": {**number,
                            "description": "move the drawing plane along its "
                                           "own normal, mm"},
                 "fillet": {**number, "description": "corner radius, mm"},
                 "midplane": {"type": "boolean",
                              "description": "pad both ways from the plane"}},
                 "required": ["points", "depth"]},
             run=session.extrude_profile),
        Tool(name="revolve_profile",
             description=(
                 "Draw a half-section and spin it about an axis: a boss, a "
                 "hub, a spigot, a pulley, a stepped shaft. The outline is "
                 "the half on one side of the axis, as a drawing shows it, "
                 "starting and ending on the axis. Far better than stacking "
                 "cylinders, which is five placements to get wrong."),
             parameters={"type": "object", "properties": {
                 "points": {"type": "array",
                            "items": {"type": "array",
                                      "items": {"type": "number"}},
                            "description": "the half-section, [[x, y], ...]"},
                 "name": text,
                 "plane": {**text, "enum": ["XY", "XZ", "YZ"]},
                 "angle": {**number, "description": "degrees, 360 for a full turn"},
                 "axis": {**text, "enum": ["X", "Y", "Z"]}},
                 "required": ["points"]},
             run=session.revolve_profile),
        Tool(name="loft",
             description=(
                 "Blend one outline into another along the part - a cable "
                 "lug's barrel becoming a flat palm, a venturi, a blade. "
                 "There is no prismatic answer to a round section becoming "
                 "a rectangular one, so this is the only tool that makes "
                 "one. sections are outlines at stations along the part, "
                 "in order."),
             parameters={"type": "object", "properties": {
                 "sections": {"type": "array", "items": {"type": "object"},
                              "description": 'outlines to blend, each '
                                             '{"points": [[x, y], ...], '
                                             '"plane": "XY", "offset": 0}'},
                 "name": text,
                 "ruled": {"type": "boolean",
                           "description": "straight between sections rather "
                                          "than a smooth skin"}},
                 "required": ["sections"]},
             run=session.loft),
        Tool(name="shell",
             description=(
                 "Hollow a solid out, leaving a wall of the thickness given "
                 "and an opening on one face: a housing, an enclosure, a "
                 "cover, a tank. There is no way to do this by cutting a "
                 "smaller box out of a bigger one that gets the corners "
                 "right."),
             parameters={"type": "object", "properties": {
                 "name": text,
                 "thickness": {**number, "description": "the wall left, mm"},
                 "open_face": {**text,
                               "enum": ["top", "bottom", "front", "back",
                                        "left", "right"]}},
                 "required": ["name", "thickness"]},
             run=session.shell),
        Tool(name="add_shape",
             description=(
                 "Add a primitive solid. kind is one of: "
                 + ", ".join(PRIMITIVES)
                 + ". Give its sizes as named arguments, e.g. kind='Part::Box' "
                   "with Length, Width and Height."),
             parameters={"type": "object", "properties": {
                 "kind": {**text, "enum": sorted(PRIMITIVES)},
                 "name": text, "position": point,
                 "Length": number, "Width": number, "Height": number,
                 "Radius": number, "Radius1": number, "Radius2": number,
                 "InnerRadius": number, "OuterRadius": number},
                 "required": ["kind"]},
             run=session.add_shape),
        Tool(name="set_size",
             description=("Change a property of an object already in the "
                          "document and let FreeCAD recompute everything "
                          "built on it."),
             parameters={"type": "object", "properties": {
                 "name": text,
                 "Length": number, "Width": number, "Height": number,
                 "Radius": number, "Radius1": number, "Radius2": number,
                 "InnerRadius": number, "OuterRadius": number},
                 "required": ["name"]},
             run=session.set_size),
        Tool(name="move",
             description="Place an object at [x, y, z] in millimetres.",
             parameters={"type": "object", "properties": {
                 "name": text, "position": point},
                 "required": ["name", "position"]},
             run=session.move),
        Tool(name="rotate",
             description="Turn an object about an axis, in degrees.",
             parameters={"type": "object", "properties": {
                 "name": text, "axis": point, "degrees": number},
                 "required": ["name", "axis", "degrees"]},
             run=session.rotate),
        Tool(name="drill",
             description=(
                 "Put a hole in a part, as a hole rather than as a cylinder "
                 "you cut. Give diameter for a plain hole, thread='M8' for a "
                 "tapped one (drilled at the tapping size and called out M8), "
                 "or clearance_for='M8' for a hole an M8 screw passes "
                 "through. depth 0 means through. counterbore is [diameter, "
                 "depth]. The drawing calls it out the way it was meant, "
                 "which a measured cylinder cannot say."),
             parameters={"type": "object", "properties": {
                 "target": text, "at": point,
                 "diameter": number, "depth": number,
                 "axis": {**text, "enum": ["X", "Y", "Z"]},
                 "thread": {**text, "description": "M3 to M24, tapped"},
                 "clearance_for": {**text,
                                   "description": "M3 to M24, a hole it passes through"},
                 "counterbore": {"type": "array", "items": {"type": "number"},
                                 "description": "[diameter, depth] in mm"},
                 "countersink": {**number, "description": "included angle, usually 90"}},
                 "required": ["target", "at"]},
             run=session.drill),
        Tool(name="combine",
             description=("Cut, union or intersect. Use 'cut' to make holes "
                          "and pockets: base is the part, tools are the "
                          "shapes to remove."),
             parameters={"type": "object", "properties": {
                 "operation": {**text, "enum": sorted(BOOLEANS)},
                 "base": text,
                 "tools": {"type": "array", "items": text}},
                 "required": ["operation", "base", "tools"]},
             run=session.combine),
        # Said on both patterns, because reaching for one to repeat a hole
        # is the obvious move and it silently makes N copies of the whole
        # part instead: a drilled hole is not an object, it is an absence.
        Tool(name="pattern_circular",
             description=(
                 "Repeat a shape evenly around a circle - a bolt circle, a "
                 "ring of holes, spokes. Place one where the first should "
                 "go, then pattern it. count is how many there are in all, "
                 "including the one you placed. Use this rather than working "
                 "out the positions yourself. This repeats an OBJECT. To repeat a hole, call drill once per hole - a hole is not an object to copy."),
             parameters={"type": "object", "properties": {
                 "name": text, "count": {"type": "integer"},
                 "centre": point,
                 "axis": {**text, "enum": ["X", "Y", "Z"]},
                 "angle": {**number,
                           "description": "degrees to spread over; 360 for "
                                          "a full circle"}},
                 "required": ["name", "count"]},
             run=session.pattern_circular),
        Tool(name="pattern_linear",
             description=(
                 "Repeat a shape along a line - a row of holes. count is "
                 "how many there are in all; spacing is the step from one "
                 "to the next. Pattern twice for a grid. This repeats an OBJECT. To repeat a hole, call drill once per hole - a hole is not an object to copy."),
             parameters={"type": "object", "properties": {
                 "name": text, "count": {"type": "integer"},
                 "spacing": point},
                 "required": ["name", "count", "spacing"]},
             run=session.pattern_linear),
        Tool(name="list_objects",
             description="What is in the document, with the names to use.",
             parameters={"type": "object", "properties": {}},
             run=session.list_objects),
        Tool(name="find_features",
             description=("Read the finished solid and report its holes, "
                          "bores and fillets the way a drawing names them. "
                          "Use before resize_hole or remove_feature."),
             parameters={"type": "object", "properties": {}},
             run=session.find_features),
        Tool(name="resize_hole",
             description=("Open a recognised hole pattern out or close it "
                          "down. feature_id comes from find_features."),
             parameters={"type": "object", "properties": {
                 "feature_id": text, "diameter": number},
                 "required": ["feature_id", "diameter"]},
             run=session.resize_hole),
        Tool(name="remove_feature",
             description=("Delete a recognised feature and heal the solid - "
                          "filling a hole, flattening a fillet."),
             parameters={"type": "object", "properties": {
                 "feature_id": text}, "required": ["feature_id"]},
             run=session.remove_feature),
        Tool(name="add_chamfer",
             description=("Break edges flat, at 45 degrees - what a drawing "
                          "means by '0.5 x 45 deg chamfer on all edges'. Use "
                          "this for a chamfer and add_fillet for a radius: "
                          "they are different features with different "
                          "callouts. where is 'all', 'top' or 'bottom'."),
             parameters={"type": "object", "properties": {
                 "size": number,
                 "where": {**text, "enum": ["all", "top", "bottom"]}},
                 "required": ["size"]},
             run=session.add_chamfer),
        Tool(name="add_fillet",
             description=("Break edges with a radius. where is 'all', 'top' "
                          "or 'bottom'."),
             parameters={"type": "object", "properties": {
                 "radius": number,
                 "where": {**text, "enum": ["all", "top", "bottom"]}},
                 "required": ["radius"]},
             run=session.add_fillet),
        Tool(name="set_material",
             description=(
                 "Say what the part is made of, when the request names a "
                 "material. Gives its weight, and the yield strength a "
                 "later check can hold it to. Takes an alloy or a family: "
                 "'6061', 'Aluminum-7075-T6', 'mild steel', 'titanium', "
                 "'ABS'."),
             parameters={"type": "object", "properties": {"name": text},
                         "required": ["name"]},
             run=session.set_material),
        Tool(name="declare_parameter",
             description=(
                 "Name a number a person should be able to adjust with a "
                 "slider afterwards, and say which object property it reads. "
                 "Declare the handful that matter - the overall sizes, a "
                 "hole diameter, a wall thickness - not every property. Use "
                 "scale=2 where you want a diameter over a Radius property."),
             parameters={"type": "object", "properties": {
                 "name": {**text, "description": "short, lower_case_with_underscores"},
                 "label": {**text, "description": "what a person reads"},
                 "object_name": text, "property_name": text, "scale": number},
                 "required": ["name", "label", "object_name", "property_name"]},
             run=session.declare_parameter),
        Tool(name="remove_object",
             description="Delete an object from the document by name.",
             parameters={"type": "object", "properties": {"name": text},
                         "required": ["name"]},
             run=session.remove),
    ]
    if allow_python:
        tools.append(Tool(
            name="run_python",
            description=(
                "Run Python inside FreeCAD. Use only when the tools above "
                "cannot do it - a sketch, a loft, a sweep, a helix. "
                "FreeCAD and the document are available; get the document "
                "with FreeCAD.getDocument(). Call doc.recompute() when done."),
            parameters={"type": "object", "properties": {"code": text},
                        "required": ["code"]},
            run=session.run_python))
    return Toolbox(tools)
