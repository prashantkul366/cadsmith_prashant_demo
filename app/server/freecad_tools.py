"""The tools a model may use to build a part in FreeCAD.

Three layers, and the ordering is the design.

**The catalogue, at the top.** ``place_standard_part`` reaches the same
router that answers "a drag bar" with no model call at all - except here the
part lands *inside* a FreeCAD document, so an agent can build around
something already verified. That is the one capability neither system has
alone: today "a drag bar" short-circuits the agents entirely and "a mounting
bracket for a drag bar" cannot be helped at all.

**Features in the middle.** ``find_features`` and ``resize_hole`` reach
``direct.py``, which names things the way a drawing does - "4x Ø8.5 through
hole, rectangular pattern 90 x 50" - rather than the way FreeCAD does. A
model that can say "the mounting holes" does not have to guess an object
name, and a selector resolved against the current solid cannot go stale.

**FreeCAD primitives at the bottom**, as the escape hatch. Reached when the
layers above do not cover it, which for a genuinely new shape is often.

Every tool answers with what it measured. Not ``{"ok": true}`` but the
bounding box, the volume, the hole that actually got made. That is what lets
a model correct itself at step two instead of failing at step eight, and it
costs nothing because FreeCAD knows the numbers anyway.

``run_python`` is the widest door and is offered deliberately: FreeCAD's API
is far larger than any vocabulary worth writing out, and a sketch-driven pad
or a loft has no primitive to call. It is last in the list because a model
reaches for the first thing that fits, and the narrow tools are the ones
whose results can be trusted without reading the code.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from app.server import freecad
from app.server.toolbox import Tool, ToolError, Toolbox

#: FreeCAD types worth naming. Not a limit - ``run_python`` reaches the rest -
#: but the ones a part is usually made of, with the properties each needs.
PRIMITIVES = {
    "Part::Box": ("Length", "Width", "Height"),
    "Part::Cylinder": ("Radius", "Height"),
    "Part::Sphere": ("Radius",),
    "Part::Cone": ("Radius1", "Radius2", "Height"),
    "Part::Torus": ("Radius1", "Radius2"),
    "Part::Tube": ("InnerRadius", "OuterRadius", "Height"),
}

#: Booleans, by the name a person uses rather than the FreeCAD class.
BOOLEANS = {"cut": "Part::Cut", "union": "Part::MultiFuse",
            "intersect": "Part::MultiCommon"}


def properties_of(described: dict) -> dict:
    """The properties in an object as the addon describes it."""
    return described.get("Properties") or {}


class Session:
    """One document in FreeCAD, and the tools that work on it.

    Holds the document name so the model never has to carry it, which is one
    fewer argument to get wrong and one fewer way to edit the wrong part.
    """

    def __init__(self, bridge: freecad.Bridge, document: str = "") -> None:
        self.bridge = bridge
        self.document = document or bridge.new_document("CADSmith")
        #: Names FreeCAD actually assigned, in the order they were made, so
        #: a report can say what was built without asking FreeCAD again.
        self.built: list[str] = []
        #: The handful of numbers that become sliders. Declared while
        #: building rather than summarised afterwards: a model that has just
        #: made the base plate knows that its Length is the one a person
        #: would want to drag, and asking it again at the end invites a
        #: tidy-sounding answer that does not match what it built.
        self.declared: list[dict] = []
        #: What the part is made of, once something has said. Nothing by
        #: default: a part reported as aluminium because nobody said
        #: otherwise is a number presented as a fact.
        self.material: Optional[dict] = None

    # -- what every tool returns --------------------------------------------

    def _measured(self, **extra: Any) -> dict:
        """The state of the part after a change, as numbers.

        Returned by every tool that alters the document. A model that is
        told the box it just asked for is 60 x 40 x 12 can check that
        against what it meant; a model told "ok" cannot.
        """
        try:
            solids = self.bridge.measure(self.document).get("solids", [])
        except freecad.FreeCADError as error:
            return {**extra, "warning": f"could not measure: {error}"}
        finished = [
            {"name": s["name"], "label": s["label"],
             "size_mm": [round(v, 3) for v in s["bbox"]],
             "volume_mm3": round(s["volume"], 1),
             "faces": s["faces"],
             "watertight": s["valid"]}
            for s in solids]
        return {**extra, "part_now": finished}

    # -- the bottom layer: FreeCAD's own primitives -------------------------

    def add_shape(self, kind: str, name: str = "",
                  position: Optional[list] = None, **sizes: Any) -> dict:
        if kind not in PRIMITIVES:
            raise ToolError(
                f"{kind!r} is not one of the shapes offered here. There is: "
                + ", ".join(PRIMITIVES)
                + ". For anything else use run_python.")
        needed = [p for p in PRIMITIVES[kind] if p not in sizes]
        if needed:
            raise ToolError(f"{kind} needs {', '.join(needed)}")

        made = self.bridge.add(self.document, kind, name or kind.split("::")[-1],
                               **sizes)
        self.built.append(made)
        if position:
            self.move(made, position)
        # FreeCAD may have renamed it; the model is told, because every
        # later call keys on the name that exists rather than the one asked
        # for.
        return self._measured(added=made,
                              renamed=(made != name if name else False))

    def move(self, name: str, position: list) -> dict:
        """Put an object somewhere. Placement is not a plain property, so it
        goes through the one door that takes arbitrary Python."""
        if len(position) != 3:
            raise ToolError("position is [x, y, z] in millimetres")
        x, y, z = (float(v) for v in position)
        self.bridge.run(f"""
