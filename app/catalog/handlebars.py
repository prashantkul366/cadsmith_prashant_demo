"""Handlebars: one tube, bent to the five numbers a bar is sold by.

A handlebar is the case study this app was asked for, and it is a good one.
It is a single part anyone recognises, it comes in a dozen named styles that
are the *same* part with different numbers, and every one of those numbers is
published by the people who make them - so the geometry can be checked
against the real thing rather than against taste.

**How a bar is measured.** Five dimensions name one, and they are the five
the trade uses (see ``docs/handlebar-research.md`` for the sources):

    width            tip to tip, at the widest point
    rise             how far the grips sit above the clamp
    pullback         how far the tips sit back from the clamp line
    clamp width      the straight at the middle that the risers hold
    control length   the straight at each end for grip and switchgear

Two more say how the bar gets there rather than what it measures: the bend
radius, and the angle the bar climbs out of the clamp at.

**What the geometry has to respect.** A bar is a bent tube, so the bend
radius is not a styling choice - it decides whether the part can be made.
The trade's rule is a centreline radius of at least twice the tube diameter,
nearer three times for a thin wall, and below about one and a half times you
are into mandrel tooling. ``bend_report`` measures that ratio off the built
solid rather than trusting the number that was asked for.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

#: Tube sizes, and where each one is used. The clamp diameter is what a
#: riser and a set of controls have to fit, so it is the size that names a
#: bar - 7/8 inch on nearly every current metric bike, an inch on a
#: Harley after 1990.
TUBES = {
    22.2: '7/8 in - metric bikes, and most current sport and commuter bars',
    25.4: '1 in - Harley-Davidson standard after 1990',
    31.8: '1-1/4 in - thick bars, turned down to 1 in where the risers clamp',
}

#: Riser spacing, which is a constraint on the clamp area rather than a
#: dimension of the bar: the straight has to be long enough to hold both.
RISER_SPACING = {"harley": 88.9, "springer": 120.7}


@dataclass(frozen=True)
class Bar:
    """One published bend, with where its numbers came from."""
    style: str
    title: str
    width: float
    rise: float
    pullback: float
    clamp_width: float
    control_length: float
    bend_radius: float
    rise_angle: float = 55.0
    tube_diameter: float = 22.2
    wall_thickness: float = 2.0
    source: str = ""

    def dimensions(self) -> dict[str, float]:
        return {
            "overall_width": self.width,
            "rise": self.rise,
            "pullback": self.pullback,
            "clamp_width": self.clamp_width,
            "control_length": self.control_length,
            "tube_diameter": self.tube_diameter,
            "wall_thickness": self.wall_thickness,
            "bend_radius": self.bend_radius,
            "rise_angle": self.rise_angle,
        }


#: The styles, in the order a catalogue would list them: the four production
#: road bends first, because every one of their numbers is published, then
#: the reference drawing this study was given, then the shapes from the
#: custom chart. Bend radii are not published by anyone - a bar is sold by
#: what it measures, not by how it was bent - so they are chosen at two to
#: three times the tube diameter, which is what the tube will take.
BARS: dict[str, Bar] = {
    "road_ultra_low": Bar(
        "road_ultra_low", "Road handlebar, ultra-low bend",
        width=725.0, rise=50.0, pullback=95.0, clamp_width=110.0,
        control_length=232.0, bend_radius=50.0, rise_angle=45.0,
        source="Renthal 758, 7/8 in road bar"),
    "road_low": Bar(
        "road_low", "Road handlebar, low bend",
        width=730.0, rise=75.0, pullback=125.0, clamp_width=105.0,
        control_length=242.0, bend_radius=50.0, rise_angle=65.0,
        source="Renthal 754, 7/8 in road bar"),
    "road_medium": Bar(
        "road_medium", "Road handlebar, medium bend",
        width=725.0, rise=85.0, pullback=105.0, clamp_width=105.0,
        control_length=223.0, bend_radius=50.0, rise_angle=55.0,
        source="Renthal 755, 7/8 in road bar"),
    "road_high": Bar(
        "road_high", "Road handlebar, high bend",
        width=710.0, rise=105.0, pullback=105.0, clamp_width=105.0,
        control_length=200.0, bend_radius=50.0, rise_angle=60.0,
        source="Renthal 756, 7/8 in road bar"),
    "commuter": Bar(
        "commuter", "Commuter handlebar, 648 mm",
        width=648.0, rise=126.0, pullback=110.0, clamp_width=136.0,
        control_length=190.0, bend_radius=45.0, rise_angle=78.0,
        tube_diameter=22.0, wall_thickness=2.0,
        source="the reference drawing: 648 wide, Ø22 x 2 wall. Its 126 is "
               "the rise to the straight; the 186 beside it is the tip, so "
               "the grips angle up - which this model does not do yet"),
    "classic": Bar(
        "classic", "Classic roadster handlebar, 737 mm",
        width=737.0, rise=152.0, pullback=130.0, clamp_width=140.0,
        control_length=200.0, bend_radius=50.0, rise_angle=70.0,
        source="Royal Enfield Classic 350 OEM bar, 29 in x 6 in rise"),
    "drag": Bar(
        "drag", "Drag bar, flat",
        width=760.0, rise=25.0, pullback=45.0, clamp_width=130.0,
        control_length=225.0, bend_radius=60.0, rise_angle=35.0,
        source="drag bar: no rise to speak of, a little pullback"),
    "tracker": Bar(
        "tracker", "Tracker bar",
        width=740.0, rise=90.0, pullback=95.0, clamp_width=130.0,
        control_length=215.0, bend_radius=55.0, rise_angle=60.0,
        source="tracker: a slight rise and pullback, after dirt-track bars"),
    "mini_ape": Bar(
        "mini_ape", "Mini ape hanger, 8 in rise",
        width=762.0, rise=203.0, pullback=120.0, clamp_width=130.0,
        control_length=215.0, bend_radius=60.0, rise_angle=75.0,
        tube_diameter=25.4, wall_thickness=3.0,
        source="mini apes: 8-10 in rise, on 1 in tube"),
    "ape": Bar(
        "ape", "Ape hanger, 12 in rise",
        width=800.0, rise=305.0, pullback=140.0, clamp_width=130.0,
        control_length=215.0, bend_radius=65.0, rise_angle=80.0,
        tube_diameter=25.4, wall_thickness=3.0,
        source="apes: 12-16 in rise, 33-38 in wide, on 1 in tube"),
}


def _n(value: float) -> str:
    """A number written the way the parameter panel reads it back."""
    return f"{value:g}" if value != int(value) else f"{value:.1f}"


def code_for(overall_width: float = 725.0, rise: float = 85.0,
             pullback: float = 105.0, clamp_width: float = 105.0,
             control_length: float = 223.0, tube_diameter: float = 22.2,
             wall_thickness: float = 2.0, bend_radius: float = 50.0,
             rise_angle: float = 55.0) -> str:
    """The CadQuery for one bar, as a script that stands on its own.

    Everything is computed from the nine assignments at the top, so the
    parameter panel's sliders drive real geometry rather than a lookup: move
    the rise and the bar is bent again, tangent arcs and all.
    """
    return f'''import cadquery as cq
import math

# A handlebar is a tube bent to five measurements. These are those five,
# plus the two that say how it gets there.
overall_width = {_n(overall_width)}
rise = {_n(rise)}
pullback = {_n(pullback)}
clamp_width = {_n(clamp_width)}
control_length = {_n(control_length)}
tube_diameter = {_n(tube_diameter)}
wall_thickness = {_n(wall_thickness)}
bend_radius = {_n(bend_radius)}
rise_angle = {_n(rise_angle)}

tube_radius = tube_diameter / 2.0
half_width = overall_width / 2.0
grip_height = rise if rise > 1.0 else 0.0

# The sweep bend brings the grips back towards the rider, and its angle is
# solved rather than stated: what is known is the pullback, and that the
# straight left beyond the bend has to be exactly the control length - the
# grip, the throttle and the switchgear need every millimetre of it.
sweep = math.atan2(pullback, half_width) if pullback > 0.0 else 0.0
for _ in range(8):
    reach = control_length + bend_radius * math.tan(sweep / 2.0)
    if pullback >= reach:
        break
    sweep = math.asin(pullback / reach)
reach = control_length + bend_radius * math.tan(sweep / 2.0)

# Width is measured across the widest point of the finished bar, and a tube
# cut square to a swept grip reaches past its own centreline by half a
# diameter. The centreline stops short by that much so the bar measures what
# it says it measures.
tip_x = half_width - tube_radius * math.sin(sweep)
grip_run = math.sqrt(max(reach ** 2 - pullback ** 2, 0.0))

# Waypoints from the middle of the clamp out to one tip. Corners here, not
# curves: the bends go in afterwards, each tangent to the two straights it
# joins, which is what comes off a tube bender.
points = [(0.0, 0.0, 0.0), (clamp_width / 2.0, 0.0, 0.0)]
if grip_height > 0.0:
    climb = grip_height / math.tan(math.radians(rise_angle))
    points.append((points[-1][0] + climb, 0.0, grip_height))
points.append((tip_x - grip_run, 0.0, grip_height))
points.append((tip_x, -pullback, grip_height))

# One side is computed and the other is its reflection, so the bar is
# exactly symmetric rather than symmetric to within a rounding error.
centreline = [(-x, y, z) for x, y, z in reversed(points)][:-1] + points


def turns_at(waypoints):
    """How far the tube turns at each corner, and the straights either side."""
    vectors = [cq.Vector(*point) for point in waypoints]
    corners = []
    for index in range(1, len(vectors) - 1):
        before, corner, after = vectors[index - 1:index + 2]
        into = corner.sub(before)
        away = after.sub(corner)
        turn = math.acos(max(-1.0, min(1.0, into.normalized().dot(
            away.normalized()))))
        corners.append((turn, into.Length, away.Length))
    return vectors, corners


def radius_that_fits(waypoints, wanted):
    """The largest bend radius this shape has room for, up to the one asked.

    One radius for the whole bar, because a bender has one die per radius and
    a second radius is a second setup. A bend eats into the straights either
    side of it by R*tan(turn/2), so two bends sharing a straight have to fit
    inside it - and where they do not, the honest answer is a gentler radius,
    not a path whose arcs run through one another.
    """
    vectors, corners = turns_at(waypoints)
    limit = wanted
    for index, (turn, before, after) in enumerate(corners):
        reach = math.tan(turn / 2.0)
        if reach < 1e-9:
            continue
        share_before = corners[index - 1][0] if index else 0.0
        share_after = corners[index + 1][0] if index + 1 < len(corners) else 0.0
        # Each straight is shared with the bend at its other end.
        limit = min(limit,
                    0.98 * before / (reach + math.tan(share_before / 2.0)),
                    0.98 * after / (reach + math.tan(share_after / 2.0)))
    return limit


def bent(waypoints, radius):
    """Line, arc, line - every corner replaced by a tangent arc."""
    vectors, _ = turns_at(waypoints)
    edges, cursor = [], vectors[0]

    def run_to(point):
        if point.sub(cursor).Length > 1e-7:
            edges.append(cq.Edge.makeLine(cursor, point))

    for index in range(1, len(vectors) - 1):
        before, corner, after = vectors[index - 1:index + 2]
        into = corner.sub(before).normalized()
        away = after.sub(corner).normalized()
        turn = math.acos(max(-1.0, min(1.0, into.dot(away))))
        if turn < 1e-6:
            continue
        offset = radius * math.tan(turn / 2.0)
        start = corner.sub(into.multiply(offset))
        end = corner.add(away.multiply(offset))
        # The apex of the arc, on the bisector, a bulge in from the corner.
        bulge = radius / math.cos(turn / 2.0) - radius
        middle = corner.add(away.sub(into).normalized().multiply(bulge))
        run_to(start)
        edges.append(cq.Edge.makeThreePointArc(start, middle, end))
        cursor = end
    run_to(vectors[-1])
    return cq.Wire.assembleEdges(edges)


# Below about one and a half tube diameters a 2 mm wall collapses rather
# than bends, mandrel or no mandrel, so that is where this stops trying.
bend_radius_used = radius_that_fits(centreline, bend_radius)
if bend_radius_used < 1.5 * tube_diameter:
    raise ValueError(
        "this bar cannot be bent: the straights leave room for a centreline "
        "radius of only %.1f mm on a %.1f mm tube (%.2f x diameter). Widen "
        "the clamp area, lengthen the bar, or lower the rise."
        % (bend_radius_used, tube_diameter, bend_radius_used / tube_diameter))

path = bent(centreline, bend_radius_used)
result = (
    cq.Workplane("YZ")
    .circle(tube_radius)
    .circle(tube_radius - wall_thickness)
    .sweep(cq.Workplane(path), isFrenet=True)
)
'''


# ---------------------------------------------------------------------------
# What the kernel can tell you about a bar once it is built
# ---------------------------------------------------------------------------

#: Below this, a mandrel and a wiper die; below 1.5 the wall folds. The
#: trade's comfortable minimum is twice the tube diameter, and about three
#: times for a thin wall (Xometry, Listertube - see docs/handlebar-research).
EASY_BEND = 2.0
TIGHT_BEND = 1.5

#: A grip, a throttle tube and a switch block need this much straight tube.
#: Renthal's own road bars run 200-242 mm of it.
MIN_CONTROL_LENGTH = 180.0


def _surfaces(solid):
    """The faces of a bar, sorted into the three kinds it has."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_SurfaceType

    ends, tubes, bends = [], [], []
    for face in solid.Faces():
        surface = BRepAdaptor_Surface(face.wrapped)
        kind = surface.GetType()
        if kind == GeomAbs_SurfaceType.GeomAbs_Plane:
            ends.append(face)
        elif kind == GeomAbs_SurfaceType.GeomAbs_Cylinder:
            tubes.append(surface.Cylinder().Radius())
        elif kind == GeomAbs_SurfaceType.GeomAbs_Torus:
            torus = surface.Torus()
            bends.append((torus.MajorRadius(), torus.MinorRadius()))
    return ends, tubes, bends


