"""An engineering drawing of the built part, projected from its STEP solid.

The views are real orthographic projections through OpenCASCADE's hidden-line
algorithm, so any part the pipeline can build gets a correct drawing rather
than a picture of one.  What makes it a *drawing* rather than four pictures
is the rest of this module: one stated scale, first angle arrangement, centre
lines, dimensions, and a title block.

Conventions, and where they come from:

* **First angle** (ISO 128-30:2001, A.2).  With reference to the front view,
  "the view from above is placed underneath" and "the view from the left is
  placed on the right".  The sheet carries the first angle symbol, which is
  the truncated cone drawn in that system: its side view (a trapezoid, narrow
  end away from the circles) on the left, its end view (two concentric
  circles) on the right.
* **Line types** (ISO 128-2).  Two widths in a 2:1 ratio - thick continuous
  for visible outlines, thin for everything else - with hidden detail dashed
  and centre lines long-dash-dotted.
* **Dimensions** (ISO 129-1).  Extension lines start clear of the feature and
  run 1.5 mm past the dimension line; values sit above the line and read from
  the bottom of the sheet.
* **Scale** (ISO 5455).  A preferred ratio, chosen as the largest that fits,
  and stated in the title block.  A drawing fitted to its frame cannot be
  measured; one drawn at 2:1 can.
* **Sheet** (ISO 5457 / ISO 216).  A3 landscape, 20 mm binding edge and 10 mm
  elsewhere.  One SVG user unit is one millimetre throughout, so every figure
  above is written here as itself.

The drawing describes the model as built.  It carries no tolerances and no
material, because nothing in the pipeline has specified either, and a general
tolerance note on a drawing nobody has toleranced would be a claim rather
than a fact.

Projection work happens in a subprocess, matching how ``autofab.executor``
isolates kernel work: an OCCT failure takes down the worker, not the server.
"""

from __future__ import annotations

import html
import json
import math
import os
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Sheet geometry, in millimetres (= SVG user units)
# ---------------------------------------------------------------------------

SHEET_W, SHEET_H = 420.0, 297.0        # ISO 216 A3, landscape
MARGIN_BIND, MARGIN = 20.0, 10.0       # ISO 5457 binding edge and trim margins
FRAME_L, FRAME_T = MARGIN_BIND, MARGIN
FRAME_R, FRAME_B = SHEET_W - MARGIN, SHEET_H - MARGIN

TITLE_W, TITLE_H = 180.0, 56.0
TITLE_L, TITLE_T = FRAME_R - TITLE_W, FRAME_B - TITLE_H

# The four view cells. First angle puts the view from above underneath the
# front view and the view from the left to its right; equal cells make the
# two pairs share a centreline without any further arithmetic.
CELLS_T, CELLS_B = FRAME_T, TITLE_T
CELL_W = (FRAME_R - FRAME_L) / 2.0
CELL_H = (CELLS_B - CELLS_T) / 2.0

VIEWS = {
    #                 line of sight      u axis on the sheet   cell (col, row)
    "FRONT":  {"dir": (0, -1, 0), "x": (1, 0, 0),  "cell": (0, 0),
               "label": "FRONT"},
    "LEFT":   {"dir": (-1, 0, 0), "x": (0, -1, 0), "cell": (1, 0),
               "label": "VIEW FROM LEFT"},
    "TOP":    {"dir": (0, 0, 1),  "x": (1, 0, 0),  "cell": (0, 1),
               "label": "VIEW FROM ABOVE"},
    "ISO":    {"dir": (1, 1, 1),  "x": (-1, 1, 0), "cell": (1, 1),
               "label": "ISOMETRIC"},
}

# Room a view may occupy inside its cell, leaving space for the dimensions
# that hang off two of its sides and for the view label.
VIEW_W, VIEW_H = CELL_W - 46.0, CELL_H - 30.0

# ISO 5455 preferred scales, as multipliers, largest first.
PREFERRED_SCALES = [50, 20, 10, 5, 2, 1,
                    0.5, 0.2, 0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001]

# ISO 128-2: two widths in a 2:1 ratio.
W_THICK, W_THIN = 0.5, 0.25
TEXT, TEXT_SMALL = 3.5, 2.5            # ISO 3098 heights for an A3 sheet
ARROW_L, ARROW_W = 3.2, 1.1            # filled arrowhead, roughly 3:1
EXT_GAP, EXT_PAST = 1.0, 1.5           # ISO 129-1: clear of the feature, 1.5 past
DIM_OFFSET = 10.0                      # first dimension line off the outline

#: ISO 3098 lettering is a technical sans. These are the faces that
#: actually match it where a machine has them, then progressively
#: plainer sans fallbacks - never a monospace, which reads as program
#: output rather than as a drawing.
FONT_STACK = ("ISOCPEUR,osifont,'Liberation Sans Narrow',"
              "'Arial Narrow','DejaVu Sans Condensed',Helvetica,"
              "Arial,sans-serif")
FONT = f'font-family="{FONT_STACK}"'


# ---------------------------------------------------------------------------
# Projection, in a subprocess
# ---------------------------------------------------------------------------

