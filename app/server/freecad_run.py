"""Build a part in FreeCAD, as one route through the job the app already runs.

This is the FreeCAD road's answer to ``catalog_run.py``: the same contract -
take a run context, produce artifacts in the version directory, publish a
version - so everything downstream is untouched. The viewer loads the same
``model.stl``, the drawing code reads the same ``model.step``, the Validation
panel draws the same measured rows, and History lists it beside every other
run.

Three things are different, and they are the reason for the road.

**It is built, not written.** No script is generated. A model calls tools,
each call lands in a live FreeCAD document, and each result comes back with
what FreeCAD measured. A wrong step costs one step.

**The deliverable is a document, not a mesh.** ``part.FCStd`` is saved beside
the geometry, so what the app hands over is a live feature tree an engineer
opens in FreeCAD and carries on with. That is the thing a STEP file cannot
carry and ``direct.py`` has to reconstruct.

**The parameters are declared while building.** The builder names the handful
of numbers worth a slider as it makes them, with the FreeCAD object and
property behind each one, and that list is written to ``parameters.json``.
Dragging one later sets a property and lets the tree recompute - it does not
rewrite and re-run a script.

What is *not* different is the gate. ``builder.check`` is ``spec.check``, the
same measurement the pipeline is held to, against the dimensions
``stated.py`` read out of the request before any model saw it. A part built
here earns its pass the same way or not at all.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from app.server import (builder, drawing, freecad, freecad_tools,
                        i18n)
from app.server.events import (
    PHASE_CODE, PHASE_EXECUTE, PHASE_FREECAD, PHASE_PLAN, PHASE_SPEC,
    PHASE_VERSION, STATUS_FAILED, STATUS_INFO, STATUS_OK, STATUS_STARTED,
)
from app.server.instrument import RunContext

#: Where FreeCAD is. From the environment rather than from the request: a
#: host and port a browser could set is a door into whatever else this
#: server can reach, and FreeCAD is a Python interpreter with a document in
#: it.
HOST_ENV = "CADSMITH_FREECAD_HOST"
PORT_ENV = "CADSMITH_FREECAD_PORT"
TOKEN_ENV = "CADSMITH_FREECAD_TOKEN"


def bridge_from_env() -> freecad.Bridge:
    """The FreeCAD this server talks to, as configured."""
    try:
        port = int(os.getenv(PORT_ENV) or freecad.DEFAULT_PORT)
    except ValueError:
        port = freecad.DEFAULT_PORT
    return freecad.Bridge(host=os.getenv(HOST_ENV) or "127.0.0.1",
                          port=port, token=os.getenv(TOKEN_ENV) or "")


def available(bridge: Optional[freecad.Bridge] = None) -> bool:
    """Whether there is a FreeCAD with the addon running to build in.

    Never raises: a FreeCAD that is not open is an ordinary state, and the
    job falls back to the pipeline rather than failing.
    """
    return (bridge or bridge_from_env()).alive()


# ---------------------------------------------------------------------------
# The record of a build
# ---------------------------------------------------------------------------

TRANSCRIPT_HEADER = '''"""How this part was built, step by step, in FreeCAD.

This is the record of the build, not a script that would reproduce it. The
part was made by calling tools against a live FreeCAD document; each line
below is one call and what FreeCAD measured afterwards. Nothing here is
re-executed by this app.

What to open instead:
  part.FCStd   the live FreeCAD document, with its feature tree
  model.step   the solid, which every other tool reads
  model.stl    the mesh the viewer in this app is showing you
