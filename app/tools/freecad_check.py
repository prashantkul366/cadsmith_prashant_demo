"""Prove the FreeCAD link end to end, against a real FreeCAD.

``app/tests/test_freecad.py`` checks the protocol against a stand-in, which
is all that can be done where FreeCAD is not installed. This is the other
half: run it on a machine with FreeCAD open and the MCP addon's RPC server
started, and it builds a part *in FreeCAD*, brings the solid back, measures
it here, and draws it.

    1. Open FreeCAD
    2. Select the "MCP Addon" workbench
    3. Click "Start RPC Server" in the FreeCAD MCP toolbar
    4. .venv/bin/python -m app.tools.freecad_check

The part it builds is deliberately dull - a plate with four holes and a
pocket - because what is being tested is the link, not the modelling. What
matters is the last section: the numbers come off the solid FreeCAD sent
back, measured by this app's own kernel, not reported by FreeCAD.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.server import freecad, spec  # noqa: E402

PLATE_X, PLATE_Y, PLATE_Z = 80.0, 50.0, 10.0
HOLE_D, POCKET_D = 6.0, 20.0
HOLE_AT = [(12.0, 10.0), (68.0, 10.0), (12.0, 40.0), (68.0, 40.0)]


def build(bridge: freecad.Bridge, document: str) -> None:
    """A plate, four holes and a central pocket - through FreeCAD's own tree.

    Written as objects plus one boolean rather than as a script, so that
    what comes back is a real feature tree a person can open in FreeCAD and
    edit afterwards. That is the whole point of going through FreeCAD: a
    script would have given us a dead solid, which is what we already had.
    """
    bridge.add(document, "Part::Box", "Plate",
               Length=PLATE_X, Width=PLATE_Y, Height=PLATE_Z)

    tools = []
    for index, (x, y) in enumerate(HOLE_AT, start=1):
        name = bridge.add(document, "Part::Cylinder", f"Hole{index}",
                          Radius=HOLE_D / 2.0, Height=PLATE_Z * 3)
        # Placement is not a scalar property, so it goes through the one
        # door that takes arbitrary Python.
        bridge.run(f"""
import FreeCAD
doc = FreeCAD.getDocument({document!r})
obj = doc.getObject({name!r})
obj.Placement = FreeCAD.Placement(
    FreeCAD.Vector({x}, {y}, -{PLATE_Z}), FreeCAD.Rotation(0, 0, 0, 1))
doc.recompute()
""")
        tools.append(name)

    pocket = bridge.add(document, "Part::Cylinder", "Pocket",
                        Radius=POCKET_D / 2.0, Height=PLATE_Z)
    bridge.run(f"""
import FreeCAD
doc = FreeCAD.getDocument({document!r})
obj = doc.getObject({pocket!r})
obj.Placement = FreeCAD.Placement(
    FreeCAD.Vector({PLATE_X / 2}, {PLATE_Y / 2}, {PLATE_Z / 2}),
    FreeCAD.Rotation(0, 0, 0, 1))
doc.recompute()
""")
    tools.append(pocket)

    # One cut against a fused tool body, so the document ends with a single
    # finished object and the export picks it up without a filter.
    bridge.run(f"""
