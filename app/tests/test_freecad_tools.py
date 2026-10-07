"""A model building a part in FreeCAD, start to finish.

The three layers under test are the design: a catalogue part placed whole,
features named the way a drawing names them, and FreeCAD primitives beneath
both as the escape hatch. What every one of them has to do is answer with
what it measured, because that is what lets a model notice at step two that
it asked for the wrong thing.

FreeCAD is not installed here, so the stand-in from ``test_freecad`` is
extended: it keeps a document of objects and, when asked to export, hands
back a real STEP built by this app's own kernel from the sizes it was given.
That is enough for the measured results to be real numbers rather than
fixtures, and for ``find_features`` to recognise genuine topology.

Run:  .venv/bin/python -m app.tests.test_freecad_tools
"""

from __future__ import annotations

import base64
import json
import sys
import tempfile
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cadquery as cq  # noqa: E402

from app.server import freecad, freecad_tools  # noqa: E402
from app.server.toolbox import ToolError  # noqa: E402
from app.tests.test_freecad import StandIn, serve  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


class Modelling(StandIn):
    """The stand-in, but it builds what it is told so exports are real.

    Only boxes and cylinders, cut by a boolean - enough for the tools under
    test to produce geometry whose measurements can be checked rather than
    asserted.
    """

    def __init__(self) -> None:
        super().__init__(b"")
        self.shapes: dict[str, dict] = {}
        self.result: str = ""
        #: Where a document has been saved, so reopening finds it again.
        self.saved: dict[str, str] = {}
        #: Set when a solid has been handed to the document whole, as
        #: ``_edit_feature`` does. The document then holds that and nothing
        #: else, which is the trade a direct edit makes in FreeCAD too.
        self.imported: Path | None = None

    def create_object(self, doc_name, obj_data):
        answer = super().create_object(doc_name, obj_data)
        if answer.get("success"):
            self.shapes[answer["object_name"]] = {
                "type": obj_data["Type"],
                "props": dict(obj_data.get("Properties") or {}),
                "at": (0.0, 0.0, 0.0)}
        return answer

    def edit_object(self, doc_name, obj_name, properties):
        answer = super().edit_object(doc_name, obj_name, properties)
        if answer.get("success") and obj_name in self.shapes:
            self.shapes[obj_name]["props"].update(
                properties.get("Properties") or {})
        return answer

    def _solid(self):
        """Whatever has been asked for, built by the real kernel."""
        if self.imported is not None:
            held = cq.Workplane(obj=cq.importers.importStep(
                str(self.imported)).val())
            # Anything added since the solid was handed over is in the
            # document too, so it is in what the document measures. Without
            # this the stand-in reports no change when a boss is added to an
            # imported part, which is a fixture saying "nothing happened"
            # about something that did.
            for shape in self.shapes.values():
                made = self._primitive(shape)
                if made is not None:
                    held = held.union(made)
            return held
        base = None
        tools = []
        for name, shape in self.shapes.items():
            made = self._primitive(shape)
            if made is None:
                continue
            if base is None and shape["type"] == "Part::Box":
                base = made
            else:
                tools.append(made)
        if base is None:
            base = cq.Workplane("XY").box(10, 10, 10)
        for tool in tools:
            base = base.cut(tool)
        return base

    @staticmethod
    def _primitive(shape):
        """One box or cylinder, where it was put."""
        p = shape["props"]
        if shape["type"] == "Part::Box":
            made = cq.Workplane("XY").box(
                float(p.get("Length", 10)), float(p.get("Width", 10)),
                float(p.get("Height", 10)), centered=(False, False, False))
        elif shape["type"] == "Part::Cylinder":
            made = (cq.Workplane("XY").circle(float(p.get("Radius", 1)))
                    .extrude(float(p.get("Height", 10))))
        else:
            return None
        x, y, z = shape["at"]
        return made.translate((x, y, z))

    def execute_code(self, code, timeout=None):
        self.calls.append(("execute_code", code, timeout))
        # Saving. The stand-in is FreeCAD on this machine, which is how the
        # addon is normally run, so the file does land where it was asked to.
        if "doc.saveAs(" in code:
            where = Path(code.split("doc.saveAs(")[1].split(")")[0].strip("'\""))
            where.parent.mkdir(parents=True, exist_ok=True)
            where.write_bytes(b"stand-in FreeCAD document")
            self.saved[str(where.resolve()).lower()] = self.documents_ and \
                list(self.documents_)[0] or ""
            return self._printed("")
        # Reopening one. The documents here are a single dictionary of
        # objects, so the name that comes back is the one already open -
        # which is what FreeCAD does too when the file is open already.
        if "FreeCAD.listDocuments()" in code:
            wanted = code.split("os.path.abspath(")[1].split(")")[0].strip("'\"")
            name = self.saved.get(str(Path(wanted).resolve()).lower(), "")
            if not name:
                return self._printed("")
            return self._printed(name, marked=True)
        # Placements, so the exported solid lands where it was put.
        if "obj.Placement = FreeCAD.Placement(" in code and "Vector(" in code:
            name = code.split("getObject(")[1].split(")")[0].strip("'\"")
            inside = code.split("Vector(")[1].split(")")[0]
            if name in self.shapes:
                self.shapes[name]["at"] = tuple(
                    float(v) for v in inside.split(","))
            return self._printed("")
        if "cadsmith_export" in code:
            work = Path(tempfile.mkdtemp(prefix="standin_"))
            step = work / "s.step"
            cq.exporters.export(self._solid(), str(step))
            return self._printed(
                base64.b64encode(step.read_bytes()).decode(), marked=True)
        if "BoundBox" in code:
            solid = self._solid().val()
            box = solid.BoundingBox()
            return self._printed(json.dumps([{
                "name": "Result", "label": "Result",
                "volume": solid.Volume(), "area": solid.Area(),
                "faces": len(solid.Faces()), "valid": solid.isValid(),
                "bbox": [box.xlen, box.ylen, box.zlen]}]), marked=True)
        if 'doc.addObject("Part::Cut"' in code or "MultiFuse" in code:
            self.result = "Result"
            return self._printed("Result")
        # A solid handed over whole, which is what a direct feature edit
        # does: every object goes, and one plain shape takes their place.
        if "shape.read(" in code:
            self.imported = Path(
                code.split("shape.read(")[1].split(")")[0].strip("'\""))
            self.shapes.clear()
            # The script removes every object before adding its one plain
            # shape, so anything that asks the document for an object by
            # name has to stop finding it - which is how a caller learns
            # the tree is gone.
            for name in self.documents_:
                self.documents_[name] = [
                    {"Name": "Edited", "Type": "Part::Feature",
                     "Properties": {}}]
            return self._printed("Edited")
        if 'addObject("Part::Feature"' in code:
            return self._printed("StandardPart")
        return self._printed("")

    def _printed(self, payload: str, marked: bool = False):
        """What the addon hands back: FreeCAD's chatter, then the output.

        ``marked`` says whether the script wrapped its answer in the markers
        the bridge looks for. It is passed explicitly rather than guessed
        from the payload - a base64 blob is sometimes all letters and
        digits, and a stand-in that decides by looking at the text fails
        once in a while on nothing but the length of the file.
        """
        body = (freecad._MARK_OPEN + payload + freecad._MARK_CLOSE  # noqa: SLF001
                if marked and payload else payload)
        return {"success": True,
                "message": "Python code executed successfully.\nOutput: " + body}


