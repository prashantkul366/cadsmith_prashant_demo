"""Edit a solid that arrived without a feature tree.

A STEP file from NX or SolidWorks is a *dead* solid: faces, edges and the
surfaces under them, and nothing else. No history, no parameters, no names.
Neither STEP AP203, AP214 nor AP242 carries construction history, and
neither does Parasolid XT - the tree stays inside the CAD that made it.

So the tree is not imported. It is *recovered*, which is what NX calls
Synchronous Technology and SolidWorks calls Direct Editing: read the
topology, work out which faces form a feature, and edit that.

Three things make this tractable here.

**Features are recognised, not remembered.** A full-sweep cylinder with
material outside it is a hole. A partial sweep is a fillet along an edge. A
torus is a fillet round a corner, or a bend in a tube. None of that needs
the code that built the part.

**Selectors are re-derived, never stored.** The oldest sore in this field
is topological naming: face 7 is not face 7 after the first edit. This
module never holds a face id between edits. A selector is a *description* -
"the 4x Ø8.5 pattern" - and it is resolved against the current solid every
time. There is nothing to go stale.

**The model names the edit; the kernel performs it.** A language model
asked to write the geometry for a part like this produces a plausible
script and a wrong solid. Asked which feature to change and what to, it
answers in forty tokens. The recipe is the whole of its output, and every
edit is measured afterwards against what was asked.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Defeaturing
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.Bnd import Bnd_Box
from OCP.GeomAbs import GeomAbs_SurfaceType
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Vec
from OCP.TopAbs import TopAbs_ShapeEnum, TopAbs_State
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Shape
from OCP.TopTools import (TopTools_IndexedDataMapOfShapeListOfShape,
                          TopTools_ListOfShape)

#: A cylindrical face this far round is a bore rather than a fillet. A
#: through hole sweeps the full turn; a fillet along an edge sweeps the
#: angle between the two faces it blends, which is far less.
FULL_SWEEP = math.radians(350.0)

#: Two features count as the same size within this. Tighter and a Ø8.5 hole
#: imported at 4.2499 reads as its own group of one.
SIZE_TOL = 0.01

#: Two positions count as the same within this, for spotting a pattern.
PLACE_TOL = 0.05


# ---------------------------------------------------------------------------
# What was found
# ---------------------------------------------------------------------------

@dataclass
class Feature:
    """One recognised feature, and the words that select it again.

    ``faces`` is valid only for the solid it was read from. Nothing outside
    this module keeps one: an edit re-reads the solid and resolves the
    selector afresh, which is how a face id that no longer exists stops
    being a problem.
    """
    id: str
    kind: str                       # hole | fillet | face
    size: float                     # diameter for a hole, radius for a fillet
    count: int
    label: str
    places: list[tuple] = field(default_factory=list)
    axis: Optional[tuple] = None    # (origin, direction) for a hole
    faces: list = field(default_factory=list)

    def summary(self) -> dict:
        return {"id": self.id, "kind": self.kind, "size": round(self.size, 3),
                "count": self.count, "label": self.label}


def _faces(shape: TopoDS_Shape) -> list:
    out, explorer = [], TopExp_Explorer(shape, TopAbs_ShapeEnum.TopAbs_FACE)
    while explorer.More():
        out.append(TopoDS.Face_s(explorer.Current()))
        explorer.Next()
    return out


def volume(shape: TopoDS_Shape) -> float:
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    return props.Mass()


def extents(shape: TopoDS_Shape) -> tuple[float, float, float]:
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return (xmax - xmin, ymax - ymin, zmax - zmin)


def _is_void(shape: TopoDS_Shape, surface, radius: float) -> bool:
    """Is the material outside this cylinder - a hole - or inside it, a boss?

    Steps a short way in from the face towards its own axis and asks the
    solid where that point is. Out means the cylinder wraps a void.
    """
    cylinder = surface.Cylinder()
    axis = cylinder.Axis()
    u = (surface.FirstUParameter() + surface.LastUParameter()) / 2.0
    v = (surface.FirstVParameter() + surface.LastVParameter()) / 2.0
    on = surface.Value(u, v)
    loc, direction = axis.Location(), axis.Direction()
    t = ((on.X() - loc.X()) * direction.X()
         + (on.Y() - loc.Y()) * direction.Y()
         + (on.Z() - loc.Z()) * direction.Z())
    foot = (loc.X() + direction.X() * t,
            loc.Y() + direction.Y() * t,
            loc.Z() + direction.Z() * t)
    step = max(min(radius * 0.1, 0.5), 1e-3) / radius
    probe = gp_Pnt(on.X() + (foot[0] - on.X()) * step,
                   on.Y() + (foot[1] - on.Y()) * step,
                   on.Z() + (foot[2] - on.Z()) * step)
    classifier = BRepClass3d_SolidClassifier(shape)
    classifier.Perform(probe, 1e-7)
    return classifier.State() == TopAbs_State.TopAbs_OUT


def _pattern(places: list[tuple], direction: tuple) -> str:
    """How a set of positions is arranged, said the way a drawing says it."""
    if len(places) < 2:
        return ""
    # Work in the plane the holes are drilled through, so a pattern on a
    # vertical wall reads the same as one on a flat plate.
    axis = gp_Dir(*direction)
    frame = gp_Ax2(gp_Pnt(0, 0, 0), axis)
    ex, ey = gp_Vec(frame.XDirection()), gp_Vec(frame.YDirection())
    flat = [(p[0] * ex.X() + p[1] * ex.Y() + p[2] * ex.Z(),
             p[0] * ey.X() + p[1] * ey.Y() + p[2] * ey.Z()) for p in places]
    xs = sorted({round(a, 2) for a, _ in flat})
    ys = sorted({round(b, 2) for _, b in flat})
    if len(xs) == 2 and len(ys) == 2 and len(places) == 4:
        return f"rectangular pattern {abs(xs[1]-xs[0]):g} x {abs(ys[1]-ys[0]):g}"
    if len(xs) == 1 or len(ys) == 1:
        return f"row of {len(places)}"
    radii = {round(math.hypot(a, b), 2) for a, b in flat}
    if len(radii) == 1:
        return f"{len(places)} on a Ø{2 * radii.pop():g} circle"
    return f"{len(places)} places"


def recognise(shape: TopoDS_Shape) -> list[Feature]:
    """Every feature this solid gives up, from its topology alone.

    Holes are grouped by diameter and axis direction, fillets by radius.
    Two holes of the same size drilled the same way are one feature with a
    count, because that is how a drawing calls them out and how a person
    asks for them to be changed.
    """
    holes: dict[tuple, list] = {}
    rounds: dict[float, list] = {}

    for face in _faces(shape):
        surface = BRepAdaptor_Surface(face)
        kind = surface.GetType()

        if kind == GeomAbs_SurfaceType.GeomAbs_Cylinder:
            cylinder = surface.Cylinder()
            radius = cylinder.Radius()
            if radius <= 0:
                continue
            sweep = surface.LastUParameter() - surface.FirstUParameter()
            if sweep >= FULL_SWEEP and _is_void(shape, surface, radius):
                axis = cylinder.Axis()
                d = axis.Direction()
                # One key for either end of the same axis direction, so
                # holes drilled from opposite sides still group.
                signed = (round(d.X(), 3), round(d.Y(), 3), round(d.Z(), 3))
                if signed < (0.0, 0.0, 0.0):
                    signed = tuple(-v for v in signed)
                key = (round(radius, 3), signed)
                loc = axis.Location()
                holes.setdefault(key, []).append(
                    ((round(loc.X(), 3), round(loc.Y(), 3), round(loc.Z(), 3)),
                     signed, face))
            elif sweep < FULL_SWEEP:
                rounds.setdefault(round(radius, 3), []).append(face)

        elif kind == GeomAbs_SurfaceType.GeomAbs_Torus:
            rounds.setdefault(round(surface.Torus().MinorRadius(), 3),
                              []).append(face)

    found: list[Feature] = []
    for (radius, direction), members in sorted(holes.items(),
                                               key=lambda kv: kv[0][0]):
        places = [m[0] for m in members]
        how = _pattern(places, direction)
        found.append(Feature(
            id=f"hole_{radius * 2:g}".replace(".", "p"),
            kind="hole", size=radius * 2, count=len(members),
            label=f"{len(members)}x Ø{radius * 2:g} through hole"
                  + (f", {how}" if how else ""),
            places=places, axis=(places[0], direction),
            faces=[m[2] for m in members]))

    for radius, members in sorted(rounds.items()):
        found.append(Feature(
            id=f"fillet_{radius:g}".replace(".", "p"),
            kind="fillet", size=radius, count=len(members),
            label=f"{len(members)}x R{radius:g} fillet",
            faces=members))
    return found


def describe(features: list[Feature], shape: TopoDS_Shape) -> str:
    """The solid written out for a model to choose from.

    Sizes and counts only. The model picks an id and a number; it is never
    asked for a coordinate, because that is the one thing it gets wrong and
    the one thing the topology already knows.
    """
    x, y, z = extents(shape)
    lines = [f"Solid: {x:.6g} x {y:.6g} x {z:.6g} mm, "
             f"volume {volume(shape):,.0f} mm3", "Features:"]
    lines += [f"  {f.id}: {f.label}" for f in features]
    return "\n".join(lines)


def select(features: list[Feature], wanted: str) -> Feature:
    """The feature this selector names, resolved against the solid in hand.

    Resolved fresh every edit, so an id that no longer matches anything
    fails loudly here rather than silently editing the wrong face.
    """
    for feature in features:
        if feature.id == wanted:
            return feature
    known = ", ".join(f.id for f in features) or "none"
    raise KeyError(f"no feature called {wanted!r} in this solid. Found: {known}")


# ---------------------------------------------------------------------------
# The edits
# ---------------------------------------------------------------------------

def _defeature(shape: TopoDS_Shape, faces: list) -> TopoDS_Shape:
    """Take faces out and let the kernel close what is left."""
    op = BRepAlgoAPI_Defeaturing()
    op.SetShape(shape)
    targets = TopTools_ListOfShape()
    for face in faces:
        targets.Append(face)
    op.AddFacesToRemove(targets)
    op.Build()
    if not op.IsDone():
        raise RuntimeError("the kernel could not close the part after "
                           "removing those faces")
    return op.Shape()


def remove(shape: TopoDS_Shape, feature: Feature) -> TopoDS_Shape:
    """Delete a feature and heal the solid - filling a hole, flattening a
    fillet. What a designer means by 'get rid of', and what defeaturing for
    analysis does."""
    return _defeature(shape, feature.faces)


def resize_hole(shape: TopoDS_Shape, feature: Feature,
                diameter: float) -> TopoDS_Shape:
    """Open a hole pattern out, or close it down.

    Fill the old holes in, then drill new ones on the axes the old ones
    were on. Those axes came off the topology, not out of a parameter
    anybody stored - which is the whole point.
    """
    if feature.kind != "hole":
        raise ValueError(f"{feature.id} is a {feature.kind}, not a hole")
    if diameter <= 0:
        raise ValueError("a hole needs a positive diameter")

    places = list(feature.places)
    direction = feature.axis[1]
    filled = _defeature(shape, feature.faces)

    # Long enough to pass clean through from well outside, whatever the
    # part's size and wherever the axis points.
    x, y, z = extents(shape)
    reach = (x + y + z) * 2.0 + 10.0
    d = gp_Dir(*direction)
    out = filled
    for place in places:
        start = gp_Pnt(place[0] - d.X() * reach / 2.0,
                       place[1] - d.Y() * reach / 2.0,
                       place[2] - d.Z() * reach / 2.0)
        drill = BRepPrimAPI_MakeCylinder(
            gp_Ax2(start, d), diameter / 2.0, reach).Shape()
        cut = BRepAlgoAPI_Cut(out, drill)
        cut.Build()
        if not cut.IsDone():
            raise RuntimeError(f"could not drill Ø{diameter:g} at {place}")
        out = cut.Shape()
    return out


def add_fillet(shape: TopoDS_Shape, radius: float,
               where: str = "all") -> TopoDS_Shape:
    """Break the sharp edges.

    ``where`` is "all", or "top"/"bottom" for the edges bounding the
    highest or lowest flat face - the two a person actually asks for.
    """
    if radius <= 0:
        raise ValueError("a fillet needs a positive radius")

    wanted = _edges_for(shape, where)
    if not wanted:
        raise ValueError(f"no edges found for {where!r}")
    maker = BRepFilletAPI_MakeFillet(shape)
    for edge in wanted:
        maker.Add(radius, edge)
    maker.Build()
    if not maker.IsDone():
        raise RuntimeError(
            f"R{radius:g} will not fit on those edges - the kernel could "
            f"not build the blend. Try a smaller radius.")
    return maker.Shape()


def _edges_for(shape: TopoDS_Shape, where: str) -> list:
    """The edges a plain-language selector means."""
    if where == "all":
        out, seen, explorer = [], set(), TopExp_Explorer(
            shape, TopAbs_ShapeEnum.TopAbs_EDGE)
        while explorer.More():
            edge = TopoDS.Edge_s(explorer.Current())
            key = edge.HashCode(1 << 30)
            if key not in seen:
                seen.add(key)
                out.append(edge)
            explorer.Next()
        return out

    # The flat face at the top or the bottom, and the edges around it.
    best, best_z = None, None
    for face in _faces(shape):
        surface = BRepAdaptor_Surface(face)
        if surface.GetType() != GeomAbs_SurfaceType.GeomAbs_Plane:
            continue
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        z = props.CentreOfMass().Z()
        if best_z is None or (z > best_z if where == "top" else z < best_z):
            best, best_z = face, z
    if best is None:
        return []
    out, explorer = [], TopExp_Explorer(best, TopAbs_ShapeEnum.TopAbs_EDGE)
    while explorer.More():
        out.append(TopoDS.Edge_s(explorer.Current()))
        explorer.Next()
    return out


#: The verbs a recipe may use. Deliberately short: each one is an edit a
#: person asks for in a sentence, and each one is something the kernel can
#: do reliably on a solid it did not build. Moving a face and re-solving
#: its neighbours is the obvious absentee - that is where OCCT is weaker
#: than the kernels NX and SolidWorks sit on, so it is not offered.
VERBS = {
    "remove": ("select",),
    "resize_hole": ("select", "diameter"),
    "add_fillet": ("radius", "where"),
}


def apply(shape: TopoDS_Shape, recipe: dict) -> TopoDS_Shape:
    """Perform one edit, resolving its selector against this solid."""
    op = recipe.get("op")
    if op not in VERBS:
        raise ValueError(f"unknown edit {op!r}. Known: {', '.join(VERBS)}")
    features = recognise(shape)

    if op == "remove":
        return remove(shape, select(features, recipe["select"]))
    if op == "resize_hole":
        return resize_hole(shape, select(features, recipe["select"]),
                           float(recipe["diameter"]))
    return add_fillet(shape, float(recipe["radius"]),
                      str(recipe.get("where", "all")))


def apply_all(shape: TopoDS_Shape, recipes: list[dict]) -> TopoDS_Shape:
    """Perform several edits in order, re-recognising between each.

    Re-recognising is not tidiness. After the first edit the face that was
    selected may not exist, and the next selector has to be resolved
    against what is there now rather than against what was there when the
    recipe was written.
    """
    out = shape
    for recipe in recipes:
        out = apply(out, recipe)
    return out


def changed(before: TopoDS_Shape, after: TopoDS_Shape) -> dict:
    """What the edit actually did, measured rather than asserted."""
    was, now = recognise(before), recognise(after)
    return {
        "volume": (round(volume(before), 1), round(volume(after), 1)),
        "extents": ([round(v, 3) for v in extents(before)],
                    [round(v, 3) for v in extents(after)]),
        "faces": (len(_faces(before)), len(_faces(after))),
        "before": [f.label for f in was],
        "after": [f.label for f in now],
    }


# ---------------------------------------------------------------------------
# The sentence a person types
# ---------------------------------------------------------------------------

#: What the model is told it may do. Short on purpose. A model asked to
#: write geometry for an imported part produces a plausible script and a
#: wrong solid; asked which of three named features to change and what to,
#: it answers in forty tokens and the kernel does the rest.
RECIPE_SYSTEM = """You turn a request to change a CAD part into edits.

