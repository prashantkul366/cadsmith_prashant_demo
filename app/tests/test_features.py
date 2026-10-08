"""Features found in a projection, and dimensioned off it.

A drawing is dimensioned from what it draws, and what it drew was the
outline: the bounding box, the circles, the corner radii. Everything cut
into that outline which is not round - a slit, a slot, a pocket, a window -
projects as a closed loop inside the boundary, and the projector hands it
over as a heap of unrelated edges, so nothing downstream could see one.
They were drawn, and the sheet said nothing about any of them.

Nothing is mocked: each case builds a solid with CadQuery, projects it the
way the app does, and reads the features back out.

The cases that matter most are the ones where a feature must *not* be
found, because a wrong dimension on a drawing is worse than a missing one -
somebody machines to it.

Run:  .venv/bin/python -m app.tests.test_features
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cadquery as cq  # noqa: E402

from app.server import drawing, features  # noqa: E402


def found(solid, into: Path, name: str, view: str = "TOP") -> list[dict]:
    step = into / f"{name}.step"
    cq.exporters.export(solid, str(step))
    views = drawing._project(step)            # noqa: SLF001
    return features.groups(features.cutouts(views[view]))


def sizes(got) -> set:
    return {(round(g["w"], 2), round(g["h"], 2)) for g in got}


def main() -> int:
    failures = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        if not ok:
            failures += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}"
              + (f" - {detail}" if detail else ""))

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)

        print("A cut-out that is not round is still a feature")
        # The shape the whole thing was found on: a thin strip with a slit
        # through it. The slit was on the page and its size was not.
        strip = (cq.Workplane("XY").box(90.0, 12.0, 2.0)
                 .faces(">Z").workplane().rect(0.5, 10.0).cutThruAll())
        got = found(strip, work, "strip")
        check("a 0.5 x 10 slit is found and measured",
              (0.5, 10.0) in sizes(got), str(sizes(got)))

        print("\nIdentical cut-outs are one dimension and a count")
        five = (cq.Workplane("XY").box(120.0, 20.0, 2.0)
                .faces(">Z").workplane()
                .pushPoints([(x, 0) for x in (-45, -22.5, 0, 22.5, 45)])
                .rect(0.5, 10.0).cutThruAll())
        got = found(five, work, "five")
        slits = [g for g in got if round(g["w"], 2) == 0.5]
        check("five slits are one group of five", bool(slits)
              and slits[0]["count"] == 5,
              str([(g["count"], round(g["w"], 2)) for g in got]))
        check("and their pitch is read off their spacing",
              bool(slits) and abs(slits[0]["pitch_u"] - 22.5) < 0.01,
              f"{slits[0]['pitch_u'] if slits else '-'}")

        print("\nA pocket is a feature; the cavity of a shell is too")
        pocket = (cq.Workplane("XY").box(100.0, 60.0, 20.0)
                  .faces(">Z").workplane().rect(40.0, 30.0).cutBlind(-5.0))
        check("a 40 x 30 pocket is found",
              (40.0, 30.0) in sizes(found(pocket, work, "pocket")),
              str(sizes(found(pocket, work, "pocket"))))
        shell = (cq.Workplane("XY")
                 .box(60.0, 40.0, 30.0, centered=(True, True, False))
                 .edges("|Z").fillet(5.0).faces(">Z").shell(-2.0))
        check("and a 2mm shell leaves a 56 x 36 cavity",
              (56.0, 36.0) in sizes(found(shell, work, "shell")),
              str(sizes(found(shell, work, "shell"))))

        print("\nWhat must not be found, because it would be a wrong number")
        # A hole is already called out with a diameter and a centre line.
        # Dimensioning it again across its box is the sheet contradicting
        # itself about the same feature.
        holed = (cq.Workplane("XY").box(60.0, 40.0, 12.0)
                 .faces(">Z").workplane().hole(10.0))
        check("a round hole is left to the diameter callout",
              not found(holed, work, "holed"),
              str(sizes(found(holed, work, "holed"))))
        # The outline is the envelope, and the overall dimensions carry it.
        plain = cq.Workplane("XY").box(60.0, 40.0, 12.0)
        check("a plain block has no cut-out at all",
              not found(plain, work, "plain"),
              str(sizes(found(plain, work, "plain"))))
        # An isometric is a picture, not a measured projection: its lengths
        # are foreshortened and its circles are ellipses. A 10 mm hole read
        # off one gives 5.773, which is 10 over root 3 and not a dimension
        # of anything. The sheet must take no number from it.
        step = work / "iso.step"
        cq.exporters.export(holed, str(step))
        sheet = drawing.plan_sheet(drawing._project(step))   # noqa: SLF001
        iso = next((v for v in sheet["views"] if v["name"] == "ISO"), None)
        check("and the pictorial view carries no dimension",
              iso is not None and not iso["dimensions"],
              f'{len(iso["dimensions"]) if iso else "no ISO view"}')
        # Dimensions and callouts together: the hole's 10 is a Ø leader,
        # not a dimension line, and both are numbers a reader works to.
        check("so every number on the sheet is a size of the part",
              sorted(set(round(n, 2) for n in features.printed(sheet)))
              == [10.0, 12.0, 40.0, 60.0],
              str(sorted(set(round(n, 2) for n in features.printed(sheet)))))

        print("\nWhat the part declares that the sheet does not carry")
        declared = [{"name": "plate_length", "value": 60.0, "kind": "length"},
                    {"name": "hole_diameter", "value": 10.0, "kind": "length"},
                    {"name": "pocket_depth", "value": 5.0, "kind": "length"},
                    {"name": "hole_count", "value": 1.0, "kind": "count"}]
        missing = features.undimensioned(sheet, declared)
        check("a length that reached the page is not reported",
              "plate_length" not in missing and "hole_diameter" not in missing,
              str(missing))
        check("a length that did not is", "pocket_depth" in missing,
              str(missing))
        check("and a count is not a length, so it is left out",
              "hole_count" not in missing, str(missing))

    print("\n" + "=" * 58)
    print("ALL CHECKS PASSED" if not failures else f"{failures} CHECK(S) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
