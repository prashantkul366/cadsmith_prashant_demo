"""Holes read off the solid, with the depths a flat projection cannot show.

A projection shows a hole as a circle, and a circle has no depth. So the
sheet could say Ø8.5 and never whether that is through twenty millimetres
or six, and it could not tell a counterbore from two holes that happen to
share a centre - which is why `counterbore_diameter`, `counterbore_depth`
and every `*_depth` in the library were among the numbers that never
reached a page.

The solid knows. Every hole is a cylindrical face, and a cylindrical face
carries its radius, its axis, and how far it runs along that axis. Two
coaxial cylinders of different radii are a counterbore; a cylinder that
spans the part is through; one that stops is blind and the stopping point
is the depth a machinist sets.

So this reads the kernel rather than the picture, and the picture is then
annotated with what the kernel said. The callouts it produces are the ones
a drawing uses - `4x Ø8.5 THRU ⌴Ø14 ▼6` - rather than three separate
diameters at one place, which is what the sheet printed before.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

#: Two axes are the same line within this, in millimetres and in the
#: cosine of the angle between them.
SAME_AXIS_MM = 0.02
SAME_AXIS_DOT = 0.999

#: Two radii are the same within this, in millimetres.
SAME_R = 0.005

#: A bore within this of spanning the part is through rather than deep.
#: Nothing is exactly flush: a chamfered mouth takes a few hundredths off
#: the cylinder, and calling that a blind hole 19.96 deep would be worse
#: than saying THRU.
THROUGH_SLACK = 0.5


@dataclass
class Bore:
    """One cylindrical face: a hole, or one step of a counterbored one."""
    radius: float
    depth: float
    #: A point on the axis, and the unit direction material is removed in.
    at: tuple
    axis: tuple
    #: Where the cylinder starts and ends along its own axis, as a signed
    #: distance from `at`. Kept so steps can be stacked in order.
    span: tuple
    inside: bool = True

    @property
    def diameter(self) -> float:
        return self.radius * 2.0


@dataclass
class Hole:
    """A hole as a drawing calls it out: its steps, in order, with depths."""
    steps: list = field(default_factory=list)
    through: bool = False
    thread: str = ""

    @property
    def radius(self) -> float:
        """The smallest step, which is the one a drill makes."""
        return min(step.radius for step in self.steps) if self.steps else 0.0

    @property
    def at(self) -> tuple:
        return self.steps[0].at if self.steps else (0.0, 0.0, 0.0)

    @property
    def axis(self) -> tuple:
        return self.steps[0].axis if self.steps else (0.0, 0.0, 1.0)


def _unit(vector) -> tuple:
    length = math.sqrt(sum(c * c for c in vector)) or 1.0
    return tuple(c / length for c in vector)


def _dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


def _coaxial(a: Bore, b: Bore) -> bool:
    """Whether these two cylinders are bored down the same line."""
    if abs(_dot(a.axis, b.axis)) < SAME_AXIS_DOT:
        return False
    # The distance from b's axis point to a's axis, which is the component
    # of the offset perpendicular to the shared direction.
    offset = tuple(x - y for x, y in zip(b.at, a.at))
    along = _dot(offset, a.axis)
    perpendicular = tuple(o - along * d for o, d in zip(offset, a.axis))
    return math.sqrt(sum(c * c for c in perpendicular)) <= SAME_AXIS_MM


def bores(shape: Any) -> list[Bore]:
    """Every cylindrical face of this solid, as a bore.

    Never raises: a kernel that will not describe a face costs the depth
    on that one hole, not the drawing.
    """
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepClass3d import BRepClass3d_SolidClassifier
        from OCP.BRepTools import BRepTools
        from OCP.GeomAbs import GeomAbs_SurfaceType
        from OCP.gp import gp_Pnt
        from OCP.TopAbs import TopAbs_OUT
    except Exception:
        return []

    found: list[Bore] = []
    for face in shape.Faces():
        try:
            surface = BRepAdaptor_Surface(face.wrapped)
            if surface.GetType() != GeomAbs_SurfaceType.GeomAbs_Cylinder:
                continue
            cylinder = surface.Cylinder()
            axis = cylinder.Axis()
            location, direction = axis.Location(), axis.Direction()
            _, _, vmin, vmax = BRepTools.UVBounds_s(face.wrapped)
            depth = abs(vmax - vmin)
            if depth <= 0:
                continue
            # Hole or boss, asked of the solid rather than inferred from
            # the face's orientation, which a CadQuery `extrude` leaves
            # REVERSED on an outside wall. The axis of a hole runs through
            # void; the axis of a boss runs through metal.
            middle = gp_Pnt(
                location.X() + direction.X() * (vmin + vmax) / 2.0,
                location.Y() + direction.Y() * (vmin + vmax) / 2.0,
                location.Z() + direction.Z() * (vmin + vmax) / 2.0)
            judge = BRepClass3d_SolidClassifier(shape.wrapped, middle, 1e-6)
            found.append(Bore(
                radius=round(cylinder.Radius(), 4),
                depth=round(depth, 4),
                at=(location.X(), location.Y(), location.Z()),
                axis=_unit((direction.X(), direction.Y(), direction.Z())),
                span=(round(min(vmin, vmax), 4), round(max(vmin, vmax), 4)),
                inside=judge.State() == TopAbs_OUT))
        except Exception:
            continue
    return found


def through_depth(axis, extents) -> float:
    """How much material a hole along this axis has to get through.

    The part's extent resolved onto the hole's own direction. A hole down
    Z through a 120 x 80 x 12 plate has 12 mm to clear, and reading the
    plan view's bounding box instead gives 80 - which is why a hole that
    went through was called out 5.5 deep.
    """
    return sum(abs(a) * e for a, e in zip(axis, extents))


def from_cylinders(records: Iterable[dict],
                   extent: Optional[Any] = None) -> list[Hole]:
    """The same as `holes`, from what the projection worker read.

    The worker has the solid open already and reads the cylindrical faces
    in the same pass, so the answer caches beside the projection and no
    second STEP import is paid for. The stacking is done here because it
    is reasoning rather than reading.
    """
    found = [Bore(radius=float(r["r"]), depth=float(r["depth"]),
                  at=tuple(r["at"]), axis=_unit(tuple(r["axis"])),
                  span=tuple(r["span"]), inside=bool(r.get("inside", True)))
             for r in records or []]
    return _stack(found, extent)


def holes(shape: Any, extent: Optional[float] = None) -> list[Hole]:
    """The bores of this solid, stacked into holes.

    Coaxial bores of different radii are one hole with steps - a
    counterbore, a spotface, a drilled-and-tapped hole - which is one
    callout on a drawing rather than one per step. `extent` is how thick
    the part is along the hole axis, used only to tell through from deep;
    without it, every hole reads as deep, which understates nothing.
    """
    return _stack(bores(shape), extent)


def _stack(found: list, extent: Optional[Any] = None) -> list[Hole]:
    """Coaxial bores collected into holes, widest step first.

    `extent` is either one thickness or the part's three extents, in which
    case each hole is measured against its own axis - which is the only
    way to get it right for a part with holes down more than one axis.
    """
    inside = [bore for bore in found if bore.inside]
    inside.sort(key=lambda b: -b.radius)

    stacks: list[list[Bore]] = []
    for bore in inside:
        for stack in stacks:
            if _coaxial(stack[0], bore):
                stack.append(bore)
                break
        else:
            stacks.append([bore])

    out: list[Hole] = []
    for stack in stacks:
        # Widest first is how a counterbore is written: the mouth, then
        # what is under it.
        stack.sort(key=lambda b: -b.radius)
        # How far the whole stack reaches, measured rather than added up:
        # a counterbore 6 deep over a pilot 14 deep goes through a 20 mm
        # plate, and summing the steps only gets that right when they do
        # not overlap. Each step's ends are projected onto the shared axis
        # and the outermost two are the reach.
        line = stack[0].axis
        origin = stack[0].at
        ends = []
        for step in stack:
            base = _dot(tuple(x - y for x, y in zip(step.at, origin)), line)
            flip = 1.0 if _dot(step.axis, line) > 0 else -1.0
            ends.append(base + flip * step.span[0])
            ends.append(base + flip * step.span[1])
        reach = max(ends) - min(ends)
        if extent is None:
            clear = 0.0
        elif isinstance(extent, (list, tuple)):
            clear = through_depth(line, extent)
        else:
            clear = float(extent)
        through = clear > 0 and reach >= clear - THROUGH_SLACK
        out.append(Hole(steps=stack, through=through))
    return out


def callout(hole: Hole, count: int = 1, thread: str = "") -> str:
    """What the leader says, in the order a drawing says it.

    `4x Ø8.5 THRU ⌴Ø14 ▼6`: how many, what the drill makes, how far it
    goes, then each step over it with its own depth. A tapped hole is
    named by its thread rather than by the drill, because M8x1.25 is what
    is being asked for and 6.8 is only how it is made.
    """
    if not hole.steps:
        return ""
    drill = hole.steps[-1]
    head = f"{count}× " if count > 1 else ""
    size = thread or f"Ø{_num(drill.diameter)}"
    text = f"{head}{size}"
    text += " THRU" if hole.through else f" ▼{_num(drill.depth)}"
    for step in hole.steps[:-1]:
        text += (f" ⌴Ø{_num(step.diameter)}"
                 f" ▼{_num(step.depth)}")
    return text


def _num(value: float) -> str:
    return f"{value:g}"


def grouped(found: Iterable[Hole], threads: Optional[dict] = None) -> list[dict]:
    """Holes that would be called out identically, counted once.

    A drawing does not dimension four identical counterbores four times,
    and the reason is the same as for four plain holes: the callout is
    what makes them interchangeable, so one callout and a count says
    everything four would.

    `threads` maps a drilled diameter to the thread it is drilled for -
    6.8 to M8x1.25 - because that is what the hole is for. A sheet saying
    Ø6.8 where the request said M8x1.25 is asking for a hole nobody wants:
    6.8 is how the thread is made, not what it is.
    """
    out: list[dict] = []
    for hole in found:
        named = ""
        if threads:
            for drilled, thread in threads.items():
                if abs(float(drilled) - hole.steps[-1].diameter) <= 0.06:
                    named = str(thread)
                    break
        hole.thread = named
        shape = (named, hole.through,
                 tuple((round(s.radius, 3), round(s.depth, 3))
                       for s in hole.steps))
        for group in out:
            if group["shape"] == shape:
                group["members"].append(hole)
                break
        else:
            out.append({"shape": shape, "members": [hole], "hole": hole,
                        "thread": named})
    for group in out:
        group["count"] = len(group["members"])
        group["label"] = callout(group["hole"], group["count"],
                                 group["thread"])
        group["radius"] = group["hole"].radius
    # Biggest first, as the leaders are drawn.
    out.sort(key=lambda g: -g["radius"])
    return out