import FreeCAD
doc = FreeCAD.getDocument({document!r})
fused = doc.addObject("Part::MultiFuse", "Tools")
fused.Shapes = [doc.getObject(n) for n in {tools!r}]
doc.recompute()
cut = doc.addObject("Part::Cut", "Finished")
cut.Base = doc.getObject("Plate")
cut.Tool = fused
doc.recompute()
""")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=freecad.DEFAULT_PORT)
    parser.add_argument("--token", default="",
                        help="only if the addon has one set")
    parser.add_argument("--out", default="",
                        help="where to leave the STEP and the drawing")
    parser.add_argument("--keep", action="store_true",
                        help="leave the document open in FreeCAD afterwards")
    args = parser.parse_args()

    out = Path(args.out) if args.out else Path(
        tempfile.mkdtemp(prefix="cadsmith_freecad_"))
    out.mkdir(parents=True, exist_ok=True)
    bridge = freecad.Bridge(host=args.host, port=args.port, token=args.token)

    print(f"FreeCAD at {args.host}:{args.port}")
    if not bridge.alive():
        print("  NOT REACHABLE.\n"
              "  Open FreeCAD, pick the 'MCP Addon' workbench, and click\n"
              "  'Start RPC Server' in the FreeCAD MCP toolbar.")
        return 1
    status = bridge.status()
    print(f"  reachable - {status}")

    document = bridge.new_document("CADSmithCheck")
    print(f"  document: {document}")

    print("\nBuilding in FreeCAD")
    build(bridge, document)
    for solid in bridge.measure(document).get("solids", []):
        print(f"  {solid['label']:12s} {solid['bbox'][0]:7.2f} x "
              f"{solid['bbox'][1]:6.2f} x {solid['bbox'][2]:6.2f}   "
              f"{solid['volume']:10,.0f} mm3   "
              f"{'valid' if solid['valid'] else 'INVALID'}")

    print("\nBringing it back")
    step = bridge.save(document, out / "freecad_part.step")
    print(f"  {step}  ({step.stat().st_size:,} bytes)")
    try:
        stl = bridge.save(document, out / "freecad_part.stl")
        print(f"  {stl}  ({stl.stat().st_size:,} bytes)")
    except freecad.FreeCADError as error:
        print(f"  STL export declined: {error}")

    print("\nMeasured here, by this app's kernel - not reported by FreeCAD")
    geometry = spec.measure_step(step)
    box = geometry["bbox"]
    print(f"  overall      {box['xlen']:.2f} x {box['ylen']:.2f} x "
          f"{box['zlen']:.2f} mm   (asked {PLATE_X:g} x {PLATE_Y:g} x {PLATE_Z:g})")
    print(f"  volume       {geometry['volume']:,.0f} mm3")
    print(f"  watertight   {geometry['is_valid']}")
    print(f"  holes        {geometry['holes']}  (asked 4 x Ø{HOLE_D:g})")

    wrong = []
    if abs(box["xlen"] - PLATE_X) > 0.01 or abs(box["zlen"] - PLATE_Z) > 0.01:
        wrong.append("the plate did not come back the size it was asked for")
    if len([d for d in geometry["holes"] if abs(d - HOLE_D) < 0.01]) != 4:
        wrong.append(f"expected four Ø{HOLE_D:g} holes")
    if not geometry["is_valid"]:
        wrong.append("the solid is not watertight")

    # A bolt circle, which is the thing with no primitive behind it and the
    # reason a model used to write a script. Built in a second document so
    # the plate above is unaffected, and measured here rather than taken on
    # the pattern's word for it.
    # A flat plate with rounded corners, which is the shape this library is
    # mostly made of and the one a corner radius used to be refused on. The
    # upright edges of a pad are the shortest group on a flat part and the
    # longest on a tall one; picking the longest filleted the wrong edges
    # and the kernel said "the corner radius will not fit" at a radius that
    # fits perfectly well.
    print("\nR5 corners on a flat plate, which is where this used to fail")
    try:
        from app.server import freecad_tools as _ft
        flat = _ft.Session(bridge, bridge.new_document("RoundedPlate"))
        flat.extrude_profile(points=[[0, 0], [120, 0], [120, 55], [0, 55]],
                             depth=6, fillet=5, name="plate")
        rounded = bridge.save(flat.document, out / "rounded_plate.step")
        plate = spec.measure_step(rounded)
        side = plate["bbox"]
        print(f"  {side['xlen']:.0f} x {side['ylen']:.0f} x {side['zlen']:.0f}"
              f"  {plate['volume']:,.0f} mm3 against 39,600 square")
        if (abs(side["xlen"] - 120) > 0.01 or abs(side["ylen"] - 55) > 0.01
                or abs(side["zlen"] - 6) > 0.01):
            wrong.append("the rounded plate came back the wrong size")
        elif not 39000 < plate["volume"] < 39590:
            wrong.append("the plate's corners were not rounded: "
                         f"{plate['volume']:,.0f} mm3, and a square one is "
                         f"39,600")
    except Exception as error:
        wrong.append(f"a flat plate with R5 corners would not build: {error}")

    print("\nA bolt circle, by tool rather than by arithmetic")
    try:
        from app.server import freecad_tools
        session = freecad_tools.Session(bridge, bridge.new_document("BoltCircle"))
        session.add_shape(kind="Part::Cylinder", name="Disc",
                          Radius=60, Height=15)
        session.add_shape(kind="Part::Cylinder", name="Bolt", Radius=5,
                          Height=45, position=[45, 0, -15])
        spread = session.pattern_circular(name="Bolt", count=6,
                                          centre=[0, 0, 0])
        session.combine(operation="cut", base="Disc",
                        tools=spread["all_of_them"])
        ring = bridge.save(session.document, out / "bolt_circle.step")
        measured = spec.measure_step(ring)
        bolts = [d for d in measured["holes"] if abs(d - 10.0) < 0.01]
        print(f"  5 tool calls, no script")
        print(f"  {ring}  ({ring.stat().st_size:,} bytes)")
        print(f"  holes        {measured['holes']}  (asked 6 x Ø10)")
        print(f"  watertight   {measured['is_valid']}")
        if len(bolts) != 6:
            wrong.append(f"the bolt circle made {len(bolts)} holes, not 6")
        if not args.keep:
            bridge.run(f"""
import FreeCAD
FreeCAD.closeDocument({session.document!r})
""")
    except Exception as error:
        print(f"  the bolt circle failed: {type(error).__name__}: {error}")
        wrong.append("the bolt circle could not be built")

    print("\nDrawing it")
    try:
        from app.server import drawing
        geometry["bounding_box"] = geometry["bbox"]
        sheet = out / "freecad_part.svg"
        sheet.write_text(drawing.build_sheet(
            step, geometry, "a plate built in FreeCAD", "freecad-check", 1),
            encoding="utf-8")
        print(f"  {sheet}  ({sheet.stat().st_size:,} bytes)")
    except Exception as error:
        print(f"  the drawing failed: {error}")
        wrong.append("the drawing could not be built")

    if not args.keep:
        bridge.run(f"""
import FreeCAD
FreeCAD.closeDocument({document!r})
""")
        print(f"\nClosed {document} in FreeCAD (--keep leaves it open).")

    print("\n" + "=" * 60)
    if wrong:
        for item in wrong:
            print(f"  PROBLEM: {item}")
        return 1
    print("The link works: built in FreeCAD, measured here, drawn here.")
    print(f"Everything is in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
