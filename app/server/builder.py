"""Plan a part, build it in FreeCAD, and measure what came out.

The pipeline this app was built on asks for a whole CadQuery script, judges
the result, and on a failure asks for the whole script again. This keeps the
half of that which earns its keep and replaces the half that does not.

**The Planner stays, and gains a job.** It still decomposes the request into
components and key dimensions. What it now also does is say what must be
true at the end, so there is something to check the finished solid against
that is not the model's own opinion of its work.

**The Coder, the Executor and the Refiner collapse into one loop.** Each
tool call is small, its result carries measurements, and a wrong step costs
one step instead of a regenerated script. That is the whole of why driving a
CAD through tool calls is immediate.

**The Judge is demoted, which is a promotion for the kernel.** Convergence
used to be a vision model's verdict. Here the gate is ``spec.measure_step``
against the dimensions ``stated.py`` read out of the request - measured, not
judged. Vision is still worth having for what measurement cannot express,
but it no longer decides.

The part never appears in FreeCAD's window as far as the person is
concerned: it is exported and shown in this app's own viewer, drawn by this
app's own drawing code, and adjusted by this app's own sliders.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from app.server import freecad, freecad_tools, spec, stated, toolbox

#: How many tool calls one part may take. A bracket is six; a part needing
#: more than this is one the loop is not going to finish.
MAX_STEPS = 24

PLANNER_SYSTEM = """You plan a mechanical part before it is built in FreeCAD.

Reply with strict JSON only:
{
  "description": "<one sentence>",
  "components": ["base plate", "vertical wall", ...],
  "build_order": ["<short step>", ...],
  "key_dimensions": {"<name>": <number in mm>, ...},
  "must_be_true": ["<a checkable statement about the finished solid>", ...]
}

Rules:
  - Use the dimensions the request states, exactly. Never round or adjust
    them, and never invent one it did not give.
  - build_order is for a builder with primitives (box, cylinder, cone,
    sphere, tube), booleans, and arbitrary FreeCAD Python. Keep it short.
  - must_be_true is for checking afterwards: overall sizes, hole counts and
    diameters, wall thicknesses. Things a kernel can measure, not opinions.
"""

BUILDER_SYSTEM = """You build mechanical parts in FreeCAD by calling tools.

How to work:
  1. Follow the plan you are given. Use the stated dimensions exactly.
  2. Before building a standard part - a washer, bearing, screw, gear, a
     named handlebar - try place_standard_part. It is already verified.
  3. Build solids, then cut the holes and pockets with combine(cut).
     Cutting tools must be long enough to pass clean through, and placed
     so they do.
  4. Anything repeated - a bolt circle, a row of holes - is one shape and
     then pattern_circular or pattern_linear. Do not work the positions out
     yourself and do not write a script for them: the tool is a tenth of
     the tokens and the arithmetic is FreeCAD's.
  5. Every tool tells you what it measured. Read it. If a size is wrong,
     fix it with set_size before carrying on.
  6. If the request says what the part is made of, call set_material. It
     gives the weight, and a weight the request set a limit on is checked.
  7. Call declare_parameter for the handful of numbers a person should be
     able to adjust afterwards - overall sizes, hole diameters, wall
     thicknesses. Use scale=2 to show a diameter over a Radius property.
  8. When the part is finished and its measurements match the plan, stop
     and say in one sentence what you built.

Make every call you can in one go. Each reply is a round trip of several
seconds, and the calls that do not depend on each other - the plate, the
bore, the first bolt hole - cost one round trip together or three apart.
Only wait for an answer when you actually need it: a boolean needs the
shapes to exist, a pattern needs the shape it repeats.