You are given the features already found in the solid. You may only use
these operations, and you may only select features by the ids listed:

  {"op": "resize_hole", "select": "<feature id>", "diameter": <mm>}
  {"op": "remove",      "select": "<feature id>"}
  {"op": "add_fillet",  "radius": <mm>, "where": "all" | "top" | "bottom"}

Reply with strict JSON only, no prose:
  {"edits": [ ... ], "note": "<one short sentence>"}

Rules:
  - Never invent a feature id. If nothing listed fits, return an empty
    edits list and say so in the note.
  - Diameters and radii are millimetres. Never guess a position; the
    solid already knows where its features are.
  - "Mounting holes" usually means the smaller pattern, not a single
    central bore."""


def plan_edits(prompt: str, features: list[Feature], shape: TopoDS_Shape,
               client: Any, model: str, repair=None) -> dict:
    """Ask a model which edits the sentence means.

    The model chooses and names; it never writes geometry and never states
    a coordinate. Whatever comes back is then applied by the kernel and
    measured, so a wrong answer is a wrong *edit* that shows up in the
    numbers, not a silently wrong solid.
    """
    import json

    reply = client.messages.create(
        model=model, max_tokens=500, system=RECIPE_SYSTEM,
        messages=[{"role": "user", "content":
                   f"{describe(features, shape)}\n\nRequest: {prompt}"}])
    text = "".join(block.text for block in reply.content).strip()
    if repair is not None:
        text = repair(text)
    plan = json.loads(text)
    edits = plan.get("edits") or []

    # The model is allowed to be wrong; it is not allowed to be wrong
    # quietly. Anything it made up is rejected here, before the kernel
    # touches the solid.
    known = {f.id for f in features}
    for edit in edits:
        if edit.get("op") not in VERBS:
            raise ValueError(f"the model asked for an edit that does not "
                             f"exist: {edit.get('op')!r}")
        wanted = edit.get("select")
        if wanted is not None and wanted not in known:
            raise ValueError(f"the model selected {wanted!r}, which is not "
                             f"in this solid. Found: {', '.join(sorted(known))}")
    return plan