import FreeCAD
doc = FreeCAD.getDocument({self.document!r})
obj = doc.getObject({name!r})
if obj is None:
    raise RuntimeError("no object called {name}")
obj.Placement = FreeCAD.Placement(
    FreeCAD.Vector({x}, {y}, {z}), obj.Placement.Rotation)
doc.recompute()
""")
        return self._measured(moved=name, to=[x, y, z])

    def rotate(self, name: str, axis: list, degrees: float) -> dict:
        if len(axis) != 3:
            raise ToolError("axis is [x, y, z]")
        ax, ay, az = (float(v) for v in axis)
        self.bridge.run(f"""
import FreeCAD
doc = FreeCAD.getDocument({self.document!r})
obj = doc.getObject({name!r})
if obj is None:
    raise RuntimeError("no object called {name}")
obj.Placement = FreeCAD.Placement(
    obj.Placement.Base,
    FreeCAD.Rotation(FreeCAD.Vector({ax}, {ay}, {az}), {float(degrees)}))
doc.recompute()
""")
        return self._measured(rotated=name, degrees=float(degrees))

    def set_size(self, name: str, **sizes: Any) -> dict:
        """Change a property and let the tree recompute.

        The reason for going through FreeCAD at all. One changed number
        re-runs everything built on it, which a STEP file can never do.

        Checked here before it reaches FreeCAD, because FreeCAD's own answer
        is not one a model can act on. Measured on an 8B asked to make a
        plate thicker, where the plate was a plain solid with no tree:
        nineteen calls, every one refused with "'Part.Feature' object has no
        attribute 'Height'", which says what went wrong and nothing about
        what to do instead. The run spent fifty-nine seconds on it.
        """
        if not sizes:
            raise ToolError("say which property to change, e.g. Length=75")
        found = self.bridge.object(self.document, name)
        if found is None:
            raise ToolError(f"there is no object called {name!r}. "
                            "Call list_objects to see what there is.")
        properties = found.get("Properties") or {}
        missing = [p for p in sizes if p not in properties]
        if missing:
            raise ToolError(self._cannot_resize(name, found, missing))
        self.bridge.edit(self.document, name, **sizes)
        return self._measured(edited=name, set=sizes)

    @staticmethod
    def _cannot_resize(name: str, found: dict, missing: list) -> str:
        """Why that property cannot be set, and what to do instead."""
        kind = found.get("TypeId") or found.get("Type") or "?"
        # The case worth naming. A solid handed to the document whole - by a
        # feature edit, an import, or a script that built it outside the
        # tree - is a Part::Feature, and it has no dimensions to set because
        # there is no tree behind it to recompute. Saying "no attribute
        # Height" leaves a model guessing at spellings; saying what the
        # object *is* sends it to the tools that work on geometry.
        if kind == "Part::Feature":
            return (f"{name} is a plain solid ({kind}) - it has no parametric "
                    f"dimensions to set, because nothing built it that could "
                    f"be re-run. Change it with the tools that work on "
                    f"geometry rather than on a tree: find_features, then "
                    f"resize_hole, remove_feature or add_fillet. To change an "
                    f"overall size you have to rebuild the shape.")
        sizeable = sorted(p for p in properties_of(found)
                          if p in {"Length", "Width", "Height", "Radius",
                                   "Radius1", "Radius2", "InnerRadius",
                                   "OuterRadius", "Angle"})
        return (f"{name} ({kind}) has no property called "
                f"{', '.join(repr(m) for m in missing)}. "
                + (f"It can be given: {', '.join(sizeable)}."
                   if sizeable else "It has no dimensions that can be set."))

    def combine(self, operation: str, base: str, tools: list) -> dict:
        """Cut, fuse or intersect. One call, because a boolean left half
        done is a document the next step cannot read."""
        kind = BOOLEANS.get(operation.lower())
        if kind is None:
            raise ToolError(f"operation is one of: {', '.join(BOOLEANS)}")
        if not tools:
            raise ToolError("name at least one object to combine with")

        names = json.dumps(list(tools))
        if operation.lower() == "cut":
            script = f"""