FreeCAD's origin is at (0, 0, 0) and a Part::Box grows from its placement
towards +X, +Y, +Z. A Part::Cylinder grows along +Z from its placement.
"""


def plan(prompt: str, client: Any, model: str,
         on_usage: Optional[Any] = None) -> dict:
    """What to build, before anything is built.

    Falls back to a plan with no components rather than failing the run: a
    builder with the request and no plan still builds, and losing the whole
    part because the planning call came back malformed would be the wrong
    trade.

    ``on_usage`` is handed what this call cost. The build loop counts its
    own tokens; without this the planning call would be spent off the books,
    which is the one kind of spend a ceiling cannot hold.
    """
    from app.server import providers

    note = stated.note(prompt)
    reply = client.messages.create(
        model=model, max_tokens=1200, system=PLANNER_SYSTEM,
        messages=[{"role": "user", "content": prompt + ("\n" + note if note else "")}])
    if on_usage is not None:
        on_usage({"input_tokens": getattr(reply.usage, "input_tokens", 0),
                  "output_tokens": getattr(reply.usage, "output_tokens", 0),
                  "calls": 1})
    text = "".join(block.text for block in reply.content)
    try:
        return json.loads(providers.repair_json(text))
    except (json.JSONDecodeError, TypeError):
        return {"description": prompt, "components": [], "build_order": [],
                "key_dimensions": {}, "must_be_true": []}


def _task(prompt: str, design: dict) -> str:
    """The plan and the request, as one instruction for the builder."""
    lines = [f"Build this part: {prompt}", ""]
    if design.get("components"):
        lines.append("Components: " + ", ".join(design["components"]))
    if design.get("key_dimensions"):
        lines.append("Key dimensions (mm): " + ", ".join(
            f"{name} = {value:g}" for name, value in
            design["key_dimensions"].items()
            if isinstance(value, (int, float))))
    if design.get("build_order"):
        lines.append("Suggested order:")
        lines += [f"  {n}. {step}" for n, step in
                  enumerate(design["build_order"], start=1)]
    if design.get("must_be_true"):
        lines.append("The finished solid must satisfy:")
        lines += [f"  - {claim}" for claim in design["must_be_true"]]
    note = stated.note(prompt)
    if note:
        lines += ["", note]
    return "\n".join(lines)


def build(bridge: freecad.Bridge, prompt: str, client: Any, model: str,
          design: Optional[dict] = None, document: str = "",
          on_step: Optional[Any] = None, max_steps: int = MAX_STEPS,
          before_call: Optional[Any] = None) -> tuple[freecad_tools.Session,
                                                      toolbox.Transcript]:
    """Build the part in FreeCAD, one measured step at a time."""
    session = freecad_tools.Session(bridge, document)
    box = freecad_tools.toolbox_for(session)
    transcript = toolbox.converse(
        client, model, BUILDER_SYSTEM, _task(prompt, design or {}), box,
        max_steps=max_steps, on_step=on_step, before_call=before_call)
    return session, transcript


# ---------------------------------------------------------------------------
# What came out, measured rather than judged
# ---------------------------------------------------------------------------

def collect(session: freecad_tools.Session, version_dir: Path) -> dict:
    """Export what FreeCAD built into the version's own directory.

    Three files and they are all the app already needs: the STEP everything
    downstream measures and draws, the STL the viewer loads, and the FreeCAD
    document itself - which is the deliverable a STEP can never be, because
    an engineer can open it and carry on with a live tree.
    """
    version_dir.mkdir(parents=True, exist_ok=True)
    out: dict = {}

    step = version_dir / "model.step"
    step.write_bytes(session.bridge.fetch(session.document, "step"))
    out["step"] = step

    try:
        out["stl"] = mesh(step, version_dir / "model.stl")
    except Exception:
        # Falling back to FreeCAD's own mesher rather than leaving the
        # viewer with nothing.
        try:
            stl = version_dir / "model.stl"
            stl.write_bytes(session.bridge.fetch(session.document, "stl"))
            out["stl"] = stl
        except freecad.FreeCADError:
            pass    # the viewer degrades to the drawing; the part is intact

    try:
        out["document"] = save_document(session, version_dir / "part.FCStd")
    except freecad.FreeCADError:
        pass
    return out


def warm_up() -> None:
    """Tessellate something tiny so the first real part does not pay for it.

    OCCT's mesher initialises on its first call and that costs about one and
    a half seconds - measured, once per process, against twenty milliseconds
    for every mesh after it. Left alone it lands on whoever makes the first
    part of the session, which is the one somebody is watching.

    Swallows everything: this is a head start, not a requirement.
    """
    try:
        import cadquery as cq
        import tempfile

        box = cq.Workplane("XY").box(1, 1, 1)
        cq.exporters.export(box, str(Path(tempfile.gettempdir())
                                     / "cadsmith_warmup.stl"),
                            exportType="STL", tolerance=0.1,
                            angularTolerance=0.2)
    except Exception:
        pass


def mesh(step: Path, path: Path) -> Path:
    """The mesh the viewer loads, made here from the solid that was measured.

    Asked of this app's own kernel rather than of FreeCAD, for two reasons
    that are both about the same thing - the viewer showing the part that
    was checked.

    *It is the measured solid.* ``spec.measure_step`` reads the STEP; so
    does this. A mesh fetched separately from FreeCAD is a second export of
    a document that may have moved on, and a viewer disagreeing with the
    measurements is the worst kind of wrong, because it looks right.

    *It is binary and an eighth the size.* FreeCAD writes ASCII STL: a
    150 mm flange came to 2.4 MB against 100 KB here, every byte of it down
    the wire to a browser.
    """
    import cadquery as cq

    path.parent.mkdir(parents=True, exist_ok=True)
    solid = cq.importers.importStep(str(step))
    # 0.1 mm chordal, 0.2 rad angular: a 50 mm bore comes out round to the
    # eye without the triangle count a CAD's default deviation produces.
    cq.exporters.export(solid, str(path), exportType="STL",
                        tolerance=0.1, angularTolerance=0.2)
    return path


def save_document(session: freecad_tools.Session, path: Path) -> Path:
    """Snapshot the live FreeCAD document beside the version's geometry.

    Saved per version rather than once per job, because going back in the
    filmstrip has to reopen *that* version's tree. Without this, stepping
    back shows an older solid while every edit silently lands on the newest
    document - which looks like it works and is not.

    This is the one call that passes a path to FreeCAD rather than carrying
    bytes, because an ``.FCStd`` is only useful if FreeCAD can open it again
    later - and it is FreeCAD that has to open it. So FreeCAD writes it, and
    this checks from here whether the file arrived. It did when FreeCAD is on
    this machine, which is how the addon is normally run; it did not when
    FreeCAD is somewhere else, and then the part is still complete - the
    geometry travelled as bytes - but there is no document to reopen, and
    saying so is better than recording a filename that is not there.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    session.bridge.run(f"""
import FreeCAD
doc = FreeCAD.getDocument({session.document!r})
doc.saveAs({str(path)!r})
""")
    if not path.exists():
        raise freecad.FreeCADError(
            f"FreeCAD saved the document, but not anywhere this server can "
            f"see ({path}). FreeCAD is running on another machine, so the "
            f"live document stays there; the geometry came back regardless.")
    return path