"""
'''


def transcript_text(prompt: str, design: dict, transcript: Any) -> str:
    """The build, as something a person can read in the Code panel."""
    lines = [TRANSCRIPT_HEADER, f"# Asked for: {prompt}", ""]
    if design.get("must_be_true"):
        lines.append("# Which was taken to mean:")
        lines += [f"#   - {claim}" for claim in design["must_be_true"]]
        lines.append("")

    for number, step in enumerate(transcript.steps, start=1):
        arguments = ", ".join(f"{name}={value!r}"
                              for name, value in step.arguments.items())
        lines.append(f"# step {number}")
        lines.append(f"{step.name}({arguments})")
        if step.error:
            lines.append(f"#   refused: {step.error}")
            lines.append("")
            continue
        for solid in (step.result or {}).get("part_now") or []:
            lines.append(
                f"#   -> {solid['label']}: "
                + " x ".join(f"{v:g}" for v in solid["size_mm"])
                + f" mm, {solid['volume_mm3']:,.0f} mm3, "
                + f"{solid['faces']} faces, "
                + ("watertight" if solid["watertight"] else "NOT watertight"))
        lines.append("")

    if transcript.answer:
        lines += ["# The builder's own account of it:",
                  *[f"#   {line}" for line in transcript.answer.splitlines()]]
    if transcript.stopped and transcript.stopped != "finished":
        lines.append(f"# The loop stopped early: {transcript.stopped}")
    return "\n".join(lines) + "\n"


def facts(step: Path) -> dict:
    """The solid's own numbers, in the shape the Model panel reads.

    The same fields the pipeline's executor writes into ``geometry.json``,
    measured here off the STEP that came back from FreeCAD rather than
    trusting FreeCAD's own report of it.
    """
    import cadquery as cq

    solid = cq.importers.importStep(str(step)).val()
    box = solid.BoundingBox()
    return {
        "volume": solid.Volume(),
        "center_of_mass": solid.Center().toTuple(),
        "bounding_box": {
            "xmin": box.xmin, "xmax": box.xmax, "xlen": box.xlen,
            "ymin": box.ymin, "ymax": box.ymax, "ylen": box.ylen,
            "zmin": box.zmin, "zmax": box.zmax, "zlen": box.zlen,
        },
        "is_valid": solid.isValid(),
        "num_faces": len(solid.Faces()),
        "num_edges": len(solid.Edges()),
        "num_vertices": len(solid.Vertices()),
        "is_assembly": False,
        "components": [],
    }


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------

def serve(ctx: RunContext, prompt: str, client: Any, model: str,
          bridge: Optional[freecad.Bridge] = None,
          max_steps: int = builder.MAX_STEPS) -> dict:
    """Plan it, build it in FreeCAD, measure it, and publish the version.

    Raises if FreeCAD will not build it, which the caller treats the way it
    treats a catalogue part that will not build here: by falling through to
    the pipeline. A part that came out wrong is not a failure of this kind -
    it is published, with the measurements that say so, exactly as a
    generated part would be.
    """
    bridge = bridge or bridge_from_env()
    lang = ctx.lang
    ctx.source = "freecad"
    ctx.method = "tools"
    started = time.time()

    # One budget, counted here. The build loop reports its own tokens and
    # the planning call reports its own; the pipeline's module-level
    # counters never see this road, so nothing else is keeping the tally.
    usage = {"input_tokens": 0, "output_tokens": 0, "calls": 0}

    def charge(spent: dict) -> None:
        for key, value in spent.items():
            usage[key] = usage.get(key, 0) + int(value)

    ctx.agent = "planner"
    ctx.emit(PHASE_PLAN, STATUS_STARTED, i18n.t("freecad.planning", lang))
    design = builder.plan(prompt, client, model, on_usage=charge)
    panel = builder.for_panel(design)
    ctx.design_plan = panel
    ctx.emit(PHASE_PLAN, STATUS_OK, i18n.t("freecad.planned", lang,
                                           n=len(design.get("components") or [])),
             design_plan=panel, tokens=dict(usage))

    ctx.agent = "builder"
    ctx.emit(PHASE_CODE, STATUS_STARTED,
             i18n.t("freecad.building", lang), tokens=dict(usage))

    def step_done(step: Any) -> None:
        """Say what just happened, while it is still happening.

        The point of the road is that the part arrives feature by feature,
        so each one is announced as FreeCAD finishes it rather than the
        whole build appearing at the end.
        """
        ctx.emit(PHASE_FREECAD, STATUS_FAILED if step.error else STATUS_OK,
                 (i18n.t("freecad.refused", lang, tool=step.name,
                         error=step.error) if step.error
                  else i18n.t("freecad.step", lang, tool=step.name,
                              ms=step.ms)),
                 iteration=ctx.iteration, step=step.summary())

    def still_going(transcript: Any) -> str:
        """Whether the next model call is within this run's ceiling."""
        if ctx.budget is None:
            return ""
        running = {"input_tokens": usage["input_tokens"] + transcript.input_tokens,
                   "output_tokens": usage["output_tokens"] + transcript.output_tokens,
                   "calls": usage["calls"] + transcript.calls}
        try:
            ctx.budget.check(running)
        except Exception as stopped:
            return str(stopped)
        return ""

    session, transcript = builder.build(
        bridge, prompt, client, model, design, on_step=step_done,
        max_steps=max_steps, before_call=still_going)
    charge({"input_tokens": transcript.input_tokens,
            "output_tokens": transcript.output_tokens,
            "calls": transcript.calls})

    code = transcript_text(prompt, design, transcript)
    version_dir = ctx.version_dir()
    (version_dir / "code.py").write_text(code, encoding="utf-8")
    ctx.emit(PHASE_CODE, STATUS_OK,
             i18n.t("freecad.built", lang, n=len(transcript.steps)),
             code=code, lines=len(code.splitlines()),
             iteration=ctx.iteration, tokens=dict(usage),
             transcript=transcript.summary())

    version = publish(ctx, session, prompt, design, bridge,
                      tokens=usage,
                      answer=transcript.answer,
                      detail={
                          "document": session.document,
                          "steps": len(transcript.steps),
                          "calls": transcript.calls,
                          "improvised": transcript.improvised,
                          "stopped": transcript.stopped,
                          "answer": transcript.answer,
                      })
    ctx.emit(PHASE_FREECAD, STATUS_INFO,
             i18n.t("freecad.done", lang,
                    ms=f"{(time.time() - started) * 1000:.0f}",
                    steps=len(transcript.steps)),
             tokens=dict(usage))
    return version