import FreeCAD
doc = FreeCAD.getDocument({self.document!r})
tools = [doc.getObject(n) for n in {names}]
missing = [n for n, o in zip({names}, tools) if o is None]
if missing:
    raise RuntimeError("no object called " + ", ".join(missing))
tool = tools[0]
if len(tools) > 1:
    tool = doc.addObject("Part::MultiFuse", "CutTools")
    tool.Shapes = tools
    doc.recompute()
result = doc.addObject("Part::Cut", "Result")
result.Base = doc.getObject({base!r})
result.Tool = tool
doc.recompute()
print(result.Name)
"""
        else:
            script = f"""
import FreeCAD
doc = FreeCAD.getDocument({self.document!r})
parts = [doc.getObject(n) for n in [{base!r}] + {names}]
missing = [n for n, o in zip([{base!r}] + {names}, parts) if o is None]
if missing:
    raise RuntimeError("no object called " + ", ".join(missing))
result = doc.addObject({kind!r}, "Result")
result.Shapes = parts
doc.recompute()
print(result.Name)
"""
        made = self.bridge.run(script).strip().splitlines()
        name = made[-1].strip() if made else "Result"
        self.built.append(name)
        return self._measured(combined=operation, result=name)

    def remove(self, name: str) -> dict:
        self.bridge.remove(self.document, name)
        return self._measured(deleted=name)

    def list_objects(self) -> dict:
        """What is in the document, with the names later calls must use."""
        return {"objects": [
            {"name": o.get("Name"), "type": o.get("TypeId") or o.get("Type"),
             "label": o.get("Label")}
            for o in self.bridge.objects(self.document)]}

    def declare_parameter(self, name: str, label: str, object_name: str,
                          property_name: str, scale: float = 1.0) -> dict:
        """Name a number a person should be able to drag.

        FreeCAD stores a cylinder's Radius; a person drags a diameter. The
        scale carries that, so the panel can say "Hole diameter 6" over a
        property holding 3 and the two never drift apart.
        """
        found = self.bridge.object(self.document, object_name)
        if found is None:
            raise ToolError(f"there is no object called {object_name!r}")
        if property_name not in (found.get("Properties") or found):
            # The stand-in and FreeCAD describe an object slightly
            # differently; either way a property that is not there is worth
            # catching now rather than when somebody drags it.
            properties = found.get("Properties") or {}
            if properties and property_name not in properties:
                raise ToolError(
                    f"{object_name} has no property called {property_name!r}. "
                    f"It has: {', '.join(sorted(properties)) or 'none'}")
        if scale == 0:
            raise ToolError("scale cannot be zero")

        self.declared = [d for d in self.declared if d["name"] != name]
        self.declared.append({"name": name, "label": label,
                              "object": object_name,
                              "property": property_name,
                              "scale": float(scale)})
        return {"declared": name, "reads": f"{object_name}.{property_name}",
                "parameters_so_far": [d["name"] for d in self.declared]}

    #: Which way a circular pattern turns, by the name a person uses.
    AXES = {"X": (1, 0, 0), "Y": (0, 1, 0), "Z": (0, 0, 1)}

    def pattern_circular(self, name: str, count: int,
                         centre: Optional[list] = None, axis: str = "Z",
                         angle: float = 360.0) -> dict:
        """Repeat an object evenly around a circle - a bolt circle.

        The one thing a part like a flange needs and no primitive provides.
        Without it a model computes six placements in a script, which is
        about 1,200 output tokens against the 40 a tool call costs, and the
        script is where the arithmetic goes wrong unseen.
        """
        if count < 2:
            raise ToolError("count is how many there are in all, so at least 2")
        if axis.upper() not in self.AXES:
            raise ToolError("axis is one of X, Y, Z")
        if self.bridge.object(self.document, name) is None:
            raise ToolError(f"there is no object called {name!r}")
        centre = [float(v) for v in (centre or [0, 0, 0])]
        if len(centre) != 3:
            raise ToolError("centre is [x, y, z] in millimetres")

        made = self._copies(f"""