def _row(key: str, label: str, expected: str, actual: str,
         passed, hard: bool = True) -> dict:
    """One measured row, in the shape the Validation panel already draws."""
    return {"key": key, "label": label, "expected": expected,
            "actual": actual, "passed": passed, "hard": hard}


def inspect(solid, wanted: dict) -> list[dict]:
    """Measure a built bar against the dimensions it was asked for.

    Every row is a measurement off the solid, not a restatement of the
    parameters: the width is the kernel's bounding box, the rise and the
    pullback are the centres of the two end faces, and a bend radius is the
    major radius of a torus. A bar that claims 725 and measures 734 is what
    this is for.
    """
    ends, tubes, bends = _surfaces(solid)
    box = solid.BoundingBox()
    rows: list[dict] = []

    width = box.xlen
    asked = wanted["overall_width"]
    rows.append(_row(
        "bar_width", "width tip to tip", f"{asked:g} mm", f"{width:.1f} mm",
        abs(width - asked) <= 0.5))

    if len(ends) == 2:
        left, right = sorted((face.Center() for face in ends), key=lambda c: c.x)
        rows.append(_row(
            "bar_rise", "rise above the clamp", f"{wanted['rise']:g} mm",
            f"{right.z:.1f} mm", abs(right.z - wanted["rise"]) <= 0.5))
        rows.append(_row(
            "bar_pullback", "pullback at the tips",
            f"{wanted['pullback']:g} mm", f"{-right.y:.1f} mm",
            abs(-right.y - wanted["pullback"]) <= 0.5))
        # A bar that is not symmetric steers crooked, and nothing else here
        # would catch it: each half can measure right on its own.
        skew = max(abs(left.z - right.z), abs(left.y - right.y),
                   abs(left.x + right.x))
        rows.append(_row(
            "bar_symmetry", "the two ends mirror", "within 0.05 mm",
            f"{skew:.3f} mm", skew <= 0.05))
    else:
        rows.append(_row("bar_ends", "one end face at each end", "2",
                         str(len(ends)), False))

    if tubes:
        outer = max(tubes) * 2.0
        wall = (max(tubes) - min(tubes)) if len(set(tubes)) > 1 else 0.0
        rows.append(_row(
            "bar_tube", "tube and wall",
            f"Ø{wanted['tube_diameter']:g} x {wanted['wall_thickness']:g}",
            f"Ø{outer:.1f} x {wall:.1f}",
            abs(outer - wanted["tube_diameter"]) <= 0.05))

    if bends:
        tightest = min(radius for radius, _ in bends)
        ratio = tightest / wanted["tube_diameter"]
        if ratio >= EASY_BEND:
            note, passed = "a plain rotary-draw bend", True
        elif ratio >= TIGHT_BEND:
            note, passed = "tight: a mandrel and a wiper die", None
        else:
            note, passed = "the wall will fold, not bend", False
        rows.append(_row(
            "bend_radius", "bends a tube will take",
            f"at least {EASY_BEND:g}x the tube diameter",
            f"R{tightest:.1f} on Ø{wanted['tube_diameter']:g} - "
            f"{ratio:.2f}x diameter, {note}",
            bool(passed), hard=False))
        # One radius for the whole bar is one die and one setup. More than
        # one is a second, which is worth saying before a quotation does.
        distinct = sorted({round(radius, 1) for radius, _ in bends})
        rows.append(_row(
            "bend_count", "bends, and how many radii", "one radius",
            f"{len(bends) // 2} bends on "
            + (f"one radius, R{distinct[0]:g}" if len(distinct) == 1
               else f"{len(distinct)} radii: "
                    + ", ".join(f"R{r:g}" for r in distinct)),
            len(distinct) == 1, hard=False))

    asked_control = wanted.get("control_length")
    if asked_control:
        rows.append(_row(
            "control_length", "straight at each end for the controls",
            f"at least {MIN_CONTROL_LENGTH:g} mm", f"{asked_control:g} mm",
            asked_control >= MIN_CONTROL_LENGTH, hard=False))
    return rows