_WORKER = r'''
import json, sys
import cadquery as cq
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir, gp_Vec
from OCP.BRepLib import BRepLib
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_CurveType

step_path, spec_json = sys.argv[1], sys.argv[2]
spec = json.loads(spec_json)

shape = cq.importers.importStep(step_path)
if hasattr(shape, "val"):
    shape = shape.val()


def polylines(compounds):
    """Each projected edge as a polyline in the view plane, in millimetres."""
    out = []
    for compound in compounds:
        if compound is None or compound.IsNull():
            continue
        BRepLib.BuildCurves3d_s(compound, 1e-6)
        for edge in cq.Shape(compound).Edges():
            curve = edge._geomAdaptor()
            points = GCPnts_QuasiUniformDeflection(
                curve, 1e-3, curve.FirstParameter(), curve.LastParameter())
            if not points.IsDone():
                continue
            line = [(round(points.Value(i + 1).X(), 3),
                     round(points.Value(i + 1).Y(), 3))
                    for i in range(points.NbPoints())]
            if len(line) > 1:
                out.append(line)
    return out


def project(direction, x_direction):
    # The basis is stated rather than left to OCCT, which chooses its own and
    # would lay the model's Z axis across the page.
    axis = gp_Ax2(gp_Pnt(), gp_Dir(*direction), gp_Dir(*x_direction))
    hlr = HLRBRep_Algo()
    hlr.Add(shape.wrapped)
    hlr.Projector(HLRAlgo_Projector(axis))
    hlr.Update()
    hlr.Hide()
    shapes = HLRBRep_HLRToShape(hlr)

    visible = polylines([shapes.VCompound(), shapes.Rg1LineVCompound(),
                         shapes.OutLineVCompound()])
    hidden = polylines([shapes.HCompound(), shapes.OutLineHCompound()])

    xd, yd = axis.XDirection(), axis.YDirection()
    ex = (xd.X(), xd.Y(), xd.Z())
    ey = (yd.X(), yd.Y(), yd.Z())

    # A circular edge whose axis lies along the line of sight projects as a
    # circle - that is what earns a centre line and a diameter.
    look = gp_Vec(*direction).Normalized()
    circles = []
    for edge in shape.Edges():
        adaptor = BRepAdaptor_Curve(edge.wrapped)
        if adaptor.GetType() != GeomAbs_CurveType.GeomAbs_Circle:
            continue
        circle = adaptor.Circle()
        if abs(gp_Vec(circle.Axis().Direction()).Normalized().Dot(look)) < 0.999:
            continue
        centre = circle.Location()
        p = (centre.X(), centre.Y(), centre.Z())
        circles.append({
            "u": round(sum(p[i] * ex[i] for i in range(3)), 3),
            "v": round(sum(p[i] * ey[i] for i in range(3)), 3),
            "r": round(circle.Radius(), 3),
        })

    us = [p[0] for line in visible + hidden for p in line]
    vs = [p[1] for line in visible + hidden for p in line]
    return {
        "visible": visible, "hidden": hidden, "circles": circles,
        "basis": [list(ex), list(ey)],
        "bbox": ([min(us), min(vs), max(us), max(vs)] if us else [0, 0, 0, 0]),
    }


print("__DRAWING__")
print(json.dumps({name: project(v["dir"], v["x"]) for name, v in spec.items()}))
'''


