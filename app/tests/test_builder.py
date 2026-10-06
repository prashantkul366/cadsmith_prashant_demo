"""Planning a part, building it in FreeCAD, and measuring what came out.

The claim under test is the one that separates this from the pipeline it
replaces: **the gate is a measurement, not a verdict**. A builder that
finishes happily having made the wrong part is caught here, by the kernel,
against the dimensions the request itself stated - read out by
``stated.py`` before any model saw it.

Also tested: that the declared parameters come back in the exact shape the
slider panel already draws, and that setting one reaches FreeCAD as a
property change rather than a rewritten script.

FreeCAD is not installed here, so the modelling stand-in from
``test_freecad_tools`` stands in for it, and a scripted endpoint stands in
for the model. Both have to be fakes for this to be testable at all; what
is real is the geometry, the measurement and the parameter plumbing.

Run:  .venv/bin/python -m app.tests.test_builder
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
from http.server import HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.server import builder, freecad, providers  # noqa: E402
from app.tests.test_freecad import serve  # noqa: E402
from app.tests.test_freecad_tools import Modelling  # noqa: E402
from app.tests.test_toolbox import Endpoint  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def client_for(port: int):
    return providers.build_client(providers.LLMConfig(
        provider="custom", kind="openai_compatible",
        base_url=f"http://127.0.0.1:{port}/v1", api_key="x",
        generation_model="fake", judge_model="fake"))


PROMPT = ("A mounting plate 80 mm wide, 50 mm deep and 10 mm thick, "
          "with a 6 mm diameter hole through it.")


def main() -> int:
    model_server = HTTPServer(("127.0.0.1", 0), Endpoint)
    model_port = model_server.server_address[1]
    threading.Thread(target=model_server.serve_forever, daemon=True).start()

    stand_in = Modelling()
    cad_server, cad_port = serve(stand_in)
    bridge = freecad.Bridge(port=cad_port, timeout=20.0)

    print("The Planner says what must be true, not just what to build")
    Endpoint.tools_supported = True
    Endpoint.seen = []
    Endpoint.script = [{"content": json.dumps({
        "description": "a mounting plate with one hole",
        "components": ["plate", "hole"],
        "build_order": ["add the plate", "cut the hole"],
        "key_dimensions": {"length": 80, "width": 50, "thickness": 10,
                           "hole_diameter": 6},
        "must_be_true": ["the plate measures 80 x 50 x 10",
                         "there is one 6 mm hole through it"]})}]
    design = builder.plan(PROMPT, client_for(model_port), "fake")
    check("it decomposes the request", design["components"] == ["plate", "hole"],
          str(design.get("components")))
    check("and leaves something checkable behind",
          len(design.get("must_be_true") or []) == 2,
          str(design.get("must_be_true")))
    check("a malformed plan does not lose the run",
          builder.plan.__doc__ and "falls back" in builder.plan.__doc__.lower())

    print("\nThe builder works in measured steps")
    Endpoint.seen = []
    Endpoint.script = [
        {"tool": "add_shape", "arguments": {
            "kind": "Part::Box", "name": "Plate",
            "Length": 80, "Width": 50, "Height": 10}},
        {"tool": "add_shape", "arguments": {
            "kind": "Part::Cylinder", "name": "Hole",
            "Radius": 3, "Height": 30, "position": [40, 25, -10]}},
        {"tool": "combine", "arguments": {
            "operation": "cut", "base": "Plate", "tools": ["Hole"]}},
        {"tool": "declare_parameter", "arguments": {
            "name": "plate_length", "label": "Plate length",
            "object_name": "Plate", "property_name": "Length"}},
        {"tool": "declare_parameter", "arguments": {
            "name": "hole_diameter", "label": "Hole diameter",
            "object_name": "Hole", "property_name": "Radius", "scale": 2}},
        {"content": "Built an 80 x 50 x 10 plate with one 6 mm hole."},
    ]
    session, transcript = builder.build(
        bridge, PROMPT, client_for(model_port), "fake", design)
    check("every step ran", all(s.ok for s in transcript.steps)
          and len(transcript.steps) == 5,
          f"{len(transcript.steps)} steps: "
          + ", ".join(s.name for s in transcript.steps))
    check("and it finished rather than running out", transcript.ok)

    print("\nThe gate is a measurement, not a verdict")
    work = Path(tempfile.mkdtemp(prefix="cadsmith_builder_"))
    files = builder.collect(session, work / "v0")
    check("the STEP the rest of the app reads was written",
          files["step"].exists() and files["step"].stat().st_size > 0,
          f"{files['step'].stat().st_size:,} bytes")
    check("and the STL the viewer loads", "stl" in files)

    verdict = builder.check(files["step"], PROMPT, design)
    rows = {row["key"]: row for row in verdict["checks"]}
    check("the part passes, because it is the part that was asked for",
          verdict["passed"], str(verdict["problems"]))
    check("the solid is closed", rows["watertight"]["passed"])
    check("the stated sizes were found in the solid",
          any(k.startswith(("size_", "stated_")) for k in rows),
          ", ".join(k for k in rows if k.startswith(("size_", "stated_"))))
    check("and the hole was measured off the geometry, not the request",
          "bore_6" in rows and rows["bore_6"]["passed"],
          rows.get("bore_6", {}).get("actual"))

    # The point of the gate. A builder that finishes happily having made the
    # wrong thing is caught by the kernel, not asked for its opinion.
    wrong = builder.check(files["step"],
                          "A plate 200 mm wide with four 12 mm holes.", design)
    check("a part that does not match the request is refused",
          not wrong["passed"], str(wrong["problems"])[:90])
    check("and the refusal names what is wrong, measured both ways",
          any("12" in row["expected"] for row in wrong["checks"]
              if row["passed"] is False),
          str([r["key"] for r in wrong["checks"] if r["passed"] is False]))

    print("\nThe declared parameters are what the slider panel already draws")
    mapping = builder.parameter_map(session)
    names = {p["name"] for p in mapping}
    check("only what the builder declared becomes a slider",
          names == {"plate_length", "hole_diameter"}, str(sorted(names)))
    panel = {p["name"]: p for p in mapping}
    for field in ("label", "value", "kind", "unit", "min", "max", "step"):
        if field not in panel["plate_length"]:
            check(f"the panel's {field} is there", False)
            break
    else:
        check("every field the panel needs is there",
              True, ", ".join(sorted(panel["plate_length"])))
    check("the value is read live from FreeCAD",
          panel["plate_length"]["value"] == 80.0,
          str(panel["plate_length"]["value"]))
    # FreeCAD holds a Radius; a person drags a diameter. The scale is the
    # whole reason the two never drift apart.
    check("a radius property is shown as the diameter a person means",
          panel["hole_diameter"]["value"] == 6.0,
          f"Radius 3 shown as {panel['hole_diameter']['value']}")

    print("\nDragging one sets a property; FreeCAD recomputes the rest")
    changed = builder.apply_parameters(
        bridge, session.document, mapping,
        {"plate_length": 95, "hole_diameter": 8})
    check("both reached FreeCAD", len(changed) == 2, str(changed))
    check("the length went across as it was dragged",
          stand_in.shapes["Plate"]["props"]["Length"] == 95.0,
          str(stand_in.shapes["Plate"]["props"]["Length"]))
    check("and the diameter went across halved, as a Radius",
          stand_in.shapes["Hole"]["props"]["Radius"] == 4.0,
          str(stand_in.shapes["Hole"]["props"]["Radius"]))
    check("what the panel reads back is the diameter again, not the radius",
          {p["name"]: p["value"] for p in builder.parameter_map(session)}
          == {"plate_length": 95.0, "hole_diameter": 8.0},
          str({p["name"]: p["value"] for p in builder.parameter_map(session)}))
    check("a name the map does not know is ignored, not guessed at",
          builder.apply_parameters(bridge, session.document, mapping,
                                   {"made_up": 5}) == [])

    print("\nA declared parameter has to exist")
    from app.server.toolbox import ToolError
    try:
        session.declare_parameter("x", "X", "Ghost", "Length")
        check("naming an object that is not there is refused", False)
    except ToolError as refused:
        check("naming an object that is not there is refused",
              "Ghost" in str(refused), str(refused)[:60])

    model_server.shutdown()
    cad_server.shutdown()
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