def reopen(bridge: freecad.Bridge, path: Path) -> str:
    """Open a saved version again, and report the name FreeCAD gave it.

    Idempotent, which matters more than it looks. FreeCAD de-duplicates
    document names, so opening the same file twice leaves two documents with
    the same tree and a name that no longer says which is which - and the
    second parameter drag would land in whichever one came back. A file that
    is already open is found and reused.

    The name this returns is the one every later call must use, not the one
    on the file.
    """
    name = bridge.value(f"""
import FreeCAD, os
wanted = os.path.normcase(os.path.abspath({str(path)!r}))
found = ""
for doc in FreeCAD.listDocuments().values():
    here = getattr(doc, "FileName", "") or ""
    if here and os.path.normcase(os.path.abspath(here)) == wanted:
        found = doc.Name
        break
if not found:
    found = FreeCAD.openDocument(wanted).Name
{freecad.marked("found")}
""")
    if not name:
        raise freecad.FreeCADError(f"FreeCAD would not open {path}")
    return name


def from_the_request(prompt: str) -> dict:
    """A design plan made of what was asked for, with no model call.

    The Planner costs a round trip - several seconds, and a thousand output
    tokens - before any geometry exists, and the builder loop does not need
    what it produces: it has the request, the dimensions ``stated.py`` read
    out of it, and tools that answer with measurements. The gate never read
    the plan either; it has always measured against the request.

    So for a request that states its own dimensions this stands in for it,
    and what the Design Plan panel shows is what was asked rather than a
    model's paraphrase of it. The Planner is still there for a request too
    vague to read anything out of.
    """
    wanted = stated.requirements(prompt)
    sizes: dict[str, float] = {}
    for value in sorted(set(wanted.get("extents") or []), reverse=True):
        sizes[f"{value:g} mm overall"] = value
    for value in sorted(set(wanted.get("bores") or [])):
        sizes[f"Ø{value:g} hole"] = value
    for value in sorted(set(wanted.get("advisory") or [])):
        sizes.setdefault(f"{value:g} mm stated", value)

    must: list[str] = []
    if wanted.get("hole_count"):
        must.append(f"{wanted['hole_count']} hole(s), as the request asks for")
    for value in sorted(set(wanted.get("bores") or [])):
        must.append(f"a Ø{value:g} hole")
    for value in sorted(set(wanted.get("extents") or [])):
        must.append(f"{value:g} mm appears in the overall size")
    return {"description": prompt, "components": [], "build_order": [],
            "key_dimensions": sizes, "must_be_true": must,
            "from_the_request": True}


