"""A TechDraw sheet built in a real FreeCAD, and read back.

The other road draws its own sheet - it projects the solid, lays out the
views and writes SVG, which is a picture of a drawing. On this road
FreeCAD is already open with the part in it, so the sheet can be a
TechDraw page in the same document: real views, real dimension objects
attached to real edges, a page the engineer opens and edits.

What is checked is not that it ran. A dimension attached to the wrong
edge looks exactly like one attached to the right edge until somebody
reads the number, so every dimension placed is read back with
getRawValue() and compared against the part it was supposed to measure.

Needs a FreeCAD with TechDraw. Skips where there is none, like the
browser tests do, because a missing tool is not a failing test.

Run:  .venv/bin/python -m app.tests.test_techdraw
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.server import techdraw  # noqa: E402

#: Where a freecadcmd might be. The environment variable first, so an
#: engineer with FreeCAD somewhere of their own can point at it.
CANDIDATES = [os.environ.get("CADSMITH_FREECADCMD", ""),
              "freecadcmd", "FreeCADCmd",
              "/tmp/claude-0/fc/bin/freecadcmd"]

#: A 120 x 80 x 12 plate with four 6.6 holes, built in FreeCAD's own
#: primitives so the test needs nothing but FreeCAD.
SETUP = '''
import FreeCAD
doc = FreeCAD.newDocument("Part")
box = doc.addObject("Part::Box", "B")
box.Length, box.Width, box.Height = 120, 80, 12
holes = []
for x, y in ((-45, -25), (45, -25), (45, 25), (-45, 25)):
    c = doc.addObject("Part::Cylinder", "C%d_%d" % (abs(x), abs(y)))
    c.Radius, c.Height = 3.3, 40
    c.Placement.Base = FreeCAD.Vector(60 + x, 40 + y, -10)
    holes.append(c)
fused = doc.addObject("Part::MultiFuse", "Holes")
fused.Shapes = holes
cut = doc.addObject("Part::Cut", "Widget")
cut.Base, cut.Tool = box, fused
doc.recompute()
'''


#: A square plate with its corners broken, which is the shape the old
#: rule for the overall dimension could not measure. Picking the longest
#: straight edge is ambiguous on a square - half of them run the wrong
#: way, and a DistanceX across a vertical edge reads 0 - and the break
#: makes every straight edge 98 of a part that is 100 across.
SQUARE = '''
import FreeCAD
doc = FreeCAD.newDocument("Part")
box = doc.addObject("Part::Box", "B")
box.Length, box.Width, box.Height = 100, 100, 10
doc.recompute()
broken = doc.addObject("Part::Chamfer", "Widget")
broken.Base = box
vertical = [i + 1 for i, e in enumerate(box.Shape.Edges)
            if abs(e.Vertexes[0].Point.z - e.Vertexes[-1].Point.z) > 1e-6]
broken.Edges = [(i, 1.0, 1.0) for i in vertical]
doc.recompute()
'''


#: A round plate, which has no straight edge at all and only a handful of
#: referenceable vertices - none of them where it is widest. Measured on
#: the library's parts, that is where attaching the overall to a model
#: vertex gave 11 for a part 22 across.
DISC = '''
import FreeCAD
doc = FreeCAD.newDocument("Part")
disc = doc.addObject("Part::Cylinder", "Widget")
disc.Radius, disc.Height = 30, 10
doc.recompute()
'''


def freecadcmd() -> str:
    for candidate in CANDIDATES:
        if not candidate:
            continue
        found = shutil.which(candidate) or (
            candidate if os.path.exists(candidate) else "")
        if found:
            return found
    return ""


class Bridge:
    """The surface the RPC bridge offers, backed by a freecadcmd.

    The module under test only ever calls `run`, which is the whole point
    of it talking to FreeCAD through a bridge: the same code works against
    the engineer's live FreeCAD and against a command-line one here.
    """

    def __init__(self, binary: str, setup: str) -> None:
        self.binary, self.setup = binary, setup

    def run(self, code: str, timeout: float = 180.0) -> str:
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".py", delete=False, encoding="utf-8")
        handle.write("# -*- coding: utf-8 -*-\n" + self.setup + "\n" + code)
        handle.close()
        try:
            done = subprocess.run([self.binary, handle.name],
                                  capture_output=True, text=True,
                                  timeout=timeout)
            return (done.stdout or "") + (done.stderr or "")
        finally:
            os.unlink(handle.name)


def main() -> int:
    binary = freecadcmd()
    if not binary:
        print("SKIP  no freecadcmd found - the TechDraw sheet is not checked")
        return 0

    failures = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        if not ok:
            failures += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}"
              + (f" - {detail}" if detail else ""))

    print("What to ask TechDraw for, from what the solid said")
    wanted = techdraw.scheme([
        {"radius": 3.3,
         "label": "4× Ø6.6 THRU ⌴Ø11 ▼6.5"}])
    check("an overall length and a diameter per hole",
          len(wanted) == 2 and wanted[0]["type"] == "DistanceX"
          and wanted[1]["type"] == "Diameter", str([w["type"] for w in wanted]))
    # TechDraw measures the edge itself and writes the value where %.2w
    # is; what the solid knew and the edge cannot - the depth, and the
    # counterbore over it - rides along after it.
    check("with the measured value left to TechDraw",
          wanted[1]["spec"].startswith("%.2w"), wanted[1]["spec"])
    check("and what only the kernel knew carried after it",
          "THRU" in wanted[1]["spec"] and "▼6.5" in wanted[1]["spec"],
          wanted[1]["spec"])

    print("\nThe page, in a real FreeCAD")
    answer = techdraw.build(Bridge(binary, SETUP), "Part", "Widget", wanted)
    check("it drew one", answer.get("ok") and answer.get("page"),
          answer.get("why") or str(answer.get("page")))
    if not answer.get("ok"):
        print("\n" + "=" * 58)
        print("1 CHECK(S) FAILED")
        return 1
    check("with three aligned views, not three loose ones",
          answer.get("views") == 3, str(answer.get("views")))
    check("and nothing it was asked for was skipped",
          not answer.get("skipped"), str(answer.get("skipped"))[:90])

    print("\nEvery dimension measures what it was meant to")
    placed = {d["type"]: d["value"] for d in answer.get("dimensions", [])}
    check("the overall length is the part's 120, not some other edge",
          abs(placed.get("DistanceX", 0) - 120.0) < 0.01,
          str(placed.get("DistanceX")))
    check("the diameter is the 6.6 hole, not the 120 edge beside it",
          abs(placed.get("Diameter", 0) - 6.6) < 0.01,
          str(placed.get("Diameter")))

    print("\nThe overall dimension on a part whose edges do not help")
    square = techdraw.build(Bridge(binary, SQUARE), "Part", "Widget",
                            [{"type": "DistanceX", "spec": ""},
                             {"type": "DistanceY", "spec": ""}])
    across = {d["type"]: d["value"] for d in square.get("dimensions", [])}
    check("a square plate is 100 across, not 0 and not 98",
          abs(across.get("DistanceX", 0) - 100.0) < 0.01,
          square.get("why") or str(across.get("DistanceX")))
    check("and 100 the other way, measured in that direction",
          abs(across.get("DistanceY", 0) - 100.0) < 0.01,
          str(across.get("DistanceY")))
    check("with neither of them refused", not square.get("skipped"),
          str(square.get("skipped"))[:90])

    round_plate = techdraw.build(Bridge(binary, DISC), "Part", "Widget",
                                 [{"type": "DistanceX", "spec": ""}])
    wide = {d["type"]: d["value"] for d in round_plate.get("dimensions", [])}
    check("a round plate is as wide as it is, with no edge to measure",
          abs(wide.get("DistanceX", 0) - 60.0) < 0.01,
          round_plate.get("why") or str(wide.get("DistanceX")))

    print("\n" + "=" * 58)
    print("ALL CHECKS PASSED" if not failures else f"{failures} CHECK(S) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
