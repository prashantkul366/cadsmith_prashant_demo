"""The document's feature tree, as something a person can read and change.

A STEP file is a solid. A FreeCAD document is a *history*: a pad that came
from a sketch, a pocket cut into it, a pattern of that pocket, each with
the numbers that made it still attached and still editable. That history
is the thing an engineer actually works in, and until now this app has
only ever shown the solid that fell out of the end of it.

This module reads the tree and writes to it:

* :func:`read` - every object, its place in the tree, and each property
  with its value, its unit, its type and whether it can be edited.
* :func:`edit` - set a property, recompute, and say whether the recompute
  held. A value that cannot rebuild is rolled back and refused with its
  reason, which is the same contract :mod:`freecad_run` gives a slider.
* :func:`suppress` - take a feature out of the recompute without deleting
  it, the way a CAD user tries "what if this chamfer were not there".

Everything runs as a script inside FreeCAD over the bridge, like
:mod:`techdraw` does, for two reasons. The addon's own ``get_objects``
returns the properties but not their metadata - no units, no read-only
flag, no dependency links - and a panel that lets someone edit a read-only
property is a panel that lies. And a script runs through any bridge, so
the whole module is testable against a headless ``freecadcmd`` rather than
only against a FreeCAD somebody has to have open.

Three kinds of property are left out of what comes back:

* **Hidden and read-only** ones are reported but marked, because a tree
  that silently drops them tells the reader the object has fewer numbers
  than it does.
* **Links** (``App::PropertyLink``) are reported as the name they point
  at, not as an object, so the tree stays a tree and not a graph dump.
* **Everything that is not a number, a string, a boolean, a length or an
  enumeration** is reported with its type and a printed form, and marked
  as not editable here. A placement matrix is a real property and a text
  box is the wrong way to change one.
"""

from __future__ import annotations

import json
from typing import Any, Optional

#: Property types this panel knows how to put an editor in front of.
#: Anything else is shown and not offered for editing, which is a smaller
#: lie than an editor that cannot write what it reads.
EDITABLE = {
    "App::PropertyLength": "length",
    "App::PropertyDistance": "length",
    "App::PropertyFloat": "number",
    "App::PropertyFloatConstraint": "number",
    "App::PropertyQuantity": "number",
    "App::PropertyAngle": "angle",
    "App::PropertyInteger": "integer",
    "App::PropertyIntegerConstraint": "integer",
    "App::PropertyBool": "boolean",
    "App::PropertyString": "text",
    "App::PropertyEnumeration": "choice",
    "App::PropertyPercent": "integer",
}

#: Properties every object carries that say nothing about the design.
#: Kept out of the default listing because a tree where the first six rows
#: are the same six rows on every object is a tree nobody scrolls.
HOUSEKEEPING = {
    "ExpressionEngine", "Visibility", "Label2", "AttacherEngine",
    "AttacherType", "MapMode", "MapReversed", "MapPathParameter",
    "AttachmentSupport", "AttachmentOffset", "_Body", "BaseFeature",
}

_READ = r'''
import json
import FreeCAD

doc = FreeCAD.getDocument(%(document)r)
verbose = %(verbose)r
housekeeping = set(json.loads(%(housekeeping)r))
editable = json.loads(%(editable)r)


def printable(value):
    """A property value as something JSON can carry and a person can read."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    for attribute in ("Value", "Text"):
        if hasattr(value, attribute):
            return printable(getattr(value, attribute))
    if hasattr(value, "Name"):           # a link to another object
        return value.Name
    if isinstance(value, (list, tuple)):
        return [printable(v) for v in value][:24]
    return str(value)[:200]


def described(obj):
    rows = []
    for name in obj.PropertiesList:
        if name in housekeeping and not verbose:
            continue
        try:
            kind = obj.getTypeIdOfProperty(name)
            raw = getattr(obj, name)
        except Exception:
            continue
        # 2 is hidden, 1 is read-only, in FreeCAD's editor mode bitmask.
        try:
            mode = set(obj.getEditorMode(name) or [])
        except Exception:
            mode = set()
        row = {
            "name": name,
            "type": kind,
            "group": (obj.getGroupOfProperty(name) or "") if hasattr(
                obj, "getGroupOfProperty") else "",
            "value": printable(raw),
            "editor": editable.get(kind),
            "writable": kind in editable and "ReadOnly" not in mode,
            "hidden": "Hidden" in mode,
        }
        if kind == "App::PropertyEnumeration":
            try:
                row["choices"] = list(obj.getEnumerationsOfProperty(name))
            except Exception:
                row["choices"] = []
        unit = getattr(raw, "UserString", None)
        if unit:
            row["shown"] = str(unit)
        rows.append(row)
    return rows


objects = []
for obj in doc.Objects:
    objects.append({
        "name": obj.Name,
        "label": obj.Label,
        "type": obj.TypeId,
        # OutList is what this object is built from, InList what is built
        # from it. A pad's OutList holds its sketch; the sketch's InList
        # holds the pad. That pair is the tree.
        "children": [o.Name for o in obj.OutList],
        "parents": [o.Name for o in obj.InList],
        "visible": bool(getattr(obj, "Visibility", True)),
        "touched": bool(obj.State and "Touched" in obj.State),
        "error": "Invalid" in (obj.State or []),
        # Only a PartDesign feature can be taken out of the recompute, so
        # the panel is told which rows may offer it rather than finding
        # out by being refused.
        "suppressible": hasattr(obj, "Suppressed"),
        "suppressed": bool(getattr(obj, "Suppressed", False)),
        "properties": described(obj),
    })

# The objects nothing else is built from: the tips of the tree, which is
# what a person means by "the part".
tips = [o["name"] for o in objects if not o["parents"]]
print("CADSMITH_TREE " + json.dumps(
    {"document": doc.Name, "objects": objects, "tips": tips}))
'''