import FreeCAD, json
doc = FreeCAD.getDocument({self.document!r})
src = doc.getObject({name!r})
centre = FreeCAD.Vector({centre[0]}, {centre[1]}, {centre[2]})
spindle = FreeCAD.Vector{self.AXES[axis.upper()]}
made = []
for i in range(1, {int(count)}):
    turn = FreeCAD.Rotation(spindle, {float(angle)} * i / {int(count)})
    copy = doc.copyObject(src, False)
    copy.Placement = FreeCAD.Placement(
        centre + turn.multVec(src.Placement.Base - centre),
        turn.multiply(src.Placement.Rotation))
    made.append(copy.Name)
doc.recompute()
{freecad.marked("json.dumps(made)")}
""")
        return self._measured(patterned=name, copies=made,
                              all_of_them=[name] + made)

    def pattern_linear(self, name: str, count: int, spacing: list) -> dict:
        """Repeat an object along a line - a row of holes."""
        if count < 2:
            raise ToolError("count is how many there are in all, so at least 2")
        if len(spacing) != 3:
            raise ToolError("spacing is [dx, dy, dz] in millimetres, "
                            "the step from one to the next")
        if self.bridge.object(self.document, name) is None:
            raise ToolError(f"there is no object called {name!r}")
        step = [float(v) for v in spacing]

        made = self._copies(f"""
import FreeCAD, json
doc = FreeCAD.getDocument({self.document!r})
src = doc.getObject({name!r})
step = FreeCAD.Vector({step[0]}, {step[1]}, {step[2]})
made = []
for i in range(1, {int(count)}):
    copy = doc.copyObject(src, False)
    copy.Placement = FreeCAD.Placement(
        src.Placement.Base + step * i, src.Placement.Rotation)
    made.append(copy.Name)
