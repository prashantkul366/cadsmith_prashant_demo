"""The handlebar case study, checked against bars that exist.

The claim being made here is not "this builds a shape". It is that a bar
asked for by the five dimensions the trade sells one by comes back measuring
those five dimensions, that a bend it could not make is refused rather than
built, and that the drawing dimensions the bend a tube bender would be set
to rather than whichever arc the projection happened to emit.

Runs the real kernel: it bends ten bars and projects one.

Run:  .venv/bin/python -m app.tests.test_handlebars
"""

from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cadquery as cq  # noqa: E402

from app.catalog import handlebars, parts, router, verify  # noqa: E402
from app.server import drawing, spec  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def measured(solid) -> dict:
    """Width, rise, pullback and the bends, off the built solid."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_SurfaceType

    ends, bends = [], set()
    for face in solid.Faces():
        surface = BRepAdaptor_Surface(face.wrapped)
        kind = surface.GetType()
        if kind == GeomAbs_SurfaceType.GeomAbs_Plane:
            ends.append(face.Center())
        elif kind == GeomAbs_SurfaceType.GeomAbs_Torus:
            bends.add(round(surface.Torus().MajorRadius(), 3))
    box = solid.BoundingBox()
    right = max(ends, key=lambda c: c.x)
    return {"width": box.xlen, "rise": right.z, "pullback": -right.y,
            "bends": sorted(bends), "ends": ends}


def main() -> int:
    print("\nEvery published bend builds, and measures what it claims")
    for name, bar in handlebars.BARS.items():
        try:
            solid, _ = verify.build(handlebars.code_for(**bar.dimensions()))
        except Exception as error:  # noqa: BLE001 - the report is the point
            check(f"{name} builds", False, f"{type(error).__name__}: {error}")
            continue
        got = measured(solid)
        check(f"{name}: {bar.width:g} x {bar.rise:g} rise x {bar.pullback:g} back",
              abs(got["width"] - bar.width) <= 0.5
              and abs(got["rise"] - bar.rise) <= 0.5
              and abs(got["pullback"] - bar.pullback) <= 0.5
              and solid.isValid(),
              f"{got['width']:.1f} x {got['rise']:.1f} x {got['pullback']:.1f}")

    print("\nA bar is the same on both sides")
    solid, _ = verify.build(handlebars.code_for(
        **handlebars.BARS["road_medium"].dimensions()))
    got = measured(solid)
    left, right = sorted(got["ends"], key=lambda c: c.x)
    check("the two ends mirror each other",
          abs(left.x + right.x) < 1e-6 and abs(left.y - right.y) < 1e-6
          and abs(left.z - right.z) < 1e-6,
          f"{left.x:.4f} vs {right.x:.4f}")

    print("\nA bend that cannot be made is refused, not built")
    # Room for R14 on a 22mm tube is 0.64 x diameter: the wall folds.
    cramped = handlebars.code_for(
        overall_width=600.0, rise=200.0, pullback=120.0, clamp_width=90.0,
        control_length=230.0, tube_diameter=22.0, wall_thickness=2.0,
        bend_radius=60.0, rise_angle=40.0)
    try:
        verify.build(cramped)
        check("a bar with no room for its bends is refused", False,
              "it built anyway")
    except ValueError as error:
        check("a bar with no room for its bends is refused",
              "cannot be bent" in str(error) and "x diameter" in str(error),
              str(error)[:96])
    except Exception as error:  # noqa: BLE001
        check("the refusal is a clear one, not a kernel error", False,
              f"{type(error).__name__}: {error}")

    print("\nThe radius is reduced to what fits, rather than overrunning")
    tight = handlebars.BARS["road_medium"]
    solid, _ = verify.build(handlebars.code_for(**tight.dimensions()))
    fitted = measured(solid)["bends"]
    check("one radius for the whole bar", len(fitted) == 1, str(fitted))
    check("and no larger than the one asked for",
          fitted[0] <= tight.bend_radius + 1e-6,
          f"R{fitted[0]:g} for a requested R{tight.bend_radius:g}")
    check("but still a radius the tube will take",
          fitted[0] / tight.tube_diameter >= handlebars.TIGHT_BEND,
          f"{fitted[0] / tight.tube_diameter:.2f} x diameter")

    print("\nThe catalogue serves a named bend, and declines the rest")
    routed = router.select("a 760mm drag bar")
    check("a named bend routes", routed is not None
          and routed.part.id.startswith("handlebar_drag"),
          routed.part.id if routed else "nothing")
    check("a bare handlebar does not: it is five dimensions, not a size",
          router.select("a handlebar") is None)
    for ask in ("a handlebar riser", "a handlebar clamp", "a bar end weight"):
        check(f"'{ask}' is not a handlebar", router.select(ask) is None)
    routed = router.select("ape hangers with 14 inch rise")
    check("an inch rise is read as one",
          routed is not None
          and abs(routed.part.parameters["rise"] - 355.6) < 0.1,
          str(routed.part.parameters["rise"]) if routed else "nothing")
    check("and a Japanese request reaches the same bend",
          (router.select("ドラッグバー") or None) is not None
          and router.select("ドラッグバー").part.id.startswith("handlebar_drag"))

    print("\nThe part reports what was measured, not what was asked")
    part = parts.select("a commuter handlebar")
    report = verify.check(part)
    rows = {row["key"]: row for row in report.measured}
    check("the bar passes its own checks", report.ok, "; ".join(report.problems))
    for key in ("bar_width", "bar_rise", "bar_pullback", "bar_symmetry",
                "bar_tube", "bend_radius"):
        check(f"{key} is measured", key in rows,
              rows.get(key, {}).get("actual", "missing"))
    check("the bend radius is reported against the tube diameter",
          "x diameter" in rows.get("bend_radius", {}).get("actual", ""),
          rows.get("bend_radius", {}).get("actual", ""))
    check("the rows carry what was asked beside what was measured",
          all({"key", "label", "expected", "actual", "passed", "hard"}
              <= set(row) for row in report.measured))
    check("and the bend ratio is advisory, not a refusal",
          rows["bend_radius"]["hard"] is False)

    work = Path(tempfile.mkdtemp(prefix="cadsmith_handlebar_test_"))
    solid, _ = verify.build(part.code)
    step = work / "bar.step"
    cq.exporters.export(cq.Workplane(obj=solid), str(step))

    print("\nA bend too tight to make is flagged wherever it is built")
    # Built the way a model would write it, not through the family: R25 on a
    # 22mm tube, which is 1.14 x diameter.
    corner = [cq.Vector(0, 0, 0), cq.Vector(150, 0, 0), cq.Vector(150, 0, 150)]
    radius = 25.0
    into = (corner[1] - corner[0]).normalized()
    away = (corner[2] - corner[1]).normalized()
    turn = math.acos(max(-1.0, min(1.0, into.dot(away))))
    offset = radius * math.tan(turn / 2.0)
    start, end = corner[1] - into.multiply(offset), corner[1] + away.multiply(offset)
    middle = corner[1] + away.sub(into).normalized().multiply(
        radius / math.cos(turn / 2.0) - radius)
    path = cq.Wire.assembleEdges([
        cq.Edge.makeLine(corner[0], start),
        cq.Edge.makeThreePointArc(start, middle, end),
        cq.Edge.makeLine(end, corner[2])])
    bent = (cq.Workplane("YZ").circle(11.0).circle(9.0)
            .sweep(cq.Workplane(path), isFrenet=True))
    tight_step = work / "tight.step"
    cq.exporters.export(bent, str(tight_step))
    tight = spec.measure_step(tight_step)
    bend_check = next((c for c in spec.manufacturability(tight)
                       if c.key == "bend_radius"), None)
    check("the advisory catches it", bend_check is not None
          and bend_check.passed is False,
          bend_check.actual if bend_check else "no bend check")
    check("and it is advisory, because a mandrel bend is a thing to buy",
          bend_check is not None and not bend_check.hard)
    check("a tube's own bore is not counted as a drilled hole",
          not spec.measure_step(step)["holes"],
          str(spec.measure_step(step)["holes"]))

    print("\nThe drawing dimensions the bend, not its silhouette")
    views = drawing._project(step)  # noqa: SLF001
    plan = drawing.plan_sheet(views)
    wanted = part.parameters["bend_radius"]
    for view in plan["views"]:
        radii = [call for call in view["callouts"]
                 if call.get("kind") == "radius"]
        if not radii:
            continue
        check(f"{view['name']} calls out the centreline radius",
              all(abs(call["measure"] - wanted) < 0.6 for call in radii),
              ", ".join(call["label"] for call in radii))
    labels = [call.get("label", "") for view in plan["views"]
              for call in view["callouts"]]
    check("the tube is called out by diameter",
          any("Ø22" in label for label in labels), str(labels))
    check("and the bends by radius",
          any(label.endswith(f"R{wanted:g}") for label in labels), str(labels))

    print("\nAnd it dimensions the path, the way the reference sheet does")
    front = next(v for v in plan["views"] if v["name"] == "FRONT")
    across = sorted(round(dim["measure"], 2) for dim in front["dimensions"]
                    if not dim["vertical"])
    # A ladder: where every straight ends, then the overall width outside
    # them all. The bounding box alone - one number - is not a drawing
    # anyone can bend a tube from.
    check("the front view stacks a ladder of widths",
          len(across) >= 4, str(across))
    check("with the overall width the largest of them",
          across and abs(across[-1] - part.parameters["overall_width"]) < 0.6,
          str(across))
    check("and each one wider than the last, so none is drawn twice",
          all(b - a > 1.0 for a, b in zip(across, across[1:])), str(across))
    # The envelope of this bar is 148 tall - tube included - and its rise is
    # 126. The drawing has to say 126, because that is what it is bent to.
    rises = [round(dim["measure"], 2) for dim in front["dimensions"]
             if dim["vertical"]]
    check("the height is the rise to the grips, not the envelope",
          any(abs(rise - part.parameters["rise"]) < 0.6 for rise in rises),
          str(rises))
    # Every dimension line has to be inside the frame it was drawn on.
    for view in plan["views"]:
        ys = [dim["p1"][1] + dim["offset"] for dim in view["dimensions"]]
        check(f"{view['name']} keeps its dimensions on the sheet",
              all(drawing.FRAME_T < y < drawing.FRAME_B for y in ys),
              str([round(y, 1) for y in ys]))
        label_y = view["label_at"][1]
        below = [y for y in ys if not view["name"] == "ISO" and y > label_y]
        check(f"{view['name']} puts its label below them, not through them",
              not below, str([round(y, 1) for y in below]))

    print("\nEvery bend answers to the words the trade uses for it")
    # The chart a custom shop sells off says "mini apes" and "apes"; the
    # catalogue said those were not handlebars at all. And "a high road
    # handlebar" came back as the medium bend, because the sentence also
    # contains "road handlebar" - a silent substitution, which is the one
    # thing the router exists to prevent.
    spoken = {
        "a drag bar": "drag", "a drag handlebar": "drag",
        "tracker bars": "tracker", "a tracker handlebar": "tracker",
        "an ultra low handlebar": "road_ultra_low",
        "an ultra-low bend handlebar": "road_ultra_low",
        "a low bend handlebar": "road_low", "a low road handlebar": "road_low",
        "a road handlebar": "road_medium", "a road bar": "road_medium",
        "a medium bend handlebar": "road_medium",
        "a high bend handlebar": "road_high",
        "a high road handlebar": "road_high",
        "a commuter handlebar": "commuter",
        "a classic handlebar": "classic", "a roadster handlebar": "classic",
        "mini apes": "mini_ape", "mini ape hangers": "mini_ape",
        "a mini-ape handlebar": "mini_ape",
        "apes": "ape", "ape hangers": "ape", "an ape bar": "ape",
    }
    wrong = []
    for phrase, style in spoken.items():
        routed = router.select(phrase)
        if routed is None or not routed.part.id.startswith(f"handlebar_{style}_"):
            wrong.append(f"{phrase} -> "
                         f"{routed.part.id if routed else 'nothing'}")
    check("all ten answer to their own names, in every phrasing",
          not wrong, "; ".join(wrong[:3]))
    check("a qualifier beats the family it qualifies",
          router.select("a high road handlebar").part.id.startswith(
              "handlebar_road_high_")
          and router.select("mini ape hangers").part.id.startswith(
              "handlebar_mini_ape_"))
    # "apes" is a bar. "shapes", "aperture" and "landscape" contain it and
    # are not, which is why the nouns are matched on word boundaries.
    for innocent in ("a bracket with a tapered shape", "an aperture plate",
                     "a landscape bracket", "a grip for a shaped handle"):
        check(f"'{innocent}' is not read as a handlebar",
              router.select(innocent) is None and not router.options(innocent))

    print("\nOne request with several right answers offers all of them")
    # No bend named. Four bends rather than a refusal, and rather than one
    # of the ten picked quietly.
    spread = handlebars.shortlist()
    check("a bare request gets a spread, not four near neighbours",
          len(spread) == handlebars.OPTIONS
          and len({handlebars.BARS[name].rise for name in spread}) == len(spread),
          str([f"{name} {handlebars.BARS[name].rise:g}" for name in spread]))
    rises = [handlebars.BARS[name].rise for name in spread]
    check("covering the flattest bend and the tallest",
          min(rises) == min(bar.rise for bar in handlebars.BARS.values())
          and max(rises) == max(bar.rise for bar in handlebars.BARS.values()),
          f"{min(rises):g} to {max(rises):g}")
    near = handlebars.shortlist(rise=152.0)
    check("a stated rise gets the bends nearest it, closest first",
          handlebars.BARS[near[0]].rise == 152.0
          and all(abs(handlebars.BARS[a].rise - 152.0)
                  <= abs(handlebars.BARS[b].rise - 152.0)
                  for a, b in zip(near, near[1:])),
          str([f"{name} {handlebars.BARS[name].rise:g}" for name in near]))
    inch = handlebars.shortlist(tube=25.4)
    check("a stated tube gets only the bends built on it",
          inch and all(handlebars.BARS[name].tube_diameter == 25.4
                       for name in inch), str(inch))

    offered = router.options("a handlebar")
    check("the router offers them, each one built and checked",
          len(offered) == handlebars.OPTIONS
          and all(routed.report.ok for routed in offered),
          str([routed.part.title.split(",")[0] for routed in offered]))
    check("a named bend is answered exactly, not offered as a choice",
          not router.options("a drag bar")
          and router.select("a drag bar") is not None)
    check("and so is every other standard part",
          not router.options("an M8 flat washer")
          and not router.options("a 20 tooth spur gear, module 2"))
    check("a riser is still not a handlebar", not router.options("a handlebar riser"))

    # A width the bend has no room for is refused with the reason, not
    # quietly widened to one that fits.
    squeezed = router.options("a 700 mm handlebar")
    check("a width that will not bend is declined, with the reason",
          squeezed.declined
          and all("cannot be bent" in why for _, why in squeezed.declined),
          str([title.split(",")[0] for title, _ in squeezed.declined]))
    check("and the ones that do fit come out at the width asked for",
          all(routed.part.parameters["overall_width"] == 700.0
              for routed in squeezed),
          str([routed.part.parameters["overall_width"] for routed in squeezed]))
    check("one survivor is not a choice, so nothing is offered",
          not router.options("a 500 mm handlebar"),
          str(len(router.options("a 500 mm handlebar").declined)) + " declined")

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