_EDIT = r'''
import json
import FreeCAD

doc = FreeCAD.getDocument(%(document)r)
obj = doc.getObject(%(object)r)
wanted = json.loads(%(values)r)
answer = {"object": %(object)r, "set": {}, "refused": {}}

# Undo in FreeCAD is per transaction, and a document with no transactions
# has nothing to undo. An engineer trying things needs to be able to back
# out of one, so every change this module makes is one.
doc.UndoMode = 1

if obj is None:
    answer["why"] = "there is no object called " + %(object)r
    print("CADSMITH_TREE " + json.dumps(answer))
else:
    # Everything is written before the single recompute, so that two
    # numbers that are only valid together - a hole moved and resized to
    # stay inside the part - are not rejected one at a time.
    was = {}
    doc.openTransaction(%(label)r)
    for name, value in wanted.items():
        if name not in obj.PropertiesList:
            answer["refused"][name] = "no such property"
            continue
        try:
            mode = set(obj.getEditorMode(name) or [])
        except Exception:
            mode = set()
        if "ReadOnly" in mode:
            answer["refused"][name] = "read-only"
            continue
        try:
            current = getattr(obj, name)
            was[name] = current.Value if hasattr(current, "Value") else current
            setattr(obj, name, value)
            answer["set"][name] = value
        except Exception as error:
            answer["refused"][name] = "%%s: %%s" %% (type(error).__name__, error)

    if answer["set"]:
        doc.recompute()
        broken = [o.Name for o in doc.Objects if "Invalid" in (o.State or [])]
        answer["broken"] = broken
        if broken:
            # A document that will not rebuild is worse than a change that
            # did not happen, so the change does not happen.
            for name, before in was.items():
                try:
                    setattr(obj, name, before)
                except Exception:
                    pass
            doc.recompute()
            answer["rolled_back"] = True
            # Whether putting it back worked, checked rather than assumed:
            # "we rolled it back" is a claim, and the document either
            # rebuilds now or the person has a broken part and a reassuring
            # message.
            answer["still_broken"] = [o.Name for o in doc.Objects
                                      if "Invalid" in (o.State or [])]
            answer["why"] = ("that value leaves " + ", ".join(broken[:3])
                             + " unable to rebuild")
            answer["set"] = {}
            doc.abortTransaction()
        else:
            doc.commitTransaction()
    if not answer["set"]:
        doc.abortTransaction()
    answer["ok"] = bool(answer["set"]) and not answer.get("rolled_back")
    print("CADSMITH_TREE " + json.dumps(answer))
'''

_SUPPRESS = r'''
import json
import FreeCAD

doc = FreeCAD.getDocument(%(document)r)
obj = doc.getObject(%(object)r)
answer = {"object": %(object)r, "suppressed": %(state)r}
doc.UndoMode = 1
if obj is None:
    answer["why"] = "there is no object called " + %(object)r
elif not hasattr(obj, "Suppressed"):
    # Not every object has it: only PartDesign features do. Hiding is not
    # the same thing and must not be offered as though it were, because a
    # hidden pocket is still cut.
    answer["why"] = (obj.TypeId + " cannot be suppressed; only a PartDesign "
                     "feature can be taken out of the recompute")
else:
    doc.openTransaction(%(label)r)
    obj.Suppressed = %(state)r
    doc.recompute()
    broken = [o.Name for o in doc.Objects if "Invalid" in (o.State or [])]
    answer["broken"] = broken
    answer["ok"] = not broken
    doc.commitTransaction() if not broken else doc.abortTransaction()
    if broken:
        doc.recompute()
print("CADSMITH_TREE " + json.dumps(answer))
'''

_MARK = "CADSMITH_TREE "


