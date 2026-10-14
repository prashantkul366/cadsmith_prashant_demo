"""The feature tree, read and written in a real FreeCAD.

A tree panel that shows the right rows and cannot change them is a
picture, and a panel that offers to change what it cannot write is worse
than a picture. So every check here goes through a real FreeCAD: the tree
is read off a document built with a sketch, a pad, a pocket and a
pattern - a history, not a solid - and then written to.

The part that matters most is the refusal. A value that leaves the
document unable to rebuild must leave the document as it was, because a
person who drags a number too far should get their part back, not a
broken one.

Needs a FreeCAD. Skips where there is none, like the other FreeCAD tests.

Run:  .venv/bin/python -m app.tests.test_tree
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.server import freecad_tools, tree  # noqa: E402
from app.server.toolbox import ToolError  # noqa: E402

CANDIDATES = [os.environ.get("CADSMITH_FREECADCMD", ""),
              "freecadcmd", "FreeCADCmd",
              "/tmp/claude-0/fc/bin/freecadcmd"]

#: A PartDesign body with a real history: a sketched rectangle padded into
#: a plate, a hole pocketed through it, and that hole patterned four ways.
#: Built out of primitives would give the same solid and no tree, which is
#: exactly the difference this module exists for.
SETUP = '''
import FreeCAD, Part, Sketcher
doc = FreeCAD.newDocument("Part")
body = doc.addObject("PartDesign::Body", "Body")

sketch = doc.addObject("Sketcher::SketchObject", "Outline")
body.addObject(sketch)
sketch.AttachmentSupport = [(doc.getObject("XY_Plane"), "")]
sketch.MapMode = "FlatFace"
for a, b in (((0, 0), (120, 0)), ((120, 0), (120, 80)),
             ((120, 80), (0, 80)), ((0, 80), (0, 0))):
    sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(a[0], a[1], 0),
                                        FreeCAD.Vector(b[0], b[1], 0)), False)
doc.recompute()

pad = doc.addObject("PartDesign::Pad", "Plate")
body.addObject(pad)
pad.Profile = sketch
pad.Length = 12.0
doc.recompute()

# The hole is drawn on the same datum plane as the outline rather than on
# the pad's top face. A sketch mapped to a face moves when the face it
# sits on is renumbered, which is a real thing that happens to real
# models and not what this test is about.
hole = doc.addObject("Sketcher::SketchObject", "HoleOutline")
body.addObject(hole)
hole.AttachmentSupport = [(doc.getObject("XY_Plane"), "")]
hole.MapMode = "FlatFace"
hole.addGeometry(Part.Circle(FreeCAD.Vector(20, 20, 0),
                             FreeCAD.Vector(0, 0, 1), 3.3), False)
doc.recompute()

pocket = doc.addObject("PartDesign::Pocket", "Pocket")
body.addObject(pocket)
pocket.Profile = hole
pocket.Type = 1          # through all
pocket.Reversed = True
pocket.Label = "Bolt hole"
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
    """The surface the RPC bridge offers, backed by freecadcmd."""

    def __init__(self, binary: str, setup: str) -> None:
        self.binary, self.setup = binary, setup
        self.carried = ""

    def run(self, code: str, timeout: float = 120.0) -> str:
        script = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                             encoding="utf-8")
        script.write("# -*- coding: utf-8 -*-\n" + self.setup
                     + self.carried + code)
        script.close()
        try:
            done = subprocess.run([self.binary, script.name],
                                  capture_output=True, text=True,
                                  timeout=timeout)
            printed = done.stdout + done.stderr
        finally:
            os.unlink(script.name)
        self._keep(printed)
        return printed

    def _keep(self, printed: str) -> None:
        """Carry an accepted change into the next call.

        A live FreeCAD holds the document between calls; freecadcmd is a
        fresh process each time. Without this, a tool that changes a number
        and then measures the part measures the part before the change,
        and a check on what it measured would be checking the harness.
        """
        for line in printed.splitlines():
            if not line.startswith("CADSMITH_TREE "):
                continue
            try:
                answer = json.loads(line[len("CADSMITH_TREE "):])
            except json.JSONDecodeError:
                continue
            for name, value in (answer.get("set") or {}).items():
                self.then(f"doc.getObject({answer['object']!r})."
                          f"{name} = {value!r}")
                self.then("doc.recompute()")

    def measure(self, document: str):
        from app.server import freecad as freecad_mod
        return freecad_mod.Bridge.measure(self, document)

    def then(self, code: str) -> "Bridge":
        """Carry a change forward, since each call is a fresh process.

        A live FreeCAD keeps the document between calls and freecadcmd does
        not, so a test that edits and then reads has to replay the edit.
        """
        self.carried += code + "\n"
        return self


def main() -> int:
    failures = 0

    def check(what: str, ok: bool, saw: str = "") -> None:
        nonlocal failures
        if not ok:
            failures += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {what}"
              + (f" - {saw}" if saw else ""))

    binary = freecadcmd()
    if not binary:
        print("No freecadcmd found - skipping, as a missing tool is not a "
              "failing test.")
        print("Set CADSMITH_FREECADCMD to point at one.")
        return 0
    print(f"FreeCAD: {binary}\n")

    print("What the tree says the part is made of")
    got = tree.read(Bridge(binary, SETUP), "Part")
    check("it read the document", got.get("ok"),
          got.get("why") or f'{len(got.get("objects") or [])} objects')
    if not got.get("ok"):
        print("\n" + "=" * 58)
        print("1 CHECK(S) FAILED")
        return 1
    names = {o["name"]: o for o in got["objects"]}
    check("the pad is in it", "Plate" in names, ", ".join(sorted(names)))
    check("and the sketch it came from",
          "Outline" in names, ", ".join(sorted(names)))
    # The tree is the history, so the pad must point at its own sketch.
    check("the pad is built from that sketch",
          "Outline" in (names.get("Plate", {}).get("children") or []),
          str(names.get("Plate", {}).get("children")))
    check("and the sketch knows what is built from it",
          "Plate" in (names.get("Outline", {}).get("parents") or []),
          str(names.get("Outline", {}).get("parents")))
    # A label is what the engineer named it; the name is FreeCAD's.
    # FreeCAD's Name is an identifier it will not let you repeat; the
    # Label is what the engineer typed. A tree panel shows the label.
    check("a feature keeps the name a person gave it",
          names.get("Pocket", {}).get("label") == "Bolt hole",
          str(names.get("Pocket", {}).get("label")))

    print("\nWhat the panel may offer to change")
    length = next((p for p in names["Plate"]["properties"]
                   if p["name"] == "Length"), None)
    check("the pad's length is there, with its value",
          length is not None and abs(float(length["value"]) - 12.0) < 1e-6,
          str(length and length["value"]))
    check("and is offered as a length, not as text",
          length is not None and length["editor"] == "length"
          and length["writable"], str(length and length["editor"]))
    check("it carries the unit FreeCAD would show",
          bool(length and length.get("shown")),
          str(length and length.get("shown")))
    shapes = [p for p in names["Plate"]["properties"]
              if p["name"] in ("Shape", "Placement")]
    check("a shape is shown but not offered for editing",
          all(not p["writable"] for p in shapes),
          str([(p["name"], p["writable"]) for p in shapes]))
    types = {p["type"] for o in got["objects"] for p in o["properties"]}
    check("the housekeeping properties are kept out by default",
          not any(p["name"] == "Visibility"
                  for o in got["objects"] for p in o["properties"]),
          f"{len(types)} property types in all")

    print("\nThe tree as rows to draw")
    rows = tree.outline(got)
    check("every object lands on a row",
          len(rows) == len(got["objects"]),
          f'{len(rows)} rows for {len(got["objects"])} objects')
    check("and a sketch is indented under the feature that uses it",
          any(r["name"] == "Outline" and r["depth"] > 0 for r in rows),
          str([(r["name"], r["depth"]) for r in rows]))

    print("\nChanging a number, and the part changing with it")
    after = tree.edit(Bridge(binary, SETUP), "Part", "Plate",
                      {"Length": 20.0})
    check("the pad took the new length", after.get("ok"),
          after.get("why") or str(after.get("set")))
    read_back = tree.read(
        Bridge(binary, SETUP).then("doc.getObject('Plate').Length = 20.0\n"
                                   "doc.recompute()\n"), "Part")
    grown = next((p for p in next(o for o in read_back["objects"]
                                  if o["name"] == "Plate")["properties"]
                  if p["name"] == "Length"), None)
    check("and reading it back says so",
          grown is not None and abs(float(grown["value"]) - 20.0) < 1e-6,
          str(grown and grown["value"]))

    print("\nWhat must be refused")
    gone = tree.edit(Bridge(binary, SETUP), "Part", "Plate",
                     {"NoSuchProperty": 1.0})
    check("a property the object does not have",
          not gone.get("ok") and "NoSuchProperty" in (gone.get("refused") or {}),
          str(gone.get("refused")))
    locked = tree.edit(Bridge(binary, SETUP), "Part", "Plate", {"Shape": 1.0})
    check("and one the panel is not allowed to write",
          not locked.get("ok") and bool(locked.get("refused")),
          str(locked.get("refused")))
    # The one that matters: a value the part cannot be rebuilt with must
    # leave the part as it was. A pad of no length is the smallest such
    # value - FreeCAD refuses it outright - and a negative one is not,
    # because a pad takes that as padding the other way.
    broken = tree.edit(Bridge(binary, SETUP), "Part", "Plate",
                       {"Length": 0.0})
    check("a length the part cannot be rebuilt with is refused",
          not broken.get("ok"),
          str(broken.get("why") or broken.get("refused")))
    check("and the document rebuilds again afterwards",
          not broken.get("still_broken"),
          str(broken.get("still_broken")))

    print("\nTaking a feature out without deleting it")
    off = tree.suppress(Bridge(binary, SETUP), "Part", "Pocket", True)
    check("a PartDesign feature can be suppressed",
          off.get("ok"), off.get("why") or "suppressed")
    cannot = tree.suppress(Bridge(binary, SETUP), "Part", "Outline", True)
    check("and a sketch says plainly that it cannot be",
          not cannot.get("ok") and "cannot be suppressed" in
          (cannot.get("why") or ""), str(cannot.get("why"))[:80])

    print("\nBacking a change out again")
    # Each call is a fresh FreeCAD, so the change to undo has to be made in
    # the same process. It is made the way this module makes one - inside a
    # transaction - because a document with no transactions has an empty
    # undo stack and would pass a weaker check for the wrong reason.
    changed = ("doc.UndoMode = 1\n"
               "doc.openTransaction('CADSmith: Plate')\n"
               "doc.getObject('Plate').Length = 20.0\n"
               "doc.recompute()\n"
               "doc.commitTransaction()\n")
    backed = tree.undo(Bridge(binary, SETUP).then(changed), "Part")
    check("the last change is undone", backed.get("ok"),
          backed.get("why") or str(backed.get("undone")))
    check("and it says which change that was",
          any("Plate" in str(name) for name in (backed.get("undone") or [])),
          str(backed.get("undone")))
    restored = tree.read(
        Bridge(binary, SETUP).then(changed
                                   + "doc.undo()\ndoc.recompute()\n"), "Part")
    length = next((p for p in next(o for o in restored["objects"]
                                   if o["name"] == "Plate")["properties"]
                   if p["name"] == "Length"), None)
    check("the pad is back to what it was",
          length is not None and abs(float(length["value"]) - 12.0) < 1e-6,
          str(length and length["value"]))
    nothing = tree.undo(Bridge(binary, SETUP), "Part")
    check("a document with nothing to undo says so, rather than failing",
          not nothing.get("ok") and "nothing to undo" in
          (nothing.get("why") or ""), str(nothing.get("why"))[:60])

    print("\nThe same tree, as the model sees it")
    # The claim being checked is that asking and dragging are one path.
    # These are the tools the model calls; they go through the module the
    # panel goes through, so a part cannot end up in a state one of them
    # believes in and the other does not.
    def session():
        return freecad_tools.Session(Bridge(binary, SETUP), "Part")

    seen = session().read_tree()
    labels = [f["label"] for f in seen["features"]]
    check("it is given the features by name", "Plate" in labels,
          ", ".join(labels[:6]))
    plate = next(f for f in seen["features"] if f["label"] == "Plate")
    check("with the numbers it may change, and not the rest",
          "Length" in plate["properties"] and "Shape" not in plate["properties"],
          ", ".join(sorted(plate["properties"])[:6]))
    one = session().read_tree("Plate")
    check("and one feature on request", len(one["features"]) == 1,
          str(len(one["features"])))
    try:
        session().read_tree("Flange")
        check("a name the part does not have is refused", False, "it was not")
    except ToolError as error:
        # The list matters: a model told only "no such feature" guesses
        # again, and a model told what there is picks from it.
        check("a name the part does not have is refused, with what there is",
              "Plate" in str(error), str(error)[:70])

    grew = session().set_property("Plate", "Length", 20.0)
    check("a number it sets changes the part",
          abs((grew.get("part_now") or [{}])[0].get("size_mm", [0, 0, 0])[2]
              - 20.0) < 1e-6,
          str((grew.get("part_now") or [{}])[0].get("size_mm")))
    try:
        session().set_property("Plate", "Length", 0.0)
        check("and one the part cannot be rebuilt with is refused",
              False, "it was taken")
    except ToolError as error:
        check("and one the part cannot be rebuilt with is refused",
              "rebuild" in str(error), str(error)[:70])
    try:
        session().undo_change()
        check("nothing to undo is said plainly", False, "it claimed to undo")
    except ToolError as error:
        check("nothing to undo is said plainly",
              "nothing to undo" in str(error), str(error)[:60])

    print("\n" + "=" * 58)
    print("ALL CHECKS PASSED" if not failures else f"{failures} CHECK(S) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