def readable(prompt: str) -> bool:
    """Whether the request states enough to build from without a Planner."""
    wanted = stated.requirements(prompt)
    return bool(wanted.get("extents") or wanted.get("bores")
                or wanted.get("advisory"))


def for_panel(design: dict) -> dict:
    """The plan in the shape the rest of the app already speaks.

    ``spec.compare`` and the Design Plan panel both read the pipeline
    Planner's layout, so the FreeCAD Planner's answer is translated into it
    rather than given a second code path on either side. ``must_be_true``
    comes along untouched: nothing measures it, and it is the sentence a
    person can read to see what the run was holding itself to.
    """
    return {
        "description": design.get("description") or "",
        "components": list(design.get("components") or []),
        "dimensions": {"key_dimensions": dict(design.get("key_dimensions") or {})},
        "constraints": {},
        "build_order": list(design.get("build_order") or []),
        "must_be_true": list(design.get("must_be_true") or []),
    }


#: A change that is meant to leave less of the part than it found.
_REMOVAL = re.compile(
    r"\b(remove|delete|drop|lose|get\s+rid\s+of|take\s+out|fill\s+in|plug|"
    r"without|no\s+more|eliminat\w*|omit)\b", re.IGNORECASE)


def _wanted(prompt: str, instruction: str = "") -> dict:
    """What must be true of the solid now.

    After a change, the request that built the part is no longer the whole
    story: "open the hole out to 25" supersedes the 20 the original asked
    for, and holding the part to both is holding it to a number nobody wants
    any more. So the change's own dimensions block, and the original's sizes
    and bores are carried alongside as advisory - reported, because "you
    asked for 20 and it is 25 now" is worth seeing, and not blocking,
    because it is the thing that was just asked for.

    The hole *count* is the exception, and it earned the exception. Asked to
    make a plate thicker, an 8B rebuilt it from scratch as a plain box and
    reported success; the part had lost its hole. A change supersedes a
    dimension; it does not quietly delete a feature. So unless the change
    says how many holes there should be, the original's count still blocks.
    """
    original = stated.requirements(prompt)
    if not instruction:
        return original
    asked = stated.requirements(instruction)

    def many(key: str) -> list:
        return list(asked.get(key) or []) + list(original.get(key) or [])

    # ...and the exception to the exception. "Remove the hole" is a change
    # that is *supposed* to leave one fewer, so carrying the old count
    # forward would refuse the part for doing exactly what was asked.
    taking_away = bool(_REMOVAL.search(instruction))

    return {
        "extents": list(asked.get("extents") or []),
        "bores": list(asked.get("bores") or []),
        # A feature that was there before should still be there, unless this
        # change is the one that says otherwise.
        "hole_count": (asked.get("hole_count")
                       if asked.get("hole_count") is not None
                       else (None if taking_away
                             else original.get("hole_count"))),
        "advisory": (list(asked.get("advisory") or [])
                     + list(original.get("extents") or [])
                     + list(original.get("advisory") or [])
                     + list(original.get("bores") or [])),
        "read": many("read"),
    }