doc.recompute()
{freecad.marked("json.dumps(made)")}
""")
        return self._measured(patterned=name, copies=made,
                              all_of_them=[name] + made)

    def _copies(self, code: str) -> list:
        """Run a pattern script and return the names FreeCAD gave the copies."""
        made = json.loads(self.bridge.value(code))
        self.built.extend(made)
        return made

    def set_material(self, name: str) -> dict:
        """Say what the part is made of, and what that makes it weigh.

        Read out of FreeCAD's own material library - 145 cards with density,
        yield and tensile strength - rather than a table written here, which
        would be a guess at numbers somebody else maintains properly.
        """
        from app.server import materials

        card = materials.find(name, self.bridge)
        if card is None:
            known = ", ".join(c["name"] for c in
                              materials.library(self.bridge)[:8])
            raise ToolError(
                f"{name!r} is not a material this FreeCAD knows. It has "
                f"{len(materials.library(self.bridge))} of them, among them: "
                f"{known}. Name an alloy or a family - '6061', 'mild steel', "
                f"'ABS'.")
        self.material = card
        measured = self._measured(material=card["name"])
        for solid in measured.get("part_now") or []:
            weighed = materials.weigh(solid.get("volume_mm3"), card)
            if weighed:
                solid["mass_g"] = weighed["mass_g"]
        return measured

    def run_python(self, code: str) -> dict:
        """Anything FreeCAD can do that the tools above cannot.

        Offered on purpose: FreeCAD's API is far wider than a vocabulary
        worth writing out, and a sketch-driven pad or a loft has no
        primitive to call. The result is still measured, so code that runs
        and builds the wrong thing is caught the same way as everything else.
        """
        printed = self.bridge.run(code)
        return self._measured(printed=printed.strip()[:1000] or None)

    # -- the top layer: parts this app already knows are right ---------------

    def place_standard_part(self, description: str,
                            position: Optional[list] = None) -> dict:
        """Put a catalogue part into the document, exactly.

        The router that answers this is the same one that serves "a drag
        bar" with no model call at all. Reaching it from inside a build is
        the thing neither half does alone: a verified part becomes a
        component of a new design rather than the whole answer.

        The geometry is built here by this app's own kernel and handed to
        FreeCAD as a solid, because the catalogue speaks CadQuery and
        re-deriving every part in FreeCAD's vocabulary would be a second
        implementation to keep honest.
        """
        from app.catalog import router

        routed = router.select(description)
        if routed is None:
            offered = router.options(description)
            if offered:
                raise ToolError(
                    f"{description!r} names more than one standard part: "
                    + "; ".join(r.part.title for r in offered)
                    + ". Ask for one of them by name.")
            raise ToolError(
                f"{description!r} is not a standard part this app knows. "
                f"Build it from shapes instead.")

        import tempfile
        from pathlib import Path
        import cadquery as cq
        from app.catalog import verify

        solid, _ = verify.build(routed.part.code)
        step = Path(tempfile.mkdtemp(prefix="cadsmith_part_")) / "part.step"
        cq.exporters.export(cq.Workplane(obj=solid), str(step))

        # Imported through FreeCAD's own reader rather than rebuilt, so what
        # lands is the solid this app verified and not an approximation of
        # it.
        name = self.bridge.run(f"""
import FreeCAD, Part
doc = FreeCAD.getDocument({self.document!r})
shape = Part.Shape()
shape.read({str(step)!r})
obj = doc.addObject("Part::Feature", "StandardPart")
obj.Shape = shape
obj.Label = {routed.part.title[:60]!r}
doc.recompute()
print(obj.Name)
""").strip().splitlines()
        made = name[-1].strip() if name else "StandardPart"
        self.built.append(made)
        if position:
            self.move(made, position)
        return self._measured(placed=made, part=routed.part.title,
                              standard=routed.part.standard,
                              verified=routed.report.summary())

    # -- the middle layer: features, named the way a drawing names them ------

    def find_features(self) -> dict:
        """What the finished solid is made of, read off its own topology.

        Names things the way a drawing does - "4x Ø8.5 through hole,
        rectangular pattern 90 x 50" - so the next call can say "the
        mounting holes" without guessing a FreeCAD object name. Resolved
        afresh every time, so a selector cannot go stale after an edit.
        """
        from app.server import direct

        step = self._export_shape()
        found = direct.recognise(step)
        return {"features": [f.summary() for f in found],
                "how_to_use": "pass an id to resize_hole or remove_feature"}

    def resize_hole(self, feature_id: str, diameter: float) -> dict:
        return self._edit_feature({"op": "resize_hole", "select": feature_id,
                                   "diameter": float(diameter)})

    def remove_feature(self, feature_id: str) -> dict:
        return self._edit_feature({"op": "remove", "select": feature_id})

    def add_fillet(self, radius: float, where: str = "all") -> dict:
        return self._edit_feature({"op": "add_fillet", "radius": float(radius),
                                   "where": where})

    def _export_shape(self):
        """The finished solid, here, as a file direct.py can read."""
        import tempfile
        from pathlib import Path
        step = Path(tempfile.mkdtemp(prefix="cadsmith_feat_")) / "part.step"
        step.write_bytes(self.bridge.fetch(self.document, "step"))
        return __import__("cadquery").importers.importStep(str(step)).val().wrapped

    def _edit_feature(self, recipe: dict) -> dict:
        """Edit a recognised feature, then put the result back in FreeCAD.

        The edit happens here, in this app's kernel, because that is where
        the feature recognition lives. What goes back is a plain solid: a
        direct edit has no tree to preserve, which is the same trade NX
        makes when synchronous technology touches an imported body.
        """
        from app.server import direct

        shape = self._export_shape()
        try:
            edited = direct.apply(shape, recipe)
        except KeyError as unknown:
            raise ToolError(str(unknown)) from None
        changed = direct.changed(shape, edited)

        import tempfile
        from pathlib import Path
        import cadquery as cq
        out = Path(tempfile.mkdtemp(prefix="cadsmith_edit_")) / "edited.step"
        cq.exporters.export(cq.Workplane(obj=cq.Shape.cast(edited)), str(out))

        self.bridge.run(f"""
