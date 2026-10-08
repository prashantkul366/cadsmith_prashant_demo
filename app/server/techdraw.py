"""A real TechDraw sheet in the engineer's own FreeCAD document.

The other road draws its own sheet: it projects the solid itself, lays the
views out, and writes SVG. That is a picture of a drawing. On this road
FreeCAD is already open with the part in it, and FreeCAD has a drawing
workbench - so the sheet can be a TechDraw page in the same document, with
real view objects and real dimension objects, which the engineer opens and
edits rather than receives.

The dimensions are the same ones the other road chose - holes.py decides
what a part needs called out and how to word it - because choosing is one
problem and rendering is another, and only the second differs between the
two roads.

What TechDraw contributes that the custom renderer cannot: the dimensions
are attached to edges rather than drawn at coordinates, so they follow the
part when it changes; the projection group keeps the views aligned and in
the right angle of projection; and the page is a document, not an image.

Every call here runs as a script inside FreeCAD over the RPC bridge, and
each one reports what it did - `getRawValue()` on every dimension it
places - because a dimension that attached to the wrong edge looks exactly
like one that attached to the right edge until somebody reads the number.
"""

from __future__ import annotations

import json
from typing import Any, Optional

#: The stock ISO sheets FreeCAD ships. Asked for by name rather than by
#: path, because the path is wherever this engineer installed FreeCAD.
SHEETS = {
    "A3": "ISO/A3_Landscape_ISO5457_advanced.svg",
    "A4": "ISO/A4_LandscapeTD.svg",
}
DEFAULT_SHEET = "A3"

#: First angle, which is what ISO uses and what the other road's sheets
#: already declare in their title block. One app, one convention.
PROJECTION = "First angle"

#: The script run inside FreeCAD. Written as one string and handed to the
#: bridge, which is how every other tool on this road talks to FreeCAD.
#: It reports a JSON line so the caller can check the dimensions rather
#: than hope: a dimension on the wrong edge is indistinguishable from one
#: on the right edge until somebody reads the value.
_BUILD = r'''
import json, os
import FreeCAD, TechDraw

doc = FreeCAD.getDocument(%(document)r)
part = doc.getObject(%(part)r)
wanted = json.loads(%(dimensions)r)
sheet = %(sheet)r

report = {"dimensions": [], "skipped": [], "page": None}

# Somewhere to find the template, whatever this installation looks like.
template = ""
for root in (os.path.join(FreeCAD.getResourceDir(), "Mod", "TechDraw",
                          "Templates"),
             os.path.join(FreeCAD.getHomePath(), "Mod", "TechDraw",
                          "Templates")):
    candidate = os.path.join(root, sheet)
    if os.path.exists(candidate):
        template = candidate
        break

old = doc.getObject("CADSmithPage")
if old is not None:
    for view in list(getattr(old, "Views", [])):
        doc.removeObject(view.Name)
    doc.removeObject(old.Name)

page = doc.addObject("TechDraw::DrawPage", "CADSmithPage")
page.Label = "Drawing"
if template:
    holder = doc.addObject("TechDraw::DrawSVGTemplate", "CADSmithTemplate")
    holder.Template = template
    page.Template = holder
doc.recompute()
page.ProjectionType = %(projection)r

group = doc.addObject("TechDraw::DrawProjGroup", "CADSmithViews")
page.addView(group)
group.Source = [part]
group.ProjectionType = %(projection)r
group.addProjection("Front")
group.Anchor.Direction = FreeCAD.Vector(0, 0, 1)
group.Anchor.XDirection = FreeCAD.Vector(1, 0, 0)
for which in ("Right", "Top"):
    try:
        group.addProjection(which)
    except Exception:
        pass
doc.recompute()
if getattr(page, "Template", None) is not None:
    group.X = float(page.Template.Width) / 2.0
    group.Y = float(page.Template.Height) / 2.0
doc.recompute()

front = group.Anchor
edges = front.getVisibleEdges()
lines = [(i, e) for i, e in enumerate(edges)
         if not hasattr(e.Curve, "Radius")]
circles = [(i, e) for i, e in enumerate(edges) if hasattr(e.Curve, "Radius")]


def place(kind, index, name, spec):
    """One dimension, attached to an edge and then read back."""
    dim = doc.addObject("TechDraw::DrawViewDimension", name)
    page.addView(dim)
    dim.Type = kind
    dim.References2D = [(front, "Edge%%d" %% index)]
    if spec:
        dim.FormatSpec = spec
    doc.recompute()
    report["dimensions"].append({
        "name": name, "type": kind, "edge": index,
        "value": round(dim.getRawValue(), 4),
    })


placed = 0
for want in wanted:
    kind = want.get("type")
    try:
        if kind == "Diameter":
            # The circle whose radius this callout is about, which is how
            # a hole's leader finds its own hole rather than the nearest.
            target = want.get("radius")
            found = [i for i, e in circles
                     if abs(e.Curve.Radius - float(target)) <= 0.01]
            if not found:
                report["skipped"].append(
                    {"want": want, "why": "no circle of that radius"})
                continue
            place(kind, found[0], "CADSmithDim%%d" %% placed,
                  want.get("spec") or "")
        elif kind in ("DistanceX", "DistanceY"):
            if not lines:
                report["skipped"].append({"want": want, "why": "no edges"})
                continue
            index = max(lines, key=lambda ie: ie[1].Length)[0]
            place(kind, index, "CADSmithDim%%d" %% placed,
                  want.get("spec") or "")
        else:
            report["skipped"].append({"want": want, "why": "unknown type"})
            continue
        placed += 1
    except Exception as error:
        report["skipped"].append(
            {"want": want, "why": "%%s: %%s" %% (type(error).__name__, error)})

doc.recompute()
report["page"] = page.Name
report["views"] = len(group.Views)
report["edges"] = len(edges)
print("CADSMITH_TECHDRAW " + json.dumps(report))
'''


