"""A prompt, built in FreeCAD, as the app's own job sees it.

What this covers is the seam, which is the part that could quietly be wrong
while every piece either side of it passes its own test: the version
directory, the event stream, and the record the browser reads. If the
viewer's ``model.stl`` is missing, or the Validation panel is handed a
version that claims a Judge ran, or the slider map does not survive being
written to disk and read back, this is where it shows.

Then the second half, which is the reason the FreeCAD road exists: dragging
a parameter on a part that is already built reopens *that version's own
document*, sets one property, and publishes what FreeCAD recomputed. No
script is rewritten and nothing is executed from the top.

FreeCAD is not installed here, so the modelling stand-in from
``test_freecad_tools`` answers for it and a scripted endpoint answers for
the model. The geometry, the measurements and the files are real.

Run:  .venv/bin/python -m app.tests.test_freecad_run
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
from http.server import HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.server import freecad, freecad_run, providers  # noqa: E402
from app.server.events import EventSink  # noqa: E402
from app.server.instrument import RunContext  # noqa: E402
from app.tests.test_freecad import serve  # noqa: E402
from app.tests.test_freecad_tools import Modelling  # noqa: E402
from app.tests.test_toolbox import Endpoint  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


PROMPT = ("A mounting plate 80 mm wide, 50 mm deep and 10 mm thick, "
          "with a 6 mm diameter hole through it.")

PLAN = {"description": "a mounting plate with one hole",
        "components": ["plate", "hole"],
        "build_order": ["add the plate", "cut the hole"],
        "key_dimensions": {"length": 80, "width": 50, "thickness": 10,
                           "hole_diameter": 6},
        "must_be_true": ["the plate measures 80 x 50 x 10",
                         "there is one 6 mm hole through it"]}

BUILD = [
    {"content": json.dumps(PLAN)},
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


def main() -> int:
    model_server = HTTPServer(("127.0.0.1", 0), Endpoint)
    model_port = model_server.server_address[1]
    threading.Thread(target=model_server.serve_forever, daemon=True).start()
    client = providers.build_client(providers.LLMConfig(
        provider="custom", kind="openai_compatible",
        base_url=f"http://127.0.0.1:{model_port}/v1", api_key="x",
        generation_model="fake", judge_model="fake"))

    stand_in = Modelling()
    cad_server, cad_port = serve(stand_in)
    bridge = freecad.Bridge(port=cad_port, timeout=20.0)

    job_dir = Path(tempfile.mkdtemp(prefix="cadsmith_run_"))
    sink = EventSink(path=job_dir / "events.jsonl")
    ctx = RunContext(sink=sink, job_dir=job_dir, part_name="part",
                     prompt=PROMPT)

    print("A FreeCAD that is not running is an ordinary state")
    check("it reads as unavailable rather than raising",
          freecad_run.available(freecad.Bridge(port=1, timeout=2.0)) is False)
    check("and a running one is found", freecad_run.available(bridge))

    print("\nOne prompt, built in FreeCAD")
    Endpoint.tools_supported = True
    Endpoint.seen = []
    Endpoint.script = list(BUILD)
    version = freecad_run.serve(ctx, PROMPT, client, "fake", bridge=bridge)

    v0 = job_dir / "v0"
    for name in ("model.step", "model.stl", "code.py", "geometry.json",
                 "parameters.json", "validation.json", "part.FCStd"):
        check(f"the version carries its {name}",
              (v0 / name).exists() and (v0 / name).stat().st_size > 0,
              f"{(v0 / name).stat().st_size:,} bytes"
              if (v0 / name).exists() else "missing")

    print("\nThe record is the one the browser already reads")
    check("the viewer's numbers are in the shape the Model panel draws",
          set(version["geometry"]) >= {"bounding_box", "volume", "num_faces",
                                       "num_edges", "is_valid"},
          ", ".join(sorted(version["geometry"])[:5]))
    check("the plate measures what was asked for",
          abs(version["geometry"]["bounding_box"]["xlen"] - 80) < 0.01,
          f"{version['geometry']['bounding_box']['xlen']:.2f} mm")
    check("it is stamped as built in FreeCAD, not generated",
          version["source"] == "freecad" and version["method"] == "tools",
          f"{version['source']} / {version['method']}")
    # The panel reads judge_passed to decide whether to credit a Judge. A
    # part no Judge saw must not arrive carrying a verdict.
    check("and carries no Judge verdict, because no Judge ran",
          version["judge_passed"] is None)
    check("the measured rows came with it", version["spec"]["checks"]
          and version["passed"], str(version["spec"]["problems"]))
    check("the FreeCAD document is named as a deliverable",
          version["freecad"]["document_file"] == "part.FCStd",
          version["freecad"]["document_file"])

    print("\nThe build was watchable while it happened")
    events = [(e.phase, e.status, e.message) for e in sink.all()]
    steps = [e for e in events if e[0] == "freecad" and e[1] == "ok"]
    check("every tool call was announced as it finished",
          len(steps) >= 5,
          f"{len(steps)} announced, {version['freecad']['steps']} taken")
    check("the plan went out before the building started",
          [e[0] for e in events].index("plan")
          < [e[0] for e in events].index("code"))
    check("the Code panel was given something to show",
          any(e.phase == "code" and e.data.get("code") for e in sink.all()))
    check("and the version was published last",
          [e[0] for e in events if e[0] in ("plan", "code", "execute",
                                            "version")][-1] == "version")

    print("\nThe transcript says what was built, and does not pretend to run")
    code = (v0 / "code.py").read_text(encoding="utf-8")
    check("it names every step", code.count("# step") == 5,
          f"{code.count('# step')} steps")
    check("it says it is a record rather than a script",
          "not a script that would reproduce it" in code)
    check("it points at the document that is the real deliverable",
          "part.FCStd" in code)
    check("and it carries the measurements, which is what makes it readable",
          "watertight" in code and "mm3" in code)

    print("\nThe slider map survives being written down")
    record = json.loads((v0 / "parameters.json").read_text(encoding="utf-8"))
    by_name = {entry["name"]: entry for entry in record["parameters"]}
    check("both declared parameters are in it",
          set(by_name) == {"plate_length", "hole_diameter"},
          ", ".join(sorted(by_name)))
    check("each says which FreeCAD property it stands for",
          by_name["hole_diameter"]["object"] == "Hole"
          and by_name["hole_diameter"]["property"] == "Radius",
          f"{by_name['hole_diameter']['object']}."
          f"{by_name['hole_diameter']['property']}")
    check("the diameter is shown as a diameter, not as the radius stored",
          by_name["hole_diameter"]["value"] == 6.0
          and by_name["hole_diameter"]["scale"] == 2.0,
          str(by_name["hole_diameter"]["value"]))

    print("\nDragging one reopens that version's document and sets a property")
    before = len(stand_in.calls)
    model_calls = len(Endpoint.seen)
    ctx.iteration = 1
    changed = freecad_run.reapply(ctx, v0, {"plate_length": 95}, PROMPT,
                                  design=PLAN, bridge=bridge)
    check("no model was called to do it",
          len(Endpoint.seen) == model_calls,
          f"{len(Endpoint.seen) - model_calls} model call(s) during the drag")
    check("the property was set on the object the map named",
          stand_in.shapes["Plate"]["props"]["Length"] == 95.0,
          str(stand_in.shapes["Plate"]["props"]["Length"]))
    check("the document was reopened rather than guessed at",
          any("listDocuments" in str(call[1])
              for call in stand_in.calls[before:] if call[0] == "execute_code"))

    print("\nAnd the result is a version like any other")
    v1 = job_dir / "v1"
    check("it has its own geometry, measured again",
          abs(changed["geometry"]["bounding_box"]["xlen"] - 95) < 0.01,
          f"{changed['geometry']['bounding_box']['xlen']:.2f} mm")
    check("its own document, so this one can be dragged from too",
          (v1 / "part.FCStd").exists() and (v1 / "parameters.json").exists())
    check("the gate ran again, which is the point of a measured edit",
          changed["spec"]["checks"] and changed["passed"] is not None,
          str(changed["spec"]["problems"]))
    # 95 was not what the request said, so the stated check should now
    # disagree - measured, not assumed.
    rows = {row["key"]: row for row in changed["spec"]["checks"]}
    check("and it notices the part no longer matches the request",
          rows["stated_adv_80"]["passed"] is False,
          f"{rows['stated_adv_80']['actual']} against "
          f"{rows['stated_adv_80']['expected']}")
    check("it reads as an edit, with what was changed",
          changed["source"] == "edit"
          and changed["changes"][0]["new"] == 95.0,
          f"{changed['source']}: {changed['changes']}")

    print("\nAsking for a change in words works on the same document")
    Endpoint.seen = []
    Endpoint.script = [
        {"tool": "find_features", "arguments": {}},
        {"tool": "resize_hole", "arguments": {
            "feature_id": "hole_6", "diameter": 11}},
        {"content": "Opened the hole out to 11 mm."},
    ]
    ctx.iteration = 2
    amended = freecad_run.amend(ctx, v1, "open the hole out to 11 mm",
                                client, "fake", PROMPT, design=PLAN,
                                bridge=bridge)
    check("it reopened the version it was asked to change, not the newest",
          amended["freecad"]["from_version"] == "v1",
          amended["freecad"]["from_version"])
    check("the feature it worked on was found off the solid, not guessed",
          any(e.data.get("step", {}).get("tool") == "find_features"
              for e in sink.all() if e.phase == "freecad"))
    check("the hole it changed is the size that was asked for",
          any(abs(d - 11.0) < 0.1 for d in
              freecad_run.builder.spec.measure_step(
                  job_dir / "v2" / "model.step")["holes"]),
          str(freecad_run.builder.spec.measure_step(
              job_dir / "v2" / "model.step")["holes"]))
    check("the rest of the part survived the change",
          abs(amended["geometry"]["bounding_box"]["xlen"] - 95) < 0.01,
          f"{amended['geometry']['bounding_box']['xlen']:.2f} mm")
    check("it is filed as an edit, with the words that asked for it",
          amended["source"] == "edit"
          and amended["instruction"] == "open the hole out to 11 mm",
          f"{amended['source']}: {amended['instruction']}")
    # The trade a direct feature edit makes, and the one thing about this
    # road a person has to be told rather than left to discover. Recognising
    # a hole off the topology is the only way to change geometry that has no
    # tree behind it, and it hands back a plain solid - so the tree, and the
    # sliders over it, are gone.
    check("the sliders are gone, because the tree they named is",
          amended["freecad"]["parameters"] == [],
          str(amended["freecad"]["parameters"]))
    check("and that was said rather than left to be noticed",
          any(e.phase == "freecad" and e.data.get("lost")
              for e in sink.all()),
          str([e.data.get("lost") for e in sink.all()
               if e.data.get("lost")]))

    print("\nA change that was not made is not published as one")
    Endpoint.seen = []
    Endpoint.script = [{"content": "I would rather not."}]
    ctx.iteration = 3
    try:
        freecad_run.amend(ctx, v1, "paint it red", client, "fake", PROMPT,
                          bridge=bridge)
        check("a model that does nothing is refused, not published", False)
    except freecad.FreeCADError as refused:
        check("a model that does nothing is refused, not published",
              "nothing in the part changed" in str(refused), str(refused)[:70])
    check("and no version was left behind for it",
          not (job_dir / "v3" / "model.step").exists())

    # The one that matters, and the one that was wrong. A model can call
    # tools, be refused by every one of them, announce success, and leave
    # the part exactly as it found it. Measured on an 8B: nineteen refused
    # set_size calls and a version published as an edit.
    Endpoint.seen = []
    Endpoint.script = [
        {"tool": "set_size", "arguments": {"name": "Ghost", "Length": 99}},
        {"tool": "set_size", "arguments": {"name": "Ghost", "Width": 99}},
        {"content": "Made it 99 mm long."},
    ]
    ctx.iteration = 3
    try:
        freecad_run.amend(ctx, v1, "make it 99 long", client, "fake", PROMPT,
                          bridge=bridge)
        check("calls that all failed are not an edit, whatever was said",
              False, "it published a version")
    except freecad.FreeCADError as refused:
        check("calls that all failed are not an edit, whatever was said",
              "nothing in the part changed" in str(refused), str(refused)[:70])
    check("and the refusal carries the last thing that was tried",
          not (job_dir / "v3" / "model.step").exists())

    print("\nWorking in a document the engineer already had open")
    # The difference between a generator and an assistant. Their part is
    # published untouched first, so stepping back goes back to their work.
    engineers = version["freecad"]["document"]
    listed = freecad_run.open_documents(bridge)
    check("what FreeCAD has open can be listed, with what it holds",
          any(d["name"] == engineers and d["objects"] for d in listed),
          ", ".join(f"{d['name']} ({d['objects']} obj)" for d in listed))
    check("and a document with a part in it is recognised as holding one",
          freecad_run.holds_a_part(bridge, engineers))

    Endpoint.seen = []
    Endpoint.script = [
        {"tool": "find_features", "arguments": {}},
        {"tool": "add_shape", "arguments": {
            "kind": "Part::Cylinder", "name": "Pin",
            "Radius": 4, "Height": 40, "position": [20, 25, -5]}},
        {"content": "Added a 8 mm pin boss."},
    ]
    theirs = Path(tempfile.mkdtemp(prefix="cadsmith_theirs_"))
    sink2 = EventSink(path=theirs / "events.jsonl")
    ctx2 = RunContext(sink=sink2, job_dir=theirs, part_name="part",
                      prompt="add a pin boss")
    after = freecad_run.serve(ctx2, "add a pin boss", client, "fake",
                              bridge=bridge, document=engineers)
    check("their part was published before anything touched it",
          (theirs / "v0" / "model.step").exists()
          and ctx2.versions[0]["method"] == "as found",
          ctx2.versions[0]["method"])
    check("and the version after it is the change",
          after["iteration"] == 1 and after["source"] == "edit",
          f"v{after['iteration']} {after['source']}/{after['method']}")
    check("the run says which document it worked in",
          after["freecad"]["attached"] is True
          and after["freecad"]["document"] == engineers,
          after["freecad"]["document"])
    check("their document was saved as found, so going back is their part",
          (theirs / "v0" / "part.FCStd").exists())
    check("nothing was built from nothing - no plan was asked for",
          not any(e.phase == "plan" for e in sink2.all()),
          ", ".join(sorted({e.phase for e in sink2.all()})))

    print("\nWhat cannot be done is refused, not half done")
    try:
        freecad_run.reapply(ctx, v0, {"made_up": 5}, PROMPT, bridge=bridge)
        check("a name the part does not declare is refused", False)
    except freecad.FreeCADError as refused:
        check("a name the part does not declare is refused",
              "is a parameter of this part" in str(refused),
              str(refused)[:70])
    bare = job_dir / "bare"
    bare.mkdir()
    (bare / "parameters.json").write_text(json.dumps({"parameters": []}),
                                          encoding="utf-8")
    try:
        freecad_run.reapply(ctx, bare, {"x": 1}, PROMPT, bridge=bridge)
        check("a version with nothing declared is refused", False)
    except freecad.FreeCADError as refused:
        check("a version with nothing declared is refused",
              "no parameters" in str(refused), str(refused)[:70])

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