def _crosses(*points):
    """The outline checker, reached by name so the test states what it means."""
    return freecad_tools._crosses_itself([list(p) for p in points])  # noqa: SLF001


def main() -> int:
    stand_in = Modelling()
    server, port = serve(stand_in)
    bridge = freecad.Bridge(port=port, timeout=20.0)
    session = freecad_tools.Session(bridge)
    box = freecad_tools.toolbox_for(session)

    print("The tools are offered in the order a model should reach for them")
    names = list(box.tools)
    check("the catalogue comes before the primitives",
          names.index("place_standard_part") < names.index("add_shape"),
          ", ".join(names[:3]))
    check("and run_python comes last, so it is not the first thing that fits",
          names[-1] == "run_python", names[-1])
    check("every tool carries a description the model can act on",
          all(len(t.description) > 40 for t in box.tools.values()))

    print("\nBuilding a plate, step by step")
    made = box.invoke("add_shape", {"kind": "Part::Box", "name": "Plate",
                                    "Length": 80, "Width": 50, "Height": 10})
    check("the result says what was measured, not that it worked",
          "part_now" in made and made["part_now"][0]["size_mm"] == [80, 50, 10],
          str(made.get("part_now")))
    check("and the volume is real, from the kernel",
          made["part_now"][0]["volume_mm3"] == 40000.0,
          str(made["part_now"][0]["volume_mm3"]))

    box.invoke("add_shape", {"kind": "Part::Cylinder", "name": "Hole",
                             "Radius": 3, "Height": 30,
                             "position": [20, 25, -10]})
    cut = box.invoke("combine", {"operation": "cut", "base": "Plate",
                                 "tools": ["Hole"]})
    expected = 40000.0 - 3.14159265 * 9 * 10
    check("a cut removes exactly the metal it should",
          abs(cut["part_now"][0]["volume_mm3"] - expected) < 1.0,
          f"{cut['part_now'][0]['volume_mm3']:,.1f} vs {expected:,.1f}")

    print("\nChanging a number re-runs what was built on it")
    grown = box.invoke("set_size", {"name": "Plate", "Length": 100})
    check("the tree recomputed rather than being rebuilt",
          grown["part_now"][0]["size_mm"][0] == 100,
          str(grown["part_now"][0]["size_mm"]))
    check("and the hole is still cut out of it",
          grown["part_now"][0]["volume_mm3"] < 100 * 50 * 10,
          f"{grown['part_now'][0]['volume_mm3']:,.1f}")

    print("\nFeatures are named the way a drawing names them")
    found = box.invoke("find_features", {})
    labels = [f["label"] for f in found["features"]]
    check("the hole is recognised off the solid's own topology",
          any("Ø6" in label for label in labels), str(labels))
    hole = next((f for f in found["features"] if f["kind"] == "hole"), None)
    check("and it carries an id the next call can use",
          hole is not None and hole["id"].startswith("hole_"),
          str(hole))

    print("\nThe shape of the part, not a pile of boxes")
    # The vocabulary gap that made complex parts fail. A bracket is an L, a
    # stepped shaft is one outline spun about an axis; built out of
    # primitives they are four times the calls and wrong in a corner.
    check("an outline padded into a solid is offered before the primitives",
          names.index("extrude_profile") < names.index("add_shape"),
          ", ".join(names[1:4]))
    for call, args, wanted in [
        ("extrude_profile", {"points": [[0, 0], [10, 0]], "depth": 5},
         "at least three"),
        ("extrude_profile", {"points": [[0, 0], [9, 0], [9, 9]], "depth": 0},
         "more than nothing"),
        ("extrude_profile", {"points": [[0, 0], [9, 0], [9, 9]], "depth": 5,
                             "plane": "QQ"}, "one of XY"),
        ("extrude_profile", {"points": [[0, 0], "x", [9, 9]], "depth": 5},
         "[x, y] pair"),
        ("revolve_profile", {"points": [[0, 0], [9, 0], [9, 9]], "angle": 400},
         "0 to 360"),
        ("shell", {"name": "Nowhere", "thickness": 2}, "no object called"),
    ]:
        try:
            box.invoke(call, args)
            check(f"{call} refuses it", False, "it accepted it")
        except ToolError as refused:
            check(f"{call} refuses {str(list(args.values())[0])[:18]}",
                  wanted in str(refused), str(refused)[:60])

    # The one FreeCAD does not refuse. A bow-tie pads into a solid that
    # measures, exports and draws, and is not the part anybody asked for.
    try:
        box.invoke("extrude_profile",
                   {"points": [[0, 0], [10, 10], [10, 0], [0, 10]], "depth": 5})
        check("an outline that crosses itself is refused", False,
              "it padded a bow-tie")
    except ToolError as refused:
        check("an outline that crosses itself is refused",
              "crosses itself" in str(refused), str(refused)[:70])
    check("and the refusal names the two sides to look at",
          _crosses((0, 0), (10, 10), (10, 0), (0, 10)) is not None
          and _crosses((0, 0), (80, 0), (80, 12), (12, 12),
                       (12, 60), (0, 60)) is None,
          "a concave L is not a crossing")

    print("\nRepetition is a tool, not arithmetic in a script")
    # The reason this exists: a bolt circle has no primitive, so a model
    # reaches for run_python and spends about 1,200 output tokens working
    # out six placements - against the 40 a tool call costs. Measured on a
    # flange: five tool calls where there had been a script.
    check("a pattern is offered well before the escape hatch",
          names.index("pattern_circular") < names.index("run_python")
          and names.index("pattern_linear") < names.index("run_python"),
          ", ".join(names[names.index("pattern_circular"):][:3]))
    for call, args, wanted in [
        ("pattern_circular", {"name": "Plate", "count": 1}, "at least 2"),
        ("pattern_circular", {"name": "Plate", "count": 4, "axis": "W"},
         "one of X, Y, Z"),
        ("pattern_circular", {"name": "Ghost", "count": 4}, "no object called"),
        ("pattern_linear", {"name": "Plate", "count": 3, "spacing": [1, 2]},
         "[dx, dy, dz]"),
    ]:
        try:
            box.invoke(call, args)
            check(f"{call} refuses {list(args.values())[1]!r}", False,
                  "it accepted it")
        except ToolError as refused:
            check(f"{call} refuses {list(args.values())[1]!r}",
                  wanted in str(refused), str(refused)[:70])

    print("\nWhat the model makes up is refused, by name")
    for call, args, wanted in [
        ("add_shape", {"kind": "Part::Banana"}, "not one of the shapes"),
        ("add_shape", {"kind": "Part::Box", "Length": 1}, "needs Width"),
        ("combine", {"operation": "weld", "base": "Plate", "tools": ["Hole"]},
         "operation is one of"),
        ("move", {"name": "Plate", "position": [1, 2]}, "[x, y, z]"),
        ("resize_hole", {"feature_id": "hole_999", "diameter": 8},
         "no feature called"),
    ]:
        try:
            box.invoke(call, args)
            check(f"{call} refuses {list(args.values())[0]!r}", False,
                  "it accepted it")
        except ToolError as refused:
            check(f"{call} refuses {list(args.values())[0]!r}",
                  wanted in str(refused), str(refused)[:70])

    print("\nA solid with no tree says so, and says what to do instead")
    # The failure this prevents: asked to make a plate thicker, where the
    # plate was a plain solid, an 8B made nineteen set_size calls and got
    # FreeCAD's own words back every time - "'Part.Feature' object has no
    # attribute 'Height'" - which says what went wrong and nothing about
    # what to do. Fifty-nine seconds and the whole step budget.
    stand_in.documents_[session.document].append(
        {"Name": "Imported", "Label": "Imported", "TypeId": "Part::Feature",
         "Properties": {}})
    try:
        box.invoke("set_size", {"name": "Imported", "Height": 15})
        check("a plain solid explains that it has no dimensions", False)
    except ToolError as refused:
        check("a plain solid explains that it has no dimensions",
              "plain solid" in str(refused)
              and "resize_hole" in str(refused), str(refused)[:80])
    try:
        box.invoke("set_size", {"name": "Plate", "Thickness": 15})
        check("and a parametric one names the dimensions it does have", False)
    except ToolError as refused:
        check("and a parametric one names the dimensions it does have",
              "Thickness" in str(refused) and "Height" in str(refused),
              str(refused)[:80])
    try:
        box.invoke("set_size", {"name": "Ghost", "Height": 15})
        check("an object that is not there is refused before FreeCAD sees it",
              False)
    except ToolError as refused:
        check("an object that is not there is refused before FreeCAD sees it",
              "no object called" in str(refused), str(refused)[:60])

    print("\nThe catalogue is reachable from inside a build")
    placed = box.invoke("place_standard_part",
                        {"description": "an M8 flat washer"})
    check("a standard part lands in the document, verified",
          placed.get("part") and "washer" in placed["part"].lower(),
          f"{placed.get('part')} - {placed.get('standard')}")
    try:
        box.invoke("place_standard_part", {"description": "a handlebar"})
        check("an ambiguous one is refused rather than guessed", False)
    except ToolError as refused:
        check("an ambiguous one is refused rather than guessed",
              "more than one" in str(refused), str(refused)[:80])
    try:
        box.invoke("place_standard_part", {"description": "a fairing"})
        check("and something that is not a standard part says so", False)
    except ToolError as refused:
        check("and something that is not a standard part says so",
              "not a standard part" in str(refused), str(refused)[:70])

    server.shutdown()
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
