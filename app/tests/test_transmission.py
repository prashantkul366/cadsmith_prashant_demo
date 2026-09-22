"""The turning half of the catalogue: shafts, keys, collars, couplings, gears.

Written against a specific report. Asked for "spur gear 50mm diameter", the
pipeline spent nearly five minutes writing a gear from scratch and produced a
star polygon with trapezoidal teeth - not an involute, so not a gear that
meshes. The catalogue could have answered instantly and exactly, and did not,
because the router took a tooth count as the only way to specify a gear and a
diameter as no specification at all.

So the first group here is that request, end to end, measured. The rest cover
the families that went in alongside it, because a gear needs a shaft, a shaft
needs a key, and none of those could be served either.

Runs the real OpenCASCADE kernel throughout: a part that builds cleanly to
the wrong size is the failure that matters, and only measuring catches it.

    .venv/bin/python -m app.tests.test_transmission
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.catalog import parts, router, standards, verify  # noqa: E402
from app.server import edits  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def near(a: float, b: float, tol: float = 0.05) -> bool:
    return abs(a - b) <= tol


def measure(part):
    """Build a part and hand back its report and bounding box."""
    report = verify.check(part)
    return report


# ---------------------------------------------------------------------------

def test_a_gear_can_be_asked_for_by_diameter() -> None:
    """The reported failure, from the words typed to the solid measured."""
    print("\n'spur gear 50mm diameter' - the request that went to the agents")

    routed = router.select("spur gear 50mm diameter")
    check("the catalogue answers it at all", routed is not None)
    if routed is None:
        return

    check("it is a spur gear", "spur gear" in routed.part.title.lower(),
          routed.part.title)
    check("with a whole tooth count",
          float(routed.part.parameters["teeth"]).is_integer(),
          str(routed.part.parameters["teeth"]))
    check("at a preferred ISO 54 module",
          routed.part.parameters["module"] in standards.GEAR_MODULES,
          str(routed.part.parameters["module"]))

    report = routed.report
    check("the solid is sound", report.ok, report.summary())
    # A gear does not measure its tip diameter in every direction: only
    # where two tips oppose each other. With 18 teeth that is across the
    # flats of the 20 degree pitch angle, and at 90 degrees to it a caliper
    # lands between teeth and reads cos(10 degrees) less. So the check is
    # that the tip circle is 50mm - the largest span - and that the smallest
    # is no further under it than one half pitch angle accounts for.
    import math
    pitch_angle = 2.0 * math.pi / routed.part.parameters["teeth"]
    across = max(report.bbox[0], report.bbox[1])
    least = min(report.bbox[0], report.bbox[1])
    check("its tip diameter is the 50mm that was asked for",
          near(across, 50.0, 0.05), f"{across:.2f} mm across the tips")
    check("and no direction reads less than the tooth spacing allows",
          least >= 50.0 * math.cos(pitch_angle / 2.0) - 0.05,
          f"{least:.2f} mm, floor "
          f"{50.0 * math.cos(pitch_angle / 2.0):.2f}")

    # The failure in the report was not a wrong size, it was a wrong flank:
    # four straight lines per tooth instead of an involute. A spline-built
    # involute leaves far more faces than a trapezoid does, so the face count
    # is enough to tell them apart.
    check("the teeth are involute, not the trapezoids a model reaches for",
          report.num_faces > routed.part.parameters["teeth"] * 4,
          f"{report.num_faces} faces for "
          f"{routed.part.parameters['teeth']:g} teeth")

    check("the answer is instant, not a five minute pipeline run",
          report.build_ms < 10000, f"{report.build_ms:.0f} ms")


def test_gear_sizing_is_exact_or_refused() -> None:
    print("\nA diameter either lands on a real gear or is handed back")
    for diameter, expected in ((50.0, (18, 2.5)), (60.0, (10, 5.0)),
                               (100.0, (18, 5.0))):
        got = standards.gear_teeth_for_diameter(diameter)
        check(f"{diameter:g}mm tip diameter", got == expected,
              f"{got} (wanted {expected})")
        if got:
            teeth, module = got
            check(f"  and {teeth}t module {module:g} really is {diameter:g}mm",
                  near(module * (teeth + 2), diameter, 0.001))

    check("a diameter no preferred module reaches is refused, not rounded",
          standards.gear_teeth_for_diameter(31.4) is None)
    check("and so is one too small to be a gear",
          standards.gear_teeth_for_diameter(4.0) is None)

    check("a pitch diameter is read as a pitch diameter",
          standards.gear_teeth_for_diameter(45.0, "pitch") == (15, 3.0),
          str(standards.gear_teeth_for_diameter(45.0, "pitch")))


def test_every_new_part_builds() -> None:
    print("\nEvery new family builds one sound solid")
    cases = [
        ("shaft, plain", parts.shaft(20.0, 100.0)),
        ("shaft, keyed", parts.shaft(20.0, 100.0, keyway=True)),
        ("shaft, keyed and grooved",
         parts.shaft(20.0, 100.0, keyway=True, ring_groove=True)),
        ("parallel key", parts.parallel_key(20.0)),
        ("plain bushing", parts.plain_bushing(12.0)),
        ("set screw", parts.set_screw("M6", 10.0)),
        ("threaded rod", parts.threaded_rod("M8", 100.0)),
        ("retaining ring", parts.retaining_ring(20.0)),
        ("shaft collar", parts.shaft_collar(12.0)),
        ("shaft collar, no clamp", parts.shaft_collar(12.0, clamp=False)),
        ("coupling", parts.rigid_coupling(12.0)),
        ("coupling, two sizes", parts.rigid_coupling(8.0, 12.0)),
    ]
    for label, part in cases:
        report = measure(part)
        check(label, report.ok, report.summary())


def test_every_listed_family_builds_at_its_defaults() -> None:
    """parts.BUILDERS is the index of what this module can make. A family
    listed there that does not build at its own defaults is a family nobody
    can reach without already knowing the sizes to pass."""
    print("\nEvery family in BUILDERS builds with no arguments")
    for name, builder in sorted(parts.BUILDERS.items()):
        try:
            report = measure(builder())
            check(name, report.ok, report.summary())
        except Exception as exc:
            check(name, False, f"{type(exc).__name__}: {exc}")


def test_the_awkward_sizes_build_too() -> None:
    """The small and large ends, where a proportion can go through a wall."""
    print("\nThe ends of each range, where proportions collide")
    for bore in (6.0, 8.0, 20.0, 30.0, 50.0):
        report = measure(parts.shaft_collar(bore))
        check(f"collar, {bore:g}mm bore", report.ok, report.summary())
    for bore in (6.0, 12.0, 25.0, 40.0):
        report = measure(parts.rigid_coupling(bore))
        check(f"coupling, {bore:g}mm bore", report.ok, report.summary())


def test_dimensions_match_the_standard() -> None:
    print("\nThe geometry matches the table it came from")

    spec = standards.key_for_shaft(20.0)
    report = measure(parts.parallel_key(20.0))
    check("a key for a 20mm shaft is 6 x 6 to DIN 6885",
          near(spec.width, 6.0) and near(spec.height, 6.0),
          f"{spec.width:g} x {spec.height:g}")
    check("and the solid is that size",
          near(report.bbox[1], spec.width, 0.01)
          and near(report.bbox[2], spec.height, 0.01),
          f"{report.bbox[1]:.2f} x {report.bbox[2]:.2f}")

    # The depth that gets invented: a keyway cut to the key's full height
    # leaves the key bearing on its top face instead of its flanks.
    keyed = parts.shaft(20.0, 100.0, keyway=True)
    check("the keyway is cut to t1, not to the key's height",
          near(keyed.parameters["keyway_depth"], spec.shaft_depth)
          and keyed.parameters["keyway_depth"] < spec.height,
          f"t1 {spec.shaft_depth:g} vs h {spec.height:g}")

    plain = measure(parts.shaft(20.0, 100.0))
    keyed_report = measure(keyed)
    check("and cutting it actually removes metal",
          keyed_report.volume < plain.volume,
          f"{plain.volume:.0f} -> {keyed_report.volume:.0f} mm3")

    ring = standards.RETAINING_RINGS[20.0]
    check("a DIN 471 groove is well under the shaft it is turned in",
          ring.groove_diameter < 20.0 - 0.5,
          f"d3 {ring.groove_diameter:g} on a 20mm shaft")

    bushing = standards.BUSHINGS[12.0]
    report = measure(parts.plain_bushing(12.0))
    check("a bushing measures its outside diameter",
          near(report.bbox[0], bushing.outer_diameter, 0.05),
          f"{report.bbox[0]:.2f} vs D {bushing.outer_diameter:g}")

    report = measure(parts.threaded_rod("M8", 50.0))
    check("threaded rod is modelled at the pitch diameter, under M8",
          report.bbox[0] < 8.0, f"{report.bbox[0]:.2f}mm across")


def test_tables_are_sane() -> None:
    print("\nThe new tables agree with themselves")
    bad = [d for d, k in standards.PARALLEL_KEYS.items()
           if not k.shaft_depth < k.height or not k.hub_depth < k.height]
    check("every key is deeper in neither slot than it is tall", not bad,
          str(bad))
    bad = [d for d, k in standards.PARALLEL_KEYS.items()
           if k.shaft_depth + k.hub_depth <= k.height]
    check("but the two slots together are deeper than the key, so it "
          "bears on its flanks", not bad, str(bad))

    bad = [d for d, r in standards.RETAINING_RINGS.items()
           if r.groove_diameter >= d or r.free_diameter <= d]
    check("every ring seats below its shaft and stands proud of it",
          not bad, str(bad))
    bad = [d for d, r in standards.RETAINING_RINGS.items()
           if r.groove_width < r.thickness]
    check("and every groove is wider than the ring going into it",
          not bad, str(bad))

    bad = [d for d, b in standards.BUSHINGS.items()
           if b.outer_diameter <= b.bore]
    check("every bushing has a wall", not bad, str(bad))

    check("the modules are sorted and unique",
          list(standards.GEAR_MODULES) == sorted(set(standards.GEAR_MODULES)))
    check("the shaft sizes are sorted and unique",
          list(standards.SHAFT_DIAMETERS)
          == sorted(set(standards.SHAFT_DIAMETERS)))

    check("a key is tabled for every shaft size that has a ring",
          all(d <= max(standards.PARALLEL_KEYS)
              for d in standards.RETAINING_RINGS))


def test_the_router_knows_what_it_is_being_asked_for() -> None:
    print("\nWhat the catalogue answers, and what it hands to the pipeline")

    serve = [
        ("spur gear 50mm diameter", "spur gear"),
        ("a 50 mm diameter spur gear", "spur gear"),
        ("spur gear, 45mm pitch diameter", "spur gear"),
        ("a 20 tooth spur gear module 2", "spur gear"),
        ("a 20mm shaft 150mm long", "shaft"),
        ("a 20mm keyed shaft", "keyway"),
        ("an axle 10mm diameter 80mm long", "shaft"),
        ("a shaft collar for a 12mm shaft", "collar"),
        ("a 20mm shaft collar", "collar"),
        ("a rigid shaft coupling for a 10mm shaft", "coupling"),
        ("a shaft coupling, 8mm to 12mm", "coupling"),
        ("a parallel key for a 20mm shaft", "key"),
        ("a 12mm plain bearing", "bushing"),
        ("a 16mm sleeve bearing 20mm long", "bushing"),
        ("an M6 set screw 10mm long", "set screw"),
        ("M8 threaded rod 200mm long", "threaded rod"),
        ("a circlip for a 20mm shaft", "retaining ring"),
        ("a retaining ring for a 25mm shaft", "retaining ring"),
    ]
    for text, expected in serve:
        routed = router.select(text)
        title = routed.part.title.lower() if routed else ""
        check(f"{text!r}", expected in title,
              routed.part.title if routed else "declined")

    # Each of these mentions a part this catalogue can build, inside a
    # request for something it cannot. Serving the mentioned part would be
    # silently wrong, which is worse than being slow.
    decline = [
        "a gearbox with a 50mm gear",
        "a bearing for a 20mm shaft",
        "a bracket to hold a 20mm shaft",
        "a pillow block for a 20mm shaft",
        "a housing for a 6203 bearing",
        "a shaft support block",
        "a shaft",                       # no size at all
        "a coupling",
        "a 31.4mm spur gear",            # no preferred module reaches it
        "a flexible jaw coupling for a 10mm shaft",
        "a woodruff key for a 20mm shaft",
        "an internal retaining ring for a 40mm bore",
        "a plate with a 20mm hole",
    ]
    for text in decline:
        routed = router.select(text)
        check(f"{text!r} goes to the pipeline", routed is None,
              routed.part.title if routed else "")


def test_the_new_parts_are_editable() -> None:
    """Same bar the rest of the catalogue is held to: the emitted source has
    to survive the app's own parameter editor, or the sliders do nothing."""
    print("\nThe emitted source survives the parameter editor")

    for part in (parts.shaft(20.0, 100.0, keyway=True),
                 parts.shaft_collar(12.0),
                 parts.rigid_coupling(12.0),
                 parts.parallel_key(20.0),
                 parts.plain_bushing(12.0)):
        found = edits.parameters(part.code)
        check(f"{part.id}: the editor reads its parameters", bool(found),
              ", ".join(sorted(found)))
        check(f"{part.id}: no dimension is mistaken for a count",
              not any(p.is_integer for p in found.values()),
              ", ".join(n for n, p in found.items() if p.is_integer))

    shaft = parts.shaft(20.0, 100.0)
    plan = edits.plan_edit(shaft.code, "make the length 150mm")
    check("a length change is understood",
          bool(plan.changes) and plan.changes[0].name == "length"
          and plan.changes[0].new == 150.0,
          plan.changes[0].name if plan.changes else plan.reason)
    if plan.changes:
        patched = edits.apply_changes(shaft.code, plan.changes)
        solid, _ = verify.build(patched)
        box = solid.BoundingBox()
        check("and the kernel rebuilds it at the new length",
              near(box.zlen, 150.0, 0.05), f"{box.zlen:.2f}mm long")


def main() -> int:
    test_a_gear_can_be_asked_for_by_diameter()
    test_gear_sizing_is_exact_or_refused()
    test_every_new_part_builds()
    test_every_listed_family_builds_at_its_defaults()
    test_the_awkward_sizes_build_too()
    test_dimensions_match_the_standard()
    test_tables_are_sane()
    test_the_router_knows_what_it_is_being_asked_for()
    test_the_new_parts_are_editable()

    print("\n" + "=" * 58)
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED: {', '.join(failures[:6])}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