import FreeCAD, Part
doc = FreeCAD.getDocument({self.document!r})
for obj in list(doc.Objects):
    doc.removeObject(obj.Name)
shape = Part.Shape()
shape.read({str(out)!r})
obj = doc.addObject("Part::Feature", "Edited")
obj.Shape = shape
doc.recompute()
print(obj.Name)
""")
        self.built = ["Edited"]
        return self._measured(edit=recipe.get("op"),
                              volume_before=changed["volume"][0],
                              volume_after=changed["volume"][1],
                              features_now=changed["after"])


def toolbox_for(session: Session, allow_python: bool = True) -> Toolbox:
    """The tools, in the order a model should reach for them."""
    number = {"type": "number"}
    text = {"type": "string"}
    point = {"type": "array", "items": {"type": "number"},
             "description": "[x, y, z] in millimetres"}

    tools = [
        Tool(name="place_standard_part",
             description=(
                 "Put a part this app already knows is correct into the "
                 "document - a bearing, a washer, a spur gear, a named "
                 "handlebar bend. Try this before building a standard part "
                 "out of shapes. Give it the part in words, e.g. 'an M8x30 "
                 "socket head cap screw' or 'a drag bar'."),
             parameters={"type": "object", "properties": {
                 "description": text, "position": point},
                 "required": ["description"]},
             run=session.place_standard_part),
        Tool(name="add_shape",
             description=(
                 "Add a primitive solid. kind is one of: "
                 + ", ".join(PRIMITIVES)
                 + ". Give its sizes as named arguments, e.g. kind='Part::Box' "
                   "with Length, Width and Height."),
             parameters={"type": "object", "properties": {
                 "kind": {**text, "enum": sorted(PRIMITIVES)},
                 "name": text, "position": point,
                 "Length": number, "Width": number, "Height": number,
                 "Radius": number, "Radius1": number, "Radius2": number,
                 "InnerRadius": number, "OuterRadius": number},
                 "required": ["kind"]},
             run=session.add_shape),
        Tool(name="set_size",
             description=("Change a property of an object already in the "
                          "document and let FreeCAD recompute everything "
                          "built on it."),
             parameters={"type": "object", "properties": {
                 "name": text,
                 "Length": number, "Width": number, "Height": number,
                 "Radius": number, "Radius1": number, "Radius2": number,
                 "InnerRadius": number, "OuterRadius": number},
                 "required": ["name"]},
             run=session.set_size),
        Tool(name="move",
             description="Place an object at [x, y, z] in millimetres.",
             parameters={"type": "object", "properties": {
                 "name": text, "position": point},
                 "required": ["name", "position"]},
             run=session.move),
        Tool(name="rotate",
             description="Turn an object about an axis, in degrees.",
             parameters={"type": "object", "properties": {
                 "name": text, "axis": point, "degrees": number},
                 "required": ["name", "axis", "degrees"]},
             run=session.rotate),
        Tool(name="combine",
             description=("Cut, union or intersect. Use 'cut' to make holes "
                          "and pockets: base is the part, tools are the "
                          "shapes to remove."),
             parameters={"type": "object", "properties": {
                 "operation": {**text, "enum": sorted(BOOLEANS)},
                 "base": text,
                 "tools": {"type": "array", "items": text}},
                 "required": ["operation", "base", "tools"]},
             run=session.combine),
        Tool(name="pattern_circular",
             description=(
                 "Repeat a shape evenly around a circle - a bolt circle, a "
                 "ring of holes, spokes. Place one where the first should "
                 "go, then pattern it. count is how many there are in all, "
                 "including the one you placed. Use this rather than working "
                 "out the positions yourself."),
             parameters={"type": "object", "properties": {
                 "name": text, "count": {"type": "integer"},
                 "centre": point,
                 "axis": {**text, "enum": ["X", "Y", "Z"]},
                 "angle": {**number,
                           "description": "degrees to spread over; 360 for "
                                          "a full circle"}},
                 "required": ["name", "count"]},
             run=session.pattern_circular),
        Tool(name="pattern_linear",
             description=(
                 "Repeat a shape along a line - a row of holes. count is "
                 "how many there are in all; spacing is the step from one "
                 "to the next. Pattern twice for a grid."),
             parameters={"type": "object", "properties": {
                 "name": text, "count": {"type": "integer"},
                 "spacing": point},
                 "required": ["name", "count", "spacing"]},
             run=session.pattern_linear),
        Tool(name="list_objects",
             description="What is in the document, with the names to use.",
             parameters={"type": "object", "properties": {}},
             run=session.list_objects),
        Tool(name="find_features",
             description=("Read the finished solid and report its holes, "
                          "bores and fillets the way a drawing names them. "
                          "Use before resize_hole or remove_feature."),
             parameters={"type": "object", "properties": {}},
             run=session.find_features),
        Tool(name="resize_hole",
             description=("Open a recognised hole pattern out or close it "
                          "down. feature_id comes from find_features."),
             parameters={"type": "object", "properties": {
                 "feature_id": text, "diameter": number},
                 "required": ["feature_id", "diameter"]},
             run=session.resize_hole),
        Tool(name="remove_feature",
             description=("Delete a recognised feature and heal the solid - "
                          "filling a hole, flattening a fillet."),
             parameters={"type": "object", "properties": {
                 "feature_id": text}, "required": ["feature_id"]},
             run=session.remove_feature),
        Tool(name="add_fillet",
             description=("Break edges with a radius. where is 'all', 'top' "
                          "or 'bottom'."),
             parameters={"type": "object", "properties": {
                 "radius": number,
                 "where": {**text, "enum": ["all", "top", "bottom"]}},
                 "required": ["radius"]},
             run=session.add_fillet),
        Tool(name="set_material",
             description=(
                 "Say what the part is made of, when the request names a "
                 "material. Gives its weight, and the yield strength a "
                 "later check can hold it to. Takes an alloy or a family: "
                 "'6061', 'Aluminum-7075-T6', 'mild steel', 'titanium', "
                 "'ABS'."),
             parameters={"type": "object", "properties": {"name": text},
                         "required": ["name"]},
             run=session.set_material),
        Tool(name="declare_parameter",
             description=(
                 "Name a number a person should be able to adjust with a "
                 "slider afterwards, and say which object property it reads. "
                 "Declare the handful that matter - the overall sizes, a "
                 "hole diameter, a wall thickness - not every property. Use "
                 "scale=2 where you want a diameter over a Radius property."),
             parameters={"type": "object", "properties": {
                 "name": {**text, "description": "short, lower_case_with_underscores"},
                 "label": {**text, "description": "what a person reads"},
                 "object_name": text, "property_name": text, "scale": number},
                 "required": ["name", "label", "object_name", "property_name"]},
             run=session.declare_parameter),
        Tool(name="remove_object",
             description="Delete an object from the document by name.",
             parameters={"type": "object", "properties": {"name": text},
                         "required": ["name"]},
             run=session.remove),
    ]
    if allow_python:
        tools.append(Tool(
            name="run_python",
            description=(
                "Run Python inside FreeCAD. Use only when the tools above "
                "cannot do it - a sketch, a loft, a sweep, a helix. "
                "FreeCAD and the document are available; get the document "
                "with FreeCAD.getDocument(). Call doc.recompute() when done."),
            parameters={"type": "object", "properties": {"code": text},
                        "required": ["code"]},
            run=session.run_python))
    return Toolbox(tools)
