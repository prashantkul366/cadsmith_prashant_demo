"""Editing a solid that arrived with no feature tree.

The claim here is the one a STEP file makes hard: a part exported from NX
or SolidWorks carries faces and edges and nothing else - no history, no
parameters, no names - and it still has to be modifiable by sentence.

So everything below starts by building a part, exporting it, and *throwing
the code away*. From the import onwards there is no privileged knowledge:
the features are recognised from topology, the selectors are re-derived
each time, and every edit is checked by measuring the result rather than by
trusting the operation.

Runs the real kernel. The model-driven half is skipped unless a backend is
configured, because the geometry has to hold up on its own.

Run:  .venv/bin/python -m app.tests.test_direct
"""

from __future__ import annotations

import math
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cadquery as cq  # noqa: E402

from app.server import direct  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def imported(work: Path):
    """A part, exported and re-imported, so nothing of how it was made survives."""
    part = (cq.Workplane("XY").box(120, 80, 12)
            .faces(">Z").workplane().rect(90, 50, forConstruction=True)
            .vertices().hole(8.5)
            .faces(">Z").workplane().hole(30.0)
            .edges("|Z").fillet(6.0))
    step = work / "part.step"
    cq.exporters.export(part, str(step))
    return cq.importers.importStep(str(step)).val().wrapped


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="cadsmith_direct_"))
    shape = imported(work)

    print("A dead solid gives up its features anyway")
    found = direct.recognise(shape)
    by_id = {f.id: f for f in found}
    check("the mounting holes are found, and counted",
          "hole_8p5" in by_id and by_id["hole_8p5"].count == 4,
          str([f.label for f in found]))
    check("and their arrangement is read off the positions",
          "rectangular pattern 90 x 50" in by_id["hole_8p5"].label,
          by_id["hole_8p5"].label)
    check("the central bore is its own feature, not lumped in with them",
          "hole_30" in by_id and by_id["hole_30"].count == 1)
    check("the corner fillets are fillets, not holes",
          "fillet_6" in by_id and by_id["fillet_6"].kind == "fillet"
          and by_id["fillet_6"].count == 4,
          by_id["fillet_6"].label if "fillet_6" in by_id else "not found")
    # A fillet is a cylinder too. Telling them apart is the whole job: a
    # through hole sweeps the full turn, a blend sweeps the angle between
    # the faces it joins.
    check("no fillet was mistaken for a hole",
          all(f.kind == "hole" for f in found if f.id.startswith("hole"))
          and not any(f.kind == "hole" and abs(f.size - 12.0) < 0.1
                      for f in found))

    print("\nEdits are performed by the kernel and checked by measurement")
    opened = direct.apply(shape, {"op": "resize_hole",
                                  "select": "hole_8p5", "diameter": 11.0})
    # Fill four Ø8.5 holes, drill four Ø11: the volume has to move by
    # exactly that much, or something else changed too.
    expected = (direct.volume(shape)
                + 4 * math.pi * 4.25 ** 2 * 12
                - 4 * math.pi * 5.5 ** 2 * 12)
    check("opening the pattern moves the volume by exactly the metal removed",
          abs(direct.volume(opened) - expected) < 1.0,
          f"{direct.volume(opened):,.1f} vs {expected:,.1f}")
    check("and the part now measures Ø11 where it measured Ø8.5",
          any(f.id == "hole_11" and f.count == 4
              for f in direct.recognise(opened)),
          str([f.label for f in direct.recognise(opened)]))
    # Not exact equality: a boolean re-derives the bounds and leaves a few
    # parts in 10^14 behind. A micron is the tolerance that means "the
    # outside of the part did not move".
    check("nothing else about it moved",
          all(abs(a - b) < 1e-6 for a, b
              in zip(direct.extents(opened), direct.extents(shape))),
          f"{direct.extents(shape)} -> {direct.extents(opened)}")

    filled = direct.apply(shape, {"op": "remove", "select": "hole_8p5"})
    check("filling the holes in puts exactly that metal back",
          abs(direct.volume(filled) - direct.volume(shape)
              - 4 * math.pi * 4.25 ** 2 * 12) < 1.0,
          f"+{direct.volume(filled) - direct.volume(shape):,.1f} mm3")
    check("and they are gone from what the solid reports",
          not any(f.id == "hole_8p5" for f in direct.recognise(filled)))

    flat = direct.apply(shape, {"op": "remove", "select": "fillet_6"})
    check("removing the fillets leaves square corners and more metal",
          direct.volume(flat) > direct.volume(shape)
          and not any(f.kind == "fillet" for f in direct.recognise(flat)),
          f"{direct.volume(shape):,.0f} -> {direct.volume(flat):,.0f} mm3")

    broken = direct.apply(shape, {"op": "add_fillet",
                                  "radius": 2.0, "where": "top"})
    check("a fillet on the top edges takes metal away, and adds faces",
          direct.volume(broken) < direct.volume(shape)
          and len(direct._faces(broken)) > len(direct._faces(shape)),  # noqa: SLF001
          f"{len(direct._faces(shape))} -> {len(direct._faces(broken))} faces")  # noqa: SLF001

    print("\nSelectors are re-derived, so none of them can go stale")
    chained = direct.apply_all(shape, [
        {"op": "resize_hole", "select": "hole_8p5", "diameter": 11.0},
        {"op": "remove", "select": "hole_30"},
    ])
    after = {f.id: f for f in direct.recognise(chained)}
    check("a second edit resolves against the solid the first one left",
          "hole_11" in after and "hole_30" not in after,
          str(list(after)))
    # The oldest sore in this field is a stored face id meaning something
    # else after an edit. Nothing is stored, so a selector that no longer
    # matches cannot quietly hit the wrong face - it fails.
    try:
        direct.apply(filled, {"op": "resize_hole",
                              "select": "hole_8p5", "diameter": 12.0})
        check("a selector that no longer matches is refused", False,
              "it silently did something")
    except KeyError as error:
        check("a selector that no longer matches is refused, by name",
              "hole_8p5" in str(error) and "hole_30" in str(error),
              str(error)[:80])

    print("\nThe kernel refuses what it cannot build")
    try:
        direct.apply(shape, {"op": "add_fillet", "radius": 50.0, "where": "top"})
        check("an impossible fillet is refused", False, "it claimed success")
    except (RuntimeError, ValueError) as error:
        check("an impossible fillet is refused, with a reason",
              "fit" in str(error) or "could not" in str(error), str(error)[:70])
    try:
        direct.apply(shape, {"op": "resize_hole",
                             "select": "fillet_6", "diameter": 10.0})
        check("a fillet cannot be resized as though it were a hole", False)
    except ValueError as error:
        check("a fillet cannot be resized as though it were a hole",
              "not a hole" in str(error), str(error)[:60])

    print("\nAnd it goes back out as STEP, for whoever sent it")
    out = work / "edited.step"
    cq.exporters.export(cq.Workplane(obj=cq.Shape.cast(chained)), str(out))
    reread = cq.importers.importStep(str(out)).val().wrapped
    check("the edited solid survives a round trip through STEP",
          abs(direct.volume(reread) - direct.volume(chained)) < 1.0
          and len(direct.recognise(reread)) == len(direct.recognise(chained)),
          f"{out.stat().st_size:,} bytes")

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
