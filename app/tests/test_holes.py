"""Holes read off the solid, which is the only place their depth is.

A projection shows a hole as a circle, and a circle has no depth. So the
sheet could say Ø8.5 and never whether that is through twenty millimetres
or six, and it could not tell a counterbore from two holes that happen to
share a centre. Measured across every drawing this app has made, those are
the three worst-covered kinds of dimension on it:

    depth        21 on the page, 125 missing   14%
    counterbore  12 on the page,  58 missing   17%
    thread       20 on the page, 120 missing   14%

Every cylindrical face carries its radius, its axis and how far it runs
along that axis, so the kernel can answer all three. Nothing here is
mocked: each case builds a solid and reads it.

Run:  .venv/bin/python -m app.tests.test_holes
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cadquery as cq  # noqa: E402

from app.server import holes  # noqa: E402

PLATE_T = 12.0


def called(part, extent=PLATE_T, threads=None) -> list[str]:
    found = holes.holes(part.val(), extent=extent)
    return [g["label"] for g in holes.grouped(found, threads)]


def main() -> int:
    failures = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        if not ok:
            failures += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}"
              + (f" - {detail}" if detail else ""))

    print("How deep, which the drawing could not say at all")
    plate = (cq.Workplane("XY").box(100, 60, PLATE_T)
             .faces(">Z").workplane().pushPoints([(-30, 0)]).hole(8.5)
             .faces(">Z").workplane().pushPoints([(30, 0)])
             .circle(5).cutBlind(-6.0))
    labels = called(plate)
    check("a hole that goes through says so",
          "Ø8.5 THRU" in labels, str(labels))
    check("and one that stops says where",
          "Ø10 ▼6" in labels, str(labels))

    print("\nA counterbore is one feature, not two holes at one place")
    cbored = (cq.Workplane("XY").box(120, 80, PLATE_T).faces(">Z").workplane()
              .rect(90, 50, forConstruction=True).vertices()
              .cboreHole(6.6, 11.0, 6.5))
    labels = called(cbored)
    check("called out as the drill, then what sits over it",
          "4× Ø6.6 THRU ⌴Ø11 ▼6.5" in labels,
          str(labels))
    check("and four of them are one callout",
          len(labels) == 1, str(labels))

    print("\nA tapped hole is named by its thread, not by its drill")
    tapped = (cq.Workplane("XY").box(60, 40, 30).faces(">Z").workplane()
              .pushPoints([(0, 0)]).circle(3.4).cutBlind(-15.0))
    check("M8x1.25, because 6.8 is how it is made and not what it is",
          "M8x1.25 ▼15" in called(tapped, 30.0, {6.8: "M8x1.25"}),
          str(called(tapped, 30.0, {6.8: "M8x1.25"})))
    check("and without the request's threads it is still a hole",
          "Ø6.8 ▼15" in called(tapped, 30.0),
          str(called(tapped, 30.0)))

    print("\nThrough is measured along the hole's own axis")
    # The trap: a hole down Z through a 120 x 80 x 12 plate clears 12 mm,
    # and reading the plan view's bounding box instead offers 80 - which
    # called a hole that went straight through 5.5 deep.
    sideways = (cq.Workplane("XY").box(120, 80, PLATE_T)
                .faces(">X").workplane().pushPoints([(0, 0)]).hole(10.0))
    check("a hole down X clears the part's X, not its Y",
          "Ø10 THRU" in called(sideways, (120.0, 80.0, PLATE_T)),
          str(called(sideways, (120.0, 80.0, PLATE_T))))
    check("and the three extents resolve onto the axis",
          abs(holes.through_depth((0, 0, 1), (120, 80, 12)) - 12) < 1e-9
          and abs(holes.through_depth((1, 0, 0), (120, 80, 12)) - 120) < 1e-9)

    print("\nWhat must not be read as a hole")
    boss = (cq.Workplane("XY").box(60, 60, 10).faces(">Z").workplane()
            .circle(12).extrude(20.0))
    check("a boss is material, not a hole", not called(boss, 30.0),
          str(called(boss, 30.0)))
    plain = cq.Workplane("XY").box(60, 40, PLATE_T)
    check("and a plain block has none", not called(plain), str(called(plain)))

    print("\n" + "=" * 58)
    print("ALL CHECKS PASSED" if not failures else f"{failures} CHECK(S) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