def publish(ctx: RunContext, session: freecad_tools.Session, prompt: str,
            design: dict, bridge: freecad.Bridge, tokens: dict,
            answer: str = "", detail: Optional[dict] = None,
            source: str = "freecad", method: str = "tools",
            instruction: str = "",
            changes: Optional[list] = None) -> dict:
    """Bring the part out of FreeCAD, measure it, and announce the version.

    Shared by a fresh build and a parameter change, because the two differ
    only in how the document got into the state it is in. Everything after
    that - the export, the measurement, the gate, the slider map, the drawing
    - has to be identical, or a dragged parameter would be checked more
    loosely than the build that preceded it.
    """
    lang = ctx.lang
    version_dir = ctx.version_dir()

    # Out of FreeCAD and into this app's own hands. Everything from here on
    # is measured here, on the solid that travelled, rather than taken on
    # FreeCAD's word for it.
    ctx.emit(PHASE_EXECUTE, STATUS_STARTED, i18n.t("freecad.exporting", lang))
    files = builder.collect(session, version_dir)
    geometry = facts(files["step"])
    (version_dir / "geometry.json").write_text(
        json.dumps(geometry, indent=2), encoding="utf-8")
    ctx.emit(PHASE_EXECUTE, STATUS_OK,
             i18n.t("freecad.exported", lang,
                    volume=f"{geometry['volume']:,.0f}"),
             iteration=ctx.iteration, geometry=geometry)

    # What a person can drag afterwards, named by the builder as it went.
    # Written beside the geometry rather than kept in memory: the next drag
    # may arrive after a restart, and it has to reach the same properties.
    mapping = builder.parameter_map(session)
    (version_dir / "parameters.json").write_text(json.dumps({
        "document": session.document,
        "document_file": (files["document"].name
                          if "document" in files else ""),
        "parameters": mapping,
    }, indent=2), encoding="utf-8")

    _screenshot(bridge, version_dir)

    verdict = builder.check(files["step"], prompt, design)
    (version_dir / "validation.json").write_text(json.dumps({
        "source": source,
        "all_passed": verdict["passed"],
        "checks": [
            {"metric": row["key"], "passed": row["passed"],
             "message": f"{row['label']}: {row['actual']}"}
            for row in verdict["checks"]
        ] + [{"metric": "llm_judge", "passed": None,
              "message": "No Judge: the gate here is the kernel's measurement."}],
        "must_be_true": design.get("must_be_true") or [],
        "feedback_text": "",
    }, indent=2), encoding="utf-8")
    ctx.emit(PHASE_SPEC, STATUS_OK if verdict["passed"] else STATUS_FAILED,
             i18n.t("freecad.passed" if verdict["passed"] else "freecad.failed",
                    lang, problems="; ".join(verdict["problems"])),
             iteration=ctx.iteration, spec=verdict)

    version = {
        "iteration": ctx.iteration,
        "passed": verdict["passed"],
        # No Judge ran, so there is no verdict to report. None is what the
        # Validation panel reads to say so rather than crediting one.
        "judge_passed": None,
        "judge_feedback": "",
        "feedback_text": answer,
        "geometry": geometry,
        "has_render": (version_dir / "render.png").exists(),
        "source": source,
        "method": method,
        "instruction": instruction,
        "changes": list(changes or []),
        "spec": verdict,
        "freecad": {
            **(detail or {}),
            "document": session.document,
            "parameters": [entry["name"] for entry in mapping],
            "document_file": (files["document"].name
                              if "document" in files else ""),
        },
        "tokens": dict(tokens),
    }
    ctx.versions.append(version)
    ctx.emit(PHASE_VERSION, STATUS_OK, **version)

    drawing.prebuild(version_dir, ctx.prompt or prompt,
                     ctx.job_dir.name, ctx.iteration)
    return version