def _project(step_path: Path, timeout: int = 180,
             cache: Optional[Path] = None) -> dict:
    """Project the solid into every view. Returns {view name: view data}.

    The hidden-line pass is the expensive half of a drawing - seconds, in a
    subprocess - and the SVG sheet and the DXF need exactly the same result.
    Caching it beside the version means the second of them is nearly free, and
    that a prebuilt sheet also pays for the DXF download.
    """
    if cache is not None and cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass  # rebuild rather than trust a half-written file

    work = Path(tempfile.mkdtemp(prefix="cadsmith_drawing_"))
    script = work / "project.py"
    script.write_text(_WORKER, encoding="utf-8")

    spec = {name: {"dir": list(v["dir"]), "x": list(v["x"])}
            for name, v in VIEWS.items()}
    result = subprocess.run(
        [sys.executable, str(script), str(step_path), json.dumps(spec)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    if "__DRAWING__" not in result.stdout:
        raise RuntimeError(
            (result.stderr or result.stdout or "projection produced no output")[-800:])

    body = result.stdout.split("__DRAWING__")[1].strip()
    if cache is not None:
        try:
            cache.write_text(body, encoding="utf-8")
        except OSError:
            pass  # a cache that cannot be written is not a failure
    return json.loads(body)


# ---------------------------------------------------------------------------
# Small drawing primitives
# ---------------------------------------------------------------------------


def _num(value: float) -> str:
    """A dimension value: no trailing zeros, and never '-0'."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text if text not in ("-0", "") else "0"


def _text(x: float, y: float, body: str, size: float = TEXT,
          anchor: str = "middle", fill: str = "#000",
          weight: str = "normal") -> str:
    return (f'<text x="{x:.2f}" y="{y:.2f}" {FONT} font-size="{size}" '
            f'fill="{fill}" text-anchor="{anchor}" font-weight="{weight}">'
            f'{html.escape(body)}</text>')


def _line(x1: float, y1: float, x2: float, y2: float, width: float = W_THIN,
          dash: str = "") -> str:
    stroke = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
            f'stroke="#000" stroke-width="{width}"{stroke}/>')


def _arrow(x: float, y: float, dx: float, dy: float) -> str:
    """A filled arrowhead at (x, y), pointing along the unit vector (dx, dy)."""
    bx, by = x - dx * ARROW_L, y - dy * ARROW_L
    px, py = -dy * ARROW_W / 2.0, dx * ARROW_W / 2.0
    return (f'<path d="M{x:.2f},{y:.2f} L{bx + px:.2f},{by + py:.2f} '
            f'L{bx - px:.2f},{by - py:.2f} Z" fill="#000"/>')


def _linear_dimension(x1: float, y1: float, x2: float, y2: float,
                      offset: float, label: str, vertical: bool) -> list[str]:
    """One dimension: extension lines, dimension line, arrows and the value.

    ``offset`` is signed, and says how far off the feature the dimension line
    sits - negative to put it above or to the left.
    """
    out: list[str] = []
    if vertical:
        dx = offset
        ax, ay = x1 + dx, y1
        bx, by = x2 + dx, y2
        step = math.copysign(1.0, dx)
        for (ex, ey) in ((x1, y1), (x2, y2)):
            out.append(_line(ex + step * EXT_GAP, ey,
                             ex + dx + step * EXT_PAST, ey))
    else:
        dy = offset
        ax, ay = x1, y1 + dy
        bx, by = x2, y2 + dy
        step = math.copysign(1.0, dy)
        for (ex, ey) in ((x1, y1), (x2, y2)):
            out.append(_line(ex, ey + step * EXT_GAP,
                             ex, ey + dy + step * EXT_PAST))

    out.append(_line(ax, ay, bx, by))
    length = math.hypot(bx - ax, by - ay)
    if length > 2 * ARROW_L:
        ux, uy = (bx - ax) / length, (by - ay) / length
        out.append(_arrow(ax, ay, -ux, -uy))
        out.append(_arrow(bx, by, ux, uy))

    mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
    if vertical:
        # Read from the right-hand side of the sheet, as ISO 129-1 has it for
        # a vertical dimension.
        out.append(f'<g transform="rotate(-90 {mx:.2f} {my:.2f})">'
                   + _text(mx, my - 2.0, label) + '</g>')
    else:
        out.append(_text(mx, my - 1.4, label))
    return out


# ---------------------------------------------------------------------------
# The sheet
# ---------------------------------------------------------------------------


def _choose_scale(views: dict) -> float:
    """The largest preferred scale at which every view still fits its cell."""
    fit = None
    for name, view in views.items():
        umin, vmin, umax, vmax = view["bbox"]
        width, height = max(umax - umin, 1e-6), max(vmax - vmin, 1e-6)
        limit = min(VIEW_W / width, VIEW_H / height)
        fit = limit if fit is None else min(fit, limit)
    if fit is None:
        return 1.0
    for scale in PREFERRED_SCALES:
        if scale <= fit:
            return float(scale)
    return PREFERRED_SCALES[-1]


def _scale_label(scale: float) -> str:
    if abs(scale - round(scale)) < 1e-9 and scale >= 1:
        return f"{round(scale)}:1"
    inverse = 1.0 / scale
    return f"1:{round(inverse)}"


def _cell_centre(cell: tuple[int, int]) -> tuple[float, float]:
    col, row = cell
    return (FRAME_L + (col + 0.5) * CELL_W, CELLS_T + (row + 0.5) * CELL_H)


def _escape(x: float, y: float, dx: float, dy: float,
            left: float, top: float, right: float, bottom: float) -> float:
    """How far from (x, y) along (dx, dy) before leaving the view's outline.

    A leader has to get clear of the drawing it points into before its text
    can sit anywhere legible.

    The *first* boundary the ray crosses, not the last. Taking the last was
    right only for a feature at the middle of the view, where every crossing
    is about as far off; from a hole near a corner it returns the distance to
    the opposite edge extended, and the leader shoots across the whole sheet
    to land in the margin. A plate's corner holes are exactly that case.
    """
    nearest = None
    for numerator, denominator in ((right - x, dx), (left - x, dx),
                                   (bottom - y, dy), (top - y, dy)):
        if abs(denominator) > 1e-9:
            distance = numerator / denominator
            if distance > 0:
                nearest = distance if nearest is None else min(nearest, distance)
    return min(nearest, 1e4) if nearest is not None else 0.0


def _distinct_circles(circles: list[dict]) -> list[dict]:
    """One entry per concentric-and-equal family, largest first.

    A through hole projects as two identical circles, and a counterbore as
    several; dimensioning each of them would say the same thing twice.
    """
    seen: dict[tuple, dict] = {}
    for circle in circles:
        key = (round(circle["u"], 2), round(circle["v"], 2),
               round(circle["r"], 3))
        seen.setdefault(key, circle)
    return sorted(seen.values(), key=lambda c: -c["r"])


#: How far a second row of dimensions sits beyond the first. ISO 129-1 wants
#: dimension lines spaced far enough apart that their values do not collide;
#: 8mm at sheet scale clears the 2.5mm text with room to read.
DIM_STEP = 8.0

#: Position dimensions are the point of a detail drawing, but a plate with
#: sixteen scattered holes dimensioned one by one is unreadable. Past this
#: many in one group, the drawing says how many there are and leaves the
#: positions to the model - which is honest, and better than a black sheet.
MAX_POSITIONED = 4

#: How close two lengths have to be before a pattern is called a pattern.
PATTERN_TOL = 0.05


def _hole_patterns(circles: list[dict]) -> list[dict]:
    """Same-size circles, grouped the way a drawing would call them out.

    A drawing does not dimension four identical holes four times.  It says
    "4 x M6" once and positions the pattern, and that is both the convention
    and the only way the sheet stays readable.  Three arrangements cover
    almost everything a part actually has:

    * a **bolt circle** - three or more equidistant from a common centre,
      called out with its pitch circle diameter;
    * a **rectangular pattern** - two or four on an axis-aligned grid,
      positioned by the two pitches;
    * anything else, positioned individually from the datum corner.

    Grouping is by diameter, because that is what makes holes interchangeable
    on a drawing. Concentric families are already collapsed upstream.
    """
    by_size: dict[float, list[dict]] = {}
    for circle in circles:
        by_size.setdefault(round(circle["r"], 3), []).append(circle)

    groups: list[dict] = []
    for radius, members in sorted(by_size.items(), key=lambda kv: -kv[0]):
        groups.append(_classify_holes(radius, members))
    return groups


def _classify_holes(radius: float, members: list[dict]) -> dict:
    group = {"radius": radius, "members": members, "count": len(members),
             "kind": "scatter"}
    if len(members) == 1:
        group["kind"] = "single"
        return group

    us = [c["u"] for c in members]
    vs = [c["v"] for c in members]
    cu, cv = sum(us) / len(us), sum(vs) / len(vs)

    distinct_u = sorted({round(u, 2) for u in us})
    distinct_v = sorted({round(v, 2) for v in vs})
    # A grid is tested before a bolt circle, because the four corners of a
    # rectangle are equidistant from its centre and would otherwise be called
    # out as a pitch circle - true, and not how anyone dimensions a plate.
    if (len(members) == 4 and len(distinct_u) == 2 and len(distinct_v) == 2) \
            or (len(members) == 2
                and (len(distinct_u) == 1 or len(distinct_v) == 1)):
        group.update(
            kind="rect",
            pitch_u=(distinct_u[-1] - distinct_u[0]) if len(distinct_u) > 1 else 0.0,
            pitch_v=(distinct_v[-1] - distinct_v[0]) if len(distinct_v) > 1 else 0.0,
            umin=min(us), umax=max(us), vmin=min(vs), vmax=max(vs))
        return group

    if len(members) >= 3:
        spans = [math.hypot(c["u"] - cu, c["v"] - cv) for c in members]
        mean = sum(spans) / len(spans)
        on_a_circle = mean > PATTERN_TOL and all(
            abs(span - mean) <= max(PATTERN_TOL, mean * 0.01) for span in spans)
        if on_a_circle:
            # Equidistant is not enough: so is every rectangle. A pitch
            # circle is equally *spaced* as well, which is what makes one
            # "6 holes on a 90 PCD" instead of six positions.
            angles = sorted(math.atan2(c["v"] - cv, c["u"] - cu)
                            for c in members)
            gaps = [(b - a) % (2 * math.pi)
                    for a, b in zip(angles, angles[1:] + [angles[0] + 2 * math.pi])]
            step = 2 * math.pi / len(members)
            if all(abs(gap - step) < math.radians(3.0) for gap in gaps):
                group.update(kind="bolt_circle", centre=(cu, cv), pcd=mean * 2.0)
                return group

    return group


def _hole_label(group: dict) -> str:
    """What the leader says: the count, the size, and the pattern if any."""
    diameter = _num(group["radius"] * 2.0)
    text = f"\u00d8{diameter}" if group["count"] == 1 \
        else f"{group['count']}\u00d7 \u00d8{diameter}"
    if group["kind"] == "bolt_circle":
        text += f" ON \u00d8{_num(group['pcd'])} PCD"
    return text


def plan_view(name: str, view: dict, scale: float, dimension: str) -> dict:
    """Where everything in one view goes, without drawing any of it.

    Separated from the drawing so that the SVG on screen and the DXF someone
    downloads are laid out by the same code. Two renderers of one plan can be
    checked against each other; two implementations of one drawing drift.

    ``dimension`` says which overall dimensions this view carries. Each length
    is dimensioned once across the whole sheet, which is what ISO 129-1 asks
    and what stops three views disagreeing about the same edge. All
    coordinates are in sheet millimetres, y downwards as SVG has it.
    """
    meta = VIEWS[name]
    cx, cy = _cell_centre(meta["cell"])
    umin, vmin, umax, vmax = view["bbox"]
    uc, vc = (umin + umax) / 2.0, (vmin + vmax) / 2.0

    def to_sheet(u: float, v: float) -> tuple[float, float]:
        return (cx + (u - uc) * scale, cy - (v - vc) * scale)

    def place(lines):
        return [[to_sheet(u, v) for u, v in line] for line in lines]

    left, top = to_sheet(umin, vmax)
    right, bottom = to_sheet(umax, vmin)

    # The pictorial view drops hidden detail: it is there to show the shape,
    # and dashed lines through a solid read as clutter rather than as
    # information.
    plan = {
        "name": name, "label": meta["label"], "centre": (cx, cy),
        "box": (left, top, right, bottom),
        "visible": place(view["visible"]),
        "hidden": [] if name == "ISO" else place(view["hidden"]),
        "centre_lines": [], "dimensions": [], "callouts": [],
    }

    # Centre lines through every circular feature (ISO 128-2 long-dash-dot).
    circles = _distinct_circles(view["circles"])
    seen: set[tuple[float, float]] = set()
    for circle in circles:
        key = (round(circle["u"], 2), round(circle["v"], 2))
        if key in seen:
            continue
        seen.add(key)
        biggest = max(c["r"] for c in circles
                      if (round(c["u"], 2), round(c["v"], 2)) == key)
        px, py = to_sheet(circle["u"], circle["v"])
        reach = biggest * scale + 3.0
        plan["centre_lines"].append((px - reach, py, px + reach, py))
        plan["centre_lines"].append((px, py - reach, px, py + reach))

    if "width" in dimension:
        plan["dimensions"].append({
            "p1": (left, bottom), "p2": (right, bottom),
            "offset": DIM_OFFSET, "vertical": False,
            "measure": umax - umin})
    if "height" in dimension:
        plan["dimensions"].append({
            "p1": (left, top), "p2": (left, bottom),
            "offset": -DIM_OFFSET, "vertical": True,
            "measure": vmax - vmin})

    # Where the features are, not just how big the part is. A plate whose
    # drawing says 100 x 60 x 8 with four 6mm holes and does not say where
    # the holes go cannot be made from that drawing - it is the single thing
    # that separated this sheet from a manufacturable one.
    groups = _hole_patterns(circles)
    level = 1 if "width" in dimension else 0
    positioned = 0

    def below_line(at_y: float) -> float:
        nonlocal level
        return (bottom + DIM_OFFSET + level * DIM_STEP) - at_y

    def left_line(at_x: float) -> float:
        return (left - DIM_OFFSET - level * DIM_STEP) - at_x

    for group in groups:
        if positioned >= 2:
            break
        members = group["members"]
        if group["kind"] == "bolt_circle":
            # The PCD is on the leader text; a pitch circle needs no further
            # dimensioning, which is exactly why drawings use one.
            continue
        if group["kind"] == "rect":
            (ax, ay) = to_sheet(group["umin"], group["vmin"])
            (bx, by) = to_sheet(group["umax"], group["vmax"])
            if group["pitch_u"] > PATTERN_TOL:
                plan["dimensions"].append({
                    "p1": (ax, ay), "p2": (bx, ay),
                    "offset": below_line(ay), "vertical": False,
                    "measure": group["pitch_u"]})
            if group["pitch_v"] > PATTERN_TOL:
                plan["dimensions"].append({
                    "p1": (ax, ay), "p2": (ax, by),
                    "offset": left_line(ax), "vertical": True,
                    "measure": group["pitch_v"]})
            level += 1
            positioned += 1
            continue

        # Single holes and small scatters: positioned from the datum corner,
        # which is the bottom-left of the view as drawn.
        if len(members) > MAX_POSITIONED:
            continue
        for circle in members:
            px, py = to_sheet(circle["u"], circle["v"])
            on_centre_u = abs(circle["u"] - uc) < PATTERN_TOL
            on_centre_v = abs(circle["v"] - vc) < PATTERN_TOL
            if on_centre_u and on_centre_v:
                # Dead centre, and the centre lines already say so.
                continue
            if not on_centre_u:
                plan["dimensions"].append({
                    "p1": (left, py), "p2": (px, py),
                    "offset": below_line(py), "vertical": False,
                    "measure": circle["u"] - umin})
            if not on_centre_v:
                plan["dimensions"].append({
                    "p1": (px, bottom), "p2": (px, py),
                    "offset": left_line(px), "vertical": True,
                    "measure": circle["v"] - vmin})
            level += 1
            positioned += 1
            if positioned >= 2:
                break

    # Leaders, largest first and capped: a drawing that calls out every
    # circle on a gear is unreadable, and the ones that matter are the big
    # ones. One leader per group, so four identical holes are named once.
    for index, group in enumerate(groups[:3]):
        # Leaders go right, because position dimensions go below and left.
        # Two things sharing the same margin is how a sheet ends up with a
        # hole size written across a pitch.
        angle = math.radians((45, -45, 135)[index])
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        # Start from the member furthest along the leader's own direction, so
        # it leaves from the outside of the group rather than crossing it.
        circle = max(group["members"],
                     key=lambda c: c["u"] * cos_a + c["v"] * sin_a)
        px, py = to_sheet(circle["u"], circle["v"])
        radius = circle["r"] * scale
        # A leader runs out from the feature and then levels off, and the
        # value sits above that shoulder. The run is long enough to clear the
        # whole view, not just its own circle: a gear's bore is small and
        # central, so a leader sized to the bore lands on the teeth.
        run = max(11.0, _escape(px, py, cos_a, -sin_a, left, top, right, bottom)
                  - radius + 4.0)
        plan["callouts"].append({
            "centre": (px, py), "radius": radius, "angle": angle,
            "start": (px + radius * cos_a, py - radius * sin_a),
            "elbow": (px + (radius + run) * cos_a,
                      py - (radius + run) * sin_a),
            "shoulder": 6.0 if cos_a > 0 else -6.0,
            "measure": circle["r"] * 2.0,
            "label": _hole_label(group)})

    below = bottom + (DIM_OFFSET + level * DIM_STEP + 10.0
                     if ("width" in dimension or level) else 5.0)
    floor = CELLS_T + (meta["cell"][1] + 1) * CELL_H - 3.0
    plan["label_at"] = (cx, min(below + 5.0, floor))
    return plan


def plan_sheet(views: dict) -> dict:
    """Everything the sheet says, before anything is drawn."""
    scale = _choose_scale(views)
    # Which view carries which overall dimension. Every length appears once:
    # the front view gives width and height, the view from above gives the
    # depth, and the remaining views repeat nothing.
    carries = {"FRONT": "width height", "TOP": "height", "LEFT": "", "ISO": ""}
    return {
        "scale": scale,
        "views": [plan_view(name, views[name], scale, carries[name])
                  for name in ("FRONT", "LEFT", "TOP", "ISO") if name in views],
    }


def _render_view(plan: dict) -> list[str]:
    """One planned view, as SVG."""
    out: list[str] = []

    def paths(lines, width, dash):
        for line in lines:
            points = " ".join(f"{x:.2f},{y:.2f}" for x, y in line)
            stroke = f' stroke-dasharray="{dash}"' if dash else ""
            out.append(f'<polyline points="{points}" fill="none" stroke="#000" '
                       f'stroke-width="{width}"{stroke} '
                       f'stroke-linecap="round" stroke-linejoin="round"/>')

    # Hidden first, so a visible edge over a hidden one wins.
    paths(plan["hidden"], W_THIN, "2.4,1.2")
    paths(plan["visible"], W_THICK, "")

    for x1, y1, x2, y2 in plan["centre_lines"]:
        out.append(_line(x1, y1, x2, y2, W_THIN, "6,1.2,1.2,1.2"))

    for dim in plan["dimensions"]:
        out += _linear_dimension(dim["p1"][0], dim["p1"][1],
                                 dim["p2"][0], dim["p2"][1],
                                 dim["offset"], _num(dim["measure"]),
                                 vertical=dim["vertical"])

    for call in plan["callouts"]:
        sx, sy = call["start"]
        ex, ey = call["elbow"]
        shoulder = call["shoulder"]
        out.append(_line(ex, ey, sx, sy))
        out.append(_line(ex, ey, ex + shoulder, ey))
        length = math.hypot(ex - sx, ey - sy) or 1.0
        out.append(_arrow(sx, sy, (sx - ex) / length, (sy - ey) / length))
        out.append(_text(ex + shoulder, ey - 1.6,
                         call.get("label") or f"Ø{_num(call['measure'])}",
                         anchor="start" if shoulder > 0 else "end"))

    out.append(_text(plan["label_at"][0], plan["label_at"][1], plan["label"],
                     TEXT_SMALL, fill="#000"))
    return out


def _projection_symbol(x: float, y: float) -> list[str]:
    """The first angle symbol: a truncated cone drawn in first angle.

    Its side view is a trapezoid and its end view two concentric circles. In
    first angle the view from the left is placed on the right, so the
    trapezoid sits on the left with its narrow end away from the circles
    (ISO 128-30 A.2; the symbol's proportions are ISO 5456-2).
    """
    h, r_big, r_small = 7.0, 3.5, 1.75
    out = [
        f'<path d="M{x:.2f},{y - r_small:.2f} L{x + h:.2f},{y - r_big:.2f} '
        f'L{x + h:.2f},{y + r_big:.2f} L{x:.2f},{y + r_small:.2f} Z" '
        f'fill="none" stroke="#000" stroke-width="{W_THIN}"/>',
        _line(x - 1.5, y, x + h + 1.5, y, W_THIN, "3,1,1,1"),
    ]
    ccx = x + h + 3.0 + r_big
    out += [
        f'<circle cx="{ccx:.2f}" cy="{y:.2f}" r="{r_big}" fill="none" '
        f'stroke="#000" stroke-width="{W_THIN}"/>',
        f'<circle cx="{ccx:.2f}" cy="{y:.2f}" r="{r_small}" fill="none" '
        f'stroke="#000" stroke-width="{W_THIN}"/>',
        _line(ccx - r_big - 1.5, y, ccx + r_big + 1.5, y, W_THIN, "3,1,1,1"),
        _line(ccx, y - r_big - 1.5, ccx, y + r_big + 1.5, W_THIN, "3,1,1,1"),
    ]
    return out


def _title_block(prompt: str, geometry: dict, job_id: str, version: int,
                 scale: float) -> list[str]:
    """An ISO 7200 title block: who, what, which sheet, and at what scale."""
    bbox = geometry.get("bounding_box", {})
    title = " ".join(prompt.split()).rstrip(".")
    if len(title) > 34:
        title = title[:34].rsplit(" ", 1)[0] + "…"

    out = [f'<rect x="{TITLE_L}" y="{TITLE_T}" width="{TITLE_W}" '
           f'height="{TITLE_H}" fill="none" stroke="#000" '
           f'stroke-width="{W_THICK}"/>']

    # Four rows; the top one is the title, which needs the width.
    rows = [14.0, 14.0, 14.0, 14.0]
    y = TITLE_T
    edges = []
    for height in rows[:-1]:
        y += height
        edges.append(y)
        out.append(_line(TITLE_L, y, TITLE_L + TITLE_W, y, W_THIN))

    def field(x: float, y_top: float, width: float, label: str, value: str,
              size: float = TEXT) -> None:
        out.append(_text(x + 2.0, y_top + 4.6, label, TEXT_SMALL,
                         anchor="start", fill="#555"))
        out.append(_text(x + 2.0, y_top + 11.4, value, size, anchor="start"))

    # Row 1 - who owns the drawing, and what it is
    field(TITLE_L, TITLE_T, TITLE_W, "LEGAL OWNER", "CADSmith")
    out.append(_line(TITLE_L + 60, TITLE_T, TITLE_L + 60, edges[0], W_THIN))
    field(TITLE_L + 60, TITLE_T, TITLE_W - 60, "TITLE", title)

    # Row 2 - the drawing's own identity
    field(TITLE_L, edges[0], 110, "DRAWING No.", f"{job_id}-{version:02d}")
    out.append(_line(TITLE_L + 110, edges[0], TITLE_L + 110, edges[1], W_THIN))
    field(TITLE_L + 110, edges[0], 70, "DATE OF ISSUE",
          time.strftime("%Y-%m-%d"))

    # Row 3 - how to read the views
    field(TITLE_L, edges[1], 40, "SCALE", _scale_label(scale))
    out.append(_line(TITLE_L + 40, edges[1], TITLE_L + 40, edges[2], W_THIN))
    field(TITLE_L + 40, edges[1], 40, "UNITS", "mm")
    out.append(_line(TITLE_L + 80, edges[1], TITLE_L + 80, edges[2], W_THIN))
    out.append(_text(TITLE_L + 82, edges[1] + 4.6, "PROJECTION", TEXT_SMALL,
                     anchor="start", fill="#555"))
    out += _projection_symbol(TITLE_L + 84, edges[1] + 9.6)
    out.append(_line(TITLE_L + 122, edges[1], TITLE_L + 122, edges[2], W_THIN))
    field(TITLE_L + 122, edges[1], 58, "SHEET", "1 / 1  A3")

    # Row 4 - what the kernel measured, which is the part of a title block
    # this app can fill in honestly
    volume = geometry.get("volume")
    field(TITLE_L, edges[2], 110, "OVERALL",
          "{:g} x {:g} x {:g}".format(
              round(bbox.get("xlen", 0), 2), round(bbox.get("ylen", 0), 2),
              round(bbox.get("zlen", 0), 2)))
    out.append(_line(TITLE_L + 110, edges[2], TITLE_L + 110,
                     TITLE_T + TITLE_H, W_THIN))
    field(TITLE_L + 110, edges[2], 70, "VOLUME mm³",
          f"{volume:.0f}" if volume else "—")
    return out


#: Said once, on the sheet, rather than repeated against every dimension.
_NOTES = [
    "ALL DIMENSIONS IN MILLIMETRES",
    "DIMENSIONS ARE AS MODELLED — NO TOLERANCES ARE SPECIFIED",
    "HIDDEN DETAIL SHOWN DASHED · ALL VIEWS TO THE STATED SCALE",
]


def _notes(geometry: dict) -> list[str]:
    """The notes as SVG."""
    lines = list(_NOTES)
    if geometry.get("is_valid"):
        lines.append("SOLID IS CLOSED AND WATERTIGHT AS PROJECTED")
    out = []
    for index, text in enumerate(lines):
        out.append(_text(FRAME_L + 2.0, TITLE_T + 8.0 + index * 5.0, text,
                         TEXT_SMALL, anchor="start", fill="#333"))
    out.append(_text(FRAME_L + 2.0, FRAME_B - 3.0,
                     "Projected from the exported STEP solid by CADSmith",
                     TEXT_SMALL, anchor="start", fill="#777"))
    return out


def build_sheet(step_path: Path, geometry: dict, prompt: str, job_id: str,
                version: int, projection: Optional[Path] = None) -> str:
    """Compose the drawing as a standalone SVG document."""
    sheet = plan_sheet(_project(step_path, cache=projection))
    scale = sheet["scale"]

    body: list[str] = []
    for view in sheet["views"]:
        body += _render_view(view)

    body += _title_block(prompt, geometry, job_id, version, scale)
    body += _notes(geometry)

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{SHEET_W}mm" '
        f'height="{SHEET_H}mm" viewBox="0 0 {SHEET_W} {SHEET_H}">'
        f'<rect width="{SHEET_W}" height="{SHEET_H}" fill="#fff"/>'
        f'<rect x="{FRAME_L}" y="{FRAME_T}" width="{FRAME_R - FRAME_L}" '
        f'height="{FRAME_B - FRAME_T}" fill="none" stroke="#000" '
        f'stroke-width="{W_THICK}"/>'
        + "\n".join(body)
        + "</svg>"
    )


def _version_inputs(version_dir: Path) -> tuple[Optional[Path], dict]:
    """The STEP this version built, and what the kernel measured of it."""
    step = version_dir / "model.step"
    if not step.exists():
        return None, {}

    geometry = {}
    geometry_file = version_dir / "geometry.json"
    if geometry_file.exists():
        try:
            geometry = json.loads(geometry_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return step, geometry


def ensure_sheet(version_dir: Path, prompt: str, job_id: str,
                 version: int) -> Optional[Path]:
    """Return the sheet for a version, building and caching it on first use."""
    target = version_dir / "drawing.svg"
    if target.exists() and target.stat().st_size > 0:
        return target

    step, geometry = _version_inputs(version_dir)
    if step is None:
        return None

    sheet = build_sheet(step, geometry, prompt, job_id, version,
                        projection=version_dir / "projection.json")
    target.write_text(sheet, encoding="utf-8")
    return target


# ---------------------------------------------------------------------------
# The same sheet as DXF, which is the format a drawing is exchanged in
# ---------------------------------------------------------------------------

#: ISO 128-24 line groups, as DXF line weights (hundredths of a millimetre).
_LW_THICK, _LW_THIN = 50, 25

#: Layers, named the way a drawing office names them, so the file opens in
#: someone else's CAD looking like a drawing rather than a pile of lines.
_LAYERS = [
    # name,        colour, weight,     linetype
    ("OUTLINE",         7, _LW_THICK, "Continuous"),
    ("HIDDEN",          8, _LW_THIN,  "DASHED2"),
    ("CENTRE",          4, _LW_THIN,  "CENTER2"),
    ("DIMENSIONS",      3, _LW_THIN,  "Continuous"),
    ("ANNOTATION",      7, _LW_THIN,  "Continuous"),
    ("FRAME",           7, _LW_THICK, "Continuous"),
]


def _dxf_y(y: float) -> float:
    """Sheet coordinates are planned y-down, as SVG has it; DXF is y-up."""
    return SHEET_H - y


def build_dxf(step_path: Path, geometry: dict, prompt: str, job_id: str,
              version: int, projection: Optional[Path] = None):
    """The same drawing as a DXF document, with real DIMENSION entities.

    The SVG on screen is a picture of the drawing; this is the drawing. Its
    dimensions are DIMENSION entities that carry the geometry they measure,
    so another CAD system re-measures them rather than trusting a string -
    which is also how the tests check that the number on the sheet is the
    number the kernel built.

    Laid out from the same plan as the SVG, so the two cannot disagree.
    """
    try:
        import ezdxf
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise RuntimeError(
            "The DXF drawing needs ezdxf: pip install -r "
            "app/requirements-app.txt. The sheet shown in the app is SVG and "
            "does not need it.") from exc

    sheet = plan_sheet(_project(step_path, cache=projection))
    scale = sheet["scale"]

    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4        # millimetres
    doc.header["$MEASUREMENT"] = 1     # metric
    for name, colour, weight, linetype in _LAYERS:
        doc.layers.add(name, color=colour, lineweight=weight,
                       linetype=linetype)

    # A dimension style to ISO 129-1 rather than ezdxf's own defaults, which
    # are sized for imperial architectural work.
    style = doc.dimstyles.duplicate_entry("EZDXF", "ISO-129")
    style.dxf.dimtxt = TEXT           # 3.5 mm text
    style.dxf.dimasz = ARROW_L        # arrowhead length
    style.dxf.dimexe = EXT_PAST       # extension past the dimension line
    style.dxf.dimexo = EXT_GAP        # gap from the feature
    style.dxf.dimgap = 0.8
    style.dxf.dimdec = 2
    style.dxf.dimtad = 1              # value above the dimension line
    style.dxf.dimtih = 0              # aligned with the line, not horizontal
    style.dxf.dimtoh = 0
    style.dxf.dimlwd = _LW_THIN
    style.dxf.dimlwe = _LW_THIN
    style.dxf.dimblk = ""  # closed filled, per ISO 129-1
    style.dxf.dimzin = 8              # no trailing zeros

    msp = doc.modelspace()

    def polyline(points, layer):
        msp.add_lwpolyline([(x, _dxf_y(y)) for x, y in points],
                           dxfattribs={"layer": layer})

    def line(x1, y1, x2, y2, layer):
        msp.add_line((x1, _dxf_y(y1)), (x2, _dxf_y(y2)),
                     dxfattribs={"layer": layer})

    def text(x, y, body, height=TEXT, align="MIDDLE_CENTER", layer="ANNOTATION"):
        entity = msp.add_text(body, height=height,
                              dxfattribs={"layer": layer,
                                          "style": "OpenSansCondensed-Light"})
        entity.set_placement((x, _dxf_y(y)), align=ezdxf.enums.TextEntityAlignment[align])
        return entity

    for view in sheet["views"]:
        for polygon in view["hidden"]:
            polyline(polygon, "HIDDEN")
        for polygon in view["visible"]:
            polyline(polygon, "OUTLINE")
        for x1, y1, x2, y2 in view["centre_lines"]:
            line(x1, y1, x2, y2, "CENTRE")

        for dim in view["dimensions"]:
            (x1, y1), (x2, y2) = dim["p1"], dim["p2"]
            offset = dim["offset"]
            base = ((x1 + offset, y1) if dim["vertical"]
                    else (x1, y1 + offset))
            # The dimension is given the points it measures, not a label, so
            # the value in the file is computed from the geometry - and
            # re-computed by whatever opens it.
            entity = msp.add_linear_dim(
                base=(base[0], _dxf_y(base[1])),
                p1=(x1, _dxf_y(y1)), p2=(x2, _dxf_y(y2)),
                angle=90.0 if dim["vertical"] else 0.0,
                dimstyle="ISO-129",
                dxfattribs={"layer": "DIMENSIONS"},
                # The views are drawn at the sheet's scale, so a dimension
                # measuring them has to divide it back out to report the part.
                override={"dimlfac": 1.0 / scale},
            )
            entity.render()

        for call in view["callouts"]:
            cx, cy = call["centre"]
            entity = msp.add_diameter_dim(
                center=(cx, _dxf_y(cy)),
                radius=call["radius"],
                angle=math.degrees(call["angle"]),
                dimstyle="ISO-129",
                dxfattribs={"layer": "DIMENSIONS"},
                override={"dimlfac": 1.0 / scale},
            )
            entity.render()

        text(view["label_at"][0], view["label_at"][1], view["label"],
             TEXT_SMALL)

    # Frame and title block. The fields are the same ones the SVG carries.
    frame = [(FRAME_L, FRAME_T), (FRAME_R, FRAME_T),
             (FRAME_R, FRAME_B), (FRAME_L, FRAME_B), (FRAME_L, FRAME_T)]
    polyline(frame, "FRAME")
    block = [(TITLE_L, TITLE_T), (FRAME_R, TITLE_T),
             (FRAME_R, FRAME_B), (TITLE_L, FRAME_B), (TITLE_L, TITLE_T)]
    polyline(block, "FRAME")

    bbox = geometry.get("bounding_box", {})
    rows = [
        ("LEGAL OWNER", "CADSmith"),
        ("TITLE", " ".join(prompt.split()).rstrip(".")),
        ("DRAWING No.", f"{job_id}-{version:02d}"),
        ("DATE OF ISSUE", time.strftime("%Y-%m-%d")),
        ("SCALE", _scale_label(scale)),
        ("UNITS", "mm"),
        ("PROJECTION", "FIRST ANGLE"),
        ("SHEET", "1 / 1  A3"),
        ("OVERALL", "{:g} x {:g} x {:g}".format(
            round(bbox.get("xlen", 0), 2), round(bbox.get("ylen", 0), 2),
            round(bbox.get("zlen", 0), 2))),
    ]
    row_h = TITLE_H / len(rows)
    for index, (label, value) in enumerate(rows):
        y = TITLE_T + (index + 0.5) * row_h
        if index:
            line(TITLE_L, TITLE_T + index * row_h,
                 FRAME_R, TITLE_T + index * row_h, "FRAME")
        text(TITLE_L + 2.0, y, label, TEXT_SMALL, "MIDDLE_LEFT")
        text(TITLE_L + 52.0, y, value, TEXT_SMALL, "MIDDLE_LEFT")

    for index, note in enumerate(_NOTES):
        text(FRAME_L + 2.0, TITLE_T + 6.0 + index * 5.0, note, TEXT_SMALL,
             "MIDDLE_LEFT")

    return doc


def ensure_dxf(version_dir: Path, prompt: str, job_id: str,
               version: int) -> Optional[Path]:
    """Return the DXF for a version, building and caching it on first use."""
    target = version_dir / "drawing.dxf"
    if target.exists() and target.stat().st_size > 0:
        return target

    step, geometry = _version_inputs(version_dir)
    if step is None:
        return None

    doc = build_dxf(step, geometry, prompt, job_id, version,
                    projection=version_dir / "projection.json")
    doc.saveas(target)
    return target


# ---------------------------------------------------------------------------
# Building it before anyone asks
# ---------------------------------------------------------------------------

#: One worker, so drawings queue behind each other rather than racing the
#: kernel for cores. They are built while the run is waiting on the model,
#: which is where the time actually goes, so the projection is usually done
#: long before anyone opens the Drawing panel.
_PREBUILD = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cadsmith-draw")

#: Versions already queued, so a re-published version is not projected twice.
_QUEUED: set[tuple[str, int]] = set()
_QUEUED_LOCK = threading.Lock()


def prebuild(version_dir: Path, prompt: str, job_id: str, version: int) -> None:
    """Start building this version's sheet now, in the background.

    Nothing waits on the result. ``ensure_sheet`` caches, so a click that
    arrives first simply builds it, and a click that arrives after this
    finishes finds the file already there - which is the point: the ten
    seconds of hidden-line projection are spent while the person is still
    looking at the part.

    Failures are swallowed deliberately. This is speculative work; if it does
    not succeed, the request path builds the sheet and reports any problem
    properly, in the caller's language.
    """
    key = (job_id, int(version))
    with _QUEUED_LOCK:
        if key in _QUEUED:
            return
        _QUEUED.add(key)

    def build() -> None:
        try:
            ensure_sheet(version_dir, prompt, job_id, version)
        except Exception:
            pass
        finally:
            with _QUEUED_LOCK:
                _QUEUED.discard(key)

    try:
        _PREBUILD.submit(build)
    except RuntimeError:
        # Interpreter shutting down: nothing to prebuild for.
        with _QUEUED_LOCK:
            _QUEUED.discard(key)