def _answer(printed: str, what: str) -> dict:
    """The one JSON line the script prints, or why there wasn't one."""
    for line in (printed or "").splitlines():
        if line.startswith(_MARK):
            try:
                return json.loads(line[len(_MARK):])
            except json.JSONDecodeError as error:
                return {"ok": False, "why": f"unreadable answer: {error}"}
    return {"ok": False,
            "why": f"{what}: FreeCAD printed " +
                   ((printed or "").strip()[:200] or "nothing")}


def read(bridge: Any, document: str, verbose: bool = False,
         timeout: float = 60.0) -> dict:
    """The whole tree of one document.

    `verbose` keeps the properties every object carries - placement,
    visibility, the attachment machinery - which are real and are noise
    until somebody is looking for them.
    """
    script = _READ % {
        "document": document,
        "verbose": bool(verbose),
        "housekeeping": json.dumps(sorted(HOUSEKEEPING)),
        "editable": json.dumps(EDITABLE),
    }
    try:
        printed = bridge.run(script, timeout=timeout)
    except Exception as error:
        return {"ok": False, "why": f"{type(error).__name__}: {error}"}
    answer = _answer(printed, "reading the tree")
    answer.setdefault("ok", "objects" in answer)
    return answer


def edit(bridge: Any, document: str, name: str, values: dict,
         timeout: float = 120.0) -> dict:
    """Set properties on one object, and say whether the part survived."""
    script = _EDIT % {"document": document, "object": name,
                      "values": json.dumps(values),
                      # What FreeCAD's own Edit > Undo menu will say.
                      "label": f"CADSmith: {name}"}
    try:
        printed = bridge.run(script, timeout=timeout)
    except Exception as error:
        return {"ok": False, "why": f"{type(error).__name__}: {error}"}
    return _answer(printed, "editing the tree")


def suppress(bridge: Any, document: str, name: str, state: bool = True,
             timeout: float = 120.0) -> dict:
    """Take a feature out of the recompute, or put it back."""
    script = _SUPPRESS % {"document": document, "object": name,
                          "state": bool(state),
                          "label": f"CADSmith: suppress {name}"}
    try:
        printed = bridge.run(script, timeout=timeout)
    except Exception as error:
        return {"ok": False, "why": f"{type(error).__name__}: {error}"}
    return _answer(printed, "suppressing a feature")


_UNDO = r'''
import json
import FreeCAD

doc = FreeCAD.getDocument(%(document)r)
answer = {"undone": []}
# What the stack holds before anything is taken off it, so the answer can
# say what was backed out rather than only that something was.
available = list(getattr(doc, "UndoNames", []) or [])
for _ in range(max(1, %(steps)d)):
    if not getattr(doc, "UndoCount", 0):
        break
    answer["undone"].append(
        (list(getattr(doc, "UndoNames", []) or []) or [""])[0])
    doc.undo()
doc.recompute()
answer["left"] = int(getattr(doc, "UndoCount", 0))
answer["was"] = available[:6]
answer["ok"] = bool(answer["undone"])
if not answer["ok"]:
    answer["why"] = ("there is nothing to undo in this document - FreeCAD "
                     "only remembers changes made since it was opened")
print("CADSMITH_TREE " + json.dumps(answer))
'''


def undo(bridge: Any, document: str, steps: int = 1,
         timeout: float = 120.0) -> dict:
    """Back out the last change, the way the engineer's own Undo does.

    FreeCAD's undo stack is per transaction, so this reaches changes this
    app made - each one is a transaction - and anything the engineer did
    in FreeCAD itself. It does not reach a change made before the document
    was opened, which is worth saying rather than failing silently.
    """
    script = _UNDO % {"document": document, "steps": int(steps)}
    try:
        printed = bridge.run(script, timeout=timeout)
    except Exception as error:
        return {"ok": False, "why": f"{type(error).__name__}: {error}"}
    return _answer(printed, "undoing a change")


def outline(tree: dict) -> list[dict]:
    """The tree as rows to draw, deepest-first under each tip.

    A feature tree is drawn as a list with indentation, not as a graph,
    and the order is the order the part was built in: a pad under its
    body, its sketch under the pad.
    """
    by_name = {o["name"]: o for o in tree.get("objects") or []}
    rows: list[dict] = []
    seen: set = set()

    def walk(name: str, depth: int) -> None:
        obj = by_name.get(name)
        if obj is None or name in seen:
            return
        seen.add(name)
        rows.append({**obj, "depth": depth})
        for child in obj.get("children") or []:
            walk(child, depth + 1)

    for tip in tree.get("tips") or []:
        walk(tip, 0)
    # Anything in a cycle, or orphaned, still belongs on the page.
    for obj in tree.get("objects") or []:
        walk(obj["name"], 0)
    return rows