# ---------------------------------------------------------------------------
# Dragging a number on a part that is already built
# ---------------------------------------------------------------------------

def declared_from(record: dict) -> list[dict]:
    """The slider map as the session that built it held it.

    ``parameters.json`` carries the panel's fields as well, which a session
    has no use for - what it needs is which object and property each name
    stands for.
    """
    return [{"name": entry["name"], "label": entry["label"],
             "object": entry["object"], "property": entry["property"],
             "scale": float(entry.get("scale") or 1.0)}
            for entry in (record.get("parameters") or [])
            if entry.get("object") and entry.get("property")]


def reapply(ctx: RunContext, base_dir: Path, values: dict, prompt: str,
            design: Optional[dict] = None,
            bridge: Optional[freecad.Bridge] = None) -> dict:
    """Set declared parameters on a saved version and publish the result.

    This is the whole reason the FreeCAD road is worth the trouble. A
    CadQuery part has its script rewritten and re-executed from the top for
    one changed number; here the version's own document is reopened, one
    property is set, and FreeCAD recomputes what depends on it.

    The version it was dragged from is reopened by file, so going back in the
    filmstrip and dragging there changes *that* part - not whichever document
    happens to still be open in FreeCAD.
    """
    bridge = bridge or bridge_from_env()
    record = json.loads((base_dir / "parameters.json").read_text(
        encoding="utf-8"))
    mapping = record.get("parameters") or []
    if not mapping:
        raise freecad.FreeCADError(
            f"{base_dir.name} declared no parameters to change")

    document_file = base_dir / (record.get("document_file") or "part.FCStd")
    if not document_file.exists():
        raise freecad.FreeCADError(
            "that version's FreeCAD document was not saved, so there is "
            "nothing to reopen and change")

    name = builder.reopen(bridge, document_file)
    session = freecad_tools.Session(bridge, name)
    session.declared = declared_from(record)

    before = {entry["name"]: entry["value"] for entry in mapping}
    changed = builder.apply_parameters(bridge, name, mapping, values)
    if not changed:
        raise freecad.FreeCADError(
            "none of those names is a parameter of this part: "
            + ", ".join(sorted(entry["name"] for entry in mapping)))
    ctx.emit(PHASE_FREECAD, STATUS_OK,
             i18n.t("freecad.dragged", ctx.lang, changes="; ".join(changed)),
             iteration=ctx.iteration, document=name)

    return publish(
        ctx, session, prompt, design or {}, bridge,
        tokens={"input_tokens": 0, "output_tokens": 0, "calls": 0},
        source="edit", method="freecad parameters",
        instruction="; ".join(changed),
        changes=[{"name": key, "old": before.get(key), "new": float(value)}
                 for key, value in values.items() if key in before],
        detail={"document": name, "from_version": base_dir.name,
                "steps": 0, "calls": 0})


def _screenshot(bridge: freecad.Bridge, version_dir: Path) -> None:
    """FreeCAD's own viewport, if it has one to give.

    Best effort and deliberately so. It is the Judge's image slot, and a
    FreeCAD started without a GUI has no viewport to photograph - which is a
    perfectly good way to run this and not a reason to fail a build.
    """
    try:
        (version_dir / "render.png").write_bytes(bridge.screenshot())
    except Exception:
        pass