def build(bridge: Any, document: str, part: str,
          dimensions: Optional[list] = None,
          sheet: str = DEFAULT_SHEET, timeout: float = 120.0) -> dict:
    """Draw this part on a TechDraw page, and say what was placed.

    `dimensions` is the scheme chosen elsewhere - each entry a type, the
    radius it belongs to where that matters, and the text to print. The
    answer carries every dimension's measured value, so a caller can check
    that what landed on the page is what it asked for.

    Never raises for a drawing that could not be made: a part is still a
    part without a sheet, and the reason comes back instead.
    """
    script = _BUILD % {
        "document": document,
        "part": part,
        "dimensions": json.dumps(dimensions or []),
        "sheet": SHEETS.get(sheet, SHEETS[DEFAULT_SHEET]),
        "projection": PROJECTION,
    }
    try:
        printed = bridge.run(script, timeout=timeout)
    except Exception as error:
        return {"ok": False, "why": f"{type(error).__name__}: {error}"}
    for line in (printed or "").splitlines():
        if line.startswith("CADSMITH_TECHDRAW "):
            try:
                answer = json.loads(line[len("CADSMITH_TECHDRAW "):])
            except json.JSONDecodeError as error:
                return {"ok": False, "why": f"unreadable report: {error}"}
            answer["ok"] = True
            return answer
    return {"ok": False, "why": "FreeCAD drew nothing it would report on"}


def scheme(found: list) -> list[dict]:
    """The dimensions to ask TechDraw for, from the holes holes.py read.

    The same choice the other road makes, in the shape this one needs: a
    diameter per distinct hole, worded as that road words it, plus the
    overall length. Keeping the choosing in one place is the whole reason
    it is a separate module from either renderer.
    """
    out: list[dict] = [{"type": "DistanceX", "spec": ""}]
    for group in found or []:
        out.append({
            "type": "Diameter",
            "radius": round(group["radius"], 4),
            # TechDraw writes the measured value wherever %.2w appears, so
            # the depth and the counterbore ride along after it and the
            # number itself stays the kernel's.
            "spec": "%.2w" + _tail(group["label"]),
        })
    return out


def _tail(label: str) -> str:
    """Everything a callout says after its diameter.

    `4x O6.6 THRU (cbore) O11 x 6.5` -> ` THRU (cbore) O11 x 6.5`. The
    count and the diameter are TechDraw's to write - it measures the edge
    itself - and the rest is what only the solid knew.
    """
    if not label:
        return ""
    marker = label.find("Ø")
    if marker < 0:
        return ""
    rest = label[marker + 1:]
    for index, char in enumerate(rest):
        if not (char.isdigit() or char == "."):
            return rest[index:]
    return ""