def check(step: Path, prompt: str, design: Optional[dict] = None,
          instruction: str = "", material: Optional[dict] = None) -> dict:
    """Measure the finished solid against what was asked for.

    This is the gate, and it is a measurement rather than a verdict. The
    numbers come off the exported solid; the expectations come from the
    request itself, read by ``stated.py`` before any model saw it. A part
    that does not match says so, whatever the builder thought of its work.

    It is ``spec.check`` - the same gate the pipeline runs, keys and all, so
    the Validation panel draws these rows exactly as it draws a generated
    part's. Writing a second one here would have meant a second set of
    tolerances to keep in step with the first, and the drill sizes, the
    thin-section check and the clash test thrown away.
    """
    report = spec.check(for_panel(design or {}), step,
                        _wanted(prompt, instruction))
    out = report.to_dict()
    # ``ok`` is "nothing measurable contradicts this". The gate also has to
    # answer for the case where nothing could be measured at all, which is
    # not a pass.
    # What it weighs, when something has said what it is made of. A mass is
    # a density multiplied by a measured volume, so it belongs with the
    # measurements rather than with anything the model said - and a request
    # that set a ceiling has given the gate something to hold it to.
    weighed = _weight_row(out, prompt, instruction, material)
    if weighed:
        out["checks"].append(weighed)

    blocking = [row for row in out["checks"]
                if row["passed"] is False and row["hard"]]
    out["passed"] = bool(report.checked and not report.error and not blocking)
    out["problems"] = [row["label"] for row in blocking]
    return out


def _weight_row(out: dict, prompt: str, instruction: str,
                material: Optional[dict]) -> Optional[dict]:
    """The mass of the measured solid, against any ceiling that was set."""
    from app.server import materials

    if not material:
        return None
    volume = (out.get("measured") or {}).get("volume")
    weighed = materials.weigh(volume, material)
    if not weighed:
        return None
    out["mass"] = weighed
    ceiling = materials.limit(instruction) or materials.limit(prompt)
    if ceiling is None:
        # Reported, not judged. Nobody said what it had to come in under.
        return {"key": "mass", "label": f"mass in {weighed['material']}",
                "expected": "no limit set", "hard": False, "passed": True,
                "actual": f"{weighed['mass_g']:,.0f} g"}
    return {"key": "mass", "label": f"mass in {weighed['material']}",
            "expected": f"under {ceiling * 1000:,.0f} g",
            "actual": f"{weighed['mass_g']:,.0f} g",
            "passed": weighed["mass_kg"] <= ceiling, "hard": True}


# ---------------------------------------------------------------------------
# The numbers a person can drag
# ---------------------------------------------------------------------------

def parameter_map(session: freecad_tools.Session) -> list[dict]:
    """The declared parameters, in the shape the slider panel already draws.

    Same fields ``edits.describe_parameters`` produces for a CadQuery
    script, so the panel needs no second code path - plus the three it
    ignores, which say where the number actually lives.
    """
    from app.server import edits

    out: list[dict] = []
    for declared in session.declared:
        found = session.bridge.object(session.document, declared["object"])
        raw = ((found or {}).get("Properties") or {}).get(declared["property"])
        reading = freecad.number(raw)
        if reading is None:
            continue
        value = reading * float(declared.get("scale") or 1.0)
        kind = edits._kind(declared["name"])                 # noqa: SLF001
        low, high, step = edits._range_for(kind, value)      # noqa: SLF001
        out.append({
            "name": declared["name"],
            "label": declared["label"],
            "value": value,
            "kind": kind,
            "unit": {"angle": "°", "count": "", "length": "mm"}[kind],
            "integer": float(value).is_integer() and kind == "count",
            "min": min(low, value), "max": max(high, value), "step": step,
            # Ignored by the panel, used when a value comes back.
            "object": declared["object"],
            "property": declared["property"],
            "scale": float(declared.get("scale") or 1.0),
        })
    return out


def apply_parameters(bridge: freecad.Bridge, document: str,
                     mapping: list[dict], values: dict) -> list[str]:
    """Set the declared parameters and let FreeCAD recompute.

    This is what a slider should always have done. A CadQuery part has its
    script rewritten and re-executed whole; here one property is set and the
    tree recomputes only what depends on it.
    """
    by_name = {entry["name"]: entry for entry in mapping}
    changed: list[str] = []
    for name, value in values.items():
        entry = by_name.get(name)
        if entry is None:
            continue
        scale = float(entry.get("scale") or 1.0)
        bridge.edit(document, entry["object"],
                    **{entry["property"]: float(value) / scale})
        changed.append(f"{entry['label']} {float(value):g}")
    if changed:
        bridge.run(f"""
import FreeCAD
FreeCAD.getDocument({document!r}).recompute()
""")
    return changed
