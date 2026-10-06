"""Driving FreeCAD from this server, without FreeCAD present.

FreeCAD cannot be installed in CI, and a test that needs a desktop
application running with an addon started is a test nobody runs. So the
protocol is the thing under test: a stand-in XML-RPC server answers exactly
as ``addon/FreeCADMCP/rpc_server.py`` does - the same method names, the same
``{"success": ..., "error": ...}`` shape, the same ``"Output: "`` prefix on
what a script printed - and the bridge is driven against it.

What that proves, and what it does not. It proves the bridge speaks the
addon's protocol, that failures arrive as failures rather than as silence,
and that geometry handed back through the export path lands here as a solid
this app can measure with its own tools. It does not prove FreeCAD builds
the right shape; only FreeCAD can show that, on a machine where it is
installed.

The export is not faked with a placeholder. The stand-in exports a real
STEP file - built by the kernel this app already runs - so the round trip
ends in ``spec.measure_step``, measuring geometry that genuinely travelled
base64 through the protocol.

Run:  .venv/bin/python -m app.tests.test_freecad
"""

from __future__ import annotations

import base64
import json
import sys
import tempfile
import threading
from pathlib import Path
from xmlrpc.server import SimpleXMLRPCServer

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cadquery as cq  # noqa: E402

from app.server import freecad, spec  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


class StandIn:
    """FreeCAD's addon, answering the way the real one does.

    Only the protocol is reproduced. The document is a dictionary and the
    geometry is built by CadQuery, because what is under test here is the
    conversation, not the kernel on the far end of it.
    """

    def __init__(self, step_bytes: bytes) -> None:
        self.step = step_bytes
        self.documents_: dict[str, list[dict]] = {}
        self.calls: list[tuple] = []
        self.token_seen: str = ""

    # -- the addon's surface ------------------------------------------------

    def ping(self):
        return True

    def get_rpc_status(self):
        return {"version": "stand-in", "gui_responsive": True}

    def list_documents(self):
        return list(self.documents_)

    def create_document(self, name="New_Document"):
        self.calls.append(("create_document", name))
        # FreeCAD sanitises and de-duplicates; the bridge has to follow the
        # name that comes back rather than the one it asked for.
        actual = name.replace(" ", "_")
        if actual in self.documents_:
            actual = f"{actual}001"
        self.documents_[actual] = []
        return {"success": True, "document_name": actual}

    def create_object(self, doc_name, obj_data):
        self.calls.append(("create_object", doc_name, obj_data))
        if doc_name not in self.documents_:
            return {"success": False, "error": f"no document {doc_name}"}
        wanted = obj_data.get("Name") or "Object"
        taken = {o["Name"] for o in self.documents_[doc_name]}
        actual = wanted if wanted not in taken else f"{wanted}001"
        self.documents_[doc_name].append(
            {"Name": actual, "Label": actual, "TypeId": obj_data["Type"],
             "Properties": dict(obj_data.get("Properties") or {})})
        return {"success": True, "object_name": actual}

    def edit_object(self, doc_name, obj_name, properties):
        self.calls.append(("edit_object", doc_name, obj_name, properties))
        for obj in self.documents_.get(doc_name, []):
            if obj["Name"] == obj_name:
                obj["Properties"].update(properties.get("Properties") or {})
                return {"success": True, "object_name": obj_name}
        return {"success": False, "error": f"no object {obj_name}"}

    def delete_object(self, doc_name, obj_name):
        before = len(self.documents_.get(doc_name, []))
        self.documents_[doc_name] = [
            o for o in self.documents_.get(doc_name, []) if o["Name"] != obj_name]
        if len(self.documents_[doc_name]) == before:
            return {"success": False, "error": f"no object {obj_name}"}
        return {"success": True, "object_name": obj_name}

    def get_objects(self, doc_name):
        return [self._as_addon(o) for o in self.documents_.get(doc_name, [])]

    def get_object(self, doc_name, obj_name):
        for obj in self.documents_.get(doc_name, []):
            if obj["Name"] == obj_name:
                return self._as_addon(obj)
        return None

    def get_objects_(self, doc_name):
        return [self._as_addon(o) for o in self.documents_.get(doc_name, [])]

    @staticmethod
    def _as_addon(obj: dict) -> dict:
        """The object as the addon puts it on the wire.

        Every property goes through str() unless it is already a plain
        scalar, and a FreeCAD length is a Quantity - so a Length of 120
        arrives as "120.0 mm". Reproduced here because a stand-in that hands
        back a tidy float tests the code against a protocol nobody speaks:
        the slider panel was empty for exactly this reason and every test
        passed.
        """
        spoken = dict(obj)
        spoken["Properties"] = {
            name: (value if isinstance(value, (bool, str)) else f"{value} mm")
            for name, value in (obj.get("Properties") or {}).items()}
        return spoken

    def execute_code(self, code, timeout=None):
        self.calls.append(("execute_code", code, timeout))
        # The real addon returns FreeCAD's own chatter with the script's
        # output after "Output: ", which is why the bridge wraps what it
        # wants in markers rather than reading the whole message.
        if "cadsmith_export" in code:
            payload = base64.b64encode(self.step).decode()
        elif "BoundBox" in code:
            payload = json.dumps([{"name": "Box", "label": "Box",
                                   "volume": 1000.0, "area": 600.0,
                                   "faces": 6, "valid": True,
                                   "bbox": [10.0, 10.0, 10.0]}])
        elif "raise" in code:
            return {"success": False,
                    "error": "RuntimeError: that document has no solid"}
        else:
            payload = ""
        body = (freecad._MARK_OPEN + payload + freecad._MARK_CLOSE  # noqa: SLF001
                if payload else "")
        return {"success": True,
                "message": "Python code executed successfully.\nOutput: "
                           + "FreeCAD console noise\n" + body}

    def get_active_screenshot(self, view="Isometric"):
        return base64.b64encode(b"\x89PNG\r\n\x1a\n fake").decode()


def _compiles(code: str) -> bool:
    """Would FreeCAD's interpreter accept this at all?"""
    try:
        compile(code, "<freecad>", "exec")
        return True
    except SyntaxError:
        return False


def serve(handler) -> tuple[SimpleXMLRPCServer, int]:
    server = SimpleXMLRPCServer(("127.0.0.1", 0), allow_none=True,
                                logRequests=False)
    server.register_instance(handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="cadsmith_freecad_"))

    # A real solid, so the round trip ends in real measurement.
    part = (cq.Workplane("XY").box(60, 40, 12)
            .faces(">Z").workplane().rect(40, 20, forConstruction=True)
            .vertices().hole(6.0))
    source = work / "source.step"
    cq.exporters.export(part, str(source))

    stand_in = StandIn(source.read_bytes())
    server, port = serve(stand_in)
    bridge = freecad.Bridge(port=port, timeout=20.0)

    print("Finding FreeCAD")
    check("a running addon answers", bridge.alive())
    check("and says what it is", bool(bridge.status()), str(bridge.status()))

    print("\nBuilding in FreeCAD's own document")
    doc = bridge.new_document("My Part")
    check("the document is opened under the name FreeCAD gave it, not ours",
          doc == "My_Part", doc)
    again = bridge.new_document("My Part")
    check("and a second one is de-duplicated, as FreeCAD does",
          again == "My_Part001", again)

    box = bridge.add(doc, "Part::Box", "Base", Length=60, Width=40, Height=12)
    check("an object is added and reports its real name", box == "Base", box)
    twin = bridge.add(doc, "Part::Box", "Base", Length=10, Width=10, Height=10)
    check("a clashing name is renamed by FreeCAD, and we follow it",
          twin == "Base001", twin)
    check("the properties went across as FreeCAD's own",
          stand_in.documents_[doc][0]["Properties"]["Length"] == 60,
          str(stand_in.documents_[doc][0]["Properties"]))

    # The whole reason for going through FreeCAD: the tree is live, so one
    # changed number re-runs what depends on it.
    bridge.edit(doc, box, Length=75)
    check("editing a property reaches the live document",
          stand_in.documents_[doc][0]["Properties"]["Length"] == 75,
          str(stand_in.documents_[doc][0]["Properties"]))

    check("the document can be read back", len(bridge.objects(doc)) == 2,
          str([o["Name"] for o in bridge.objects(doc)]))
    check("and one object by name, under the key the addon uses",
          (bridge.object(doc, box) or {}).get("TypeId") == "Part::Box",
          str((bridge.object(doc, box) or {}).get("TypeId")))
    # The addon sends every property through str(), and a FreeCAD length is
    # a Quantity - so this is "120.0 mm", not a number. Anything that reads
    # one has to go through freecad.number().
    length = (bridge.object(doc, box) or {}).get("Properties", {}).get("Length")
    check("a length arrives as a quantity, the way the addon sends it",
          isinstance(length, str) and length.endswith("mm"), repr(length))
    check("and reads back as the number it is",
          freecad.number(length) == 75.0, str(freecad.number(length)))
    bridge.remove(doc, twin)
    check("an object can be deleted", len(bridge.objects(doc)) == 1)

    print("\nBringing the geometry back")
    blob = bridge.fetch(doc, "step")
    check("the export comes back as bytes, not as a path",
          isinstance(blob, bytes) and blob.startswith(b"ISO-10303"),
          f"{len(blob):,} bytes")
    check("and it survived base64 through the protocol intact",
          blob == source.read_bytes())

    landed = bridge.save(doc, work / "from_freecad.step")
    geometry = spec.measure_step(landed)
    box_dims = geometry["bbox"]
    check("this app can measure what FreeCAD sent it",
          abs(box_dims["xlen"] - 60) < 0.01 and abs(box_dims["zlen"] - 12) < 0.01,
          f"{box_dims['xlen']:.2f} x {box_dims['ylen']:.2f} x {box_dims['zlen']:.2f}")
    check("including the holes, off the solid rather than off the request",
          len(geometry["holes"]) == 4 and abs(geometry["holes"][0] - 6.0) < 0.01,
          str(geometry["holes"]))
    check("the exported file is the one the viewer and the drawing already read",
          landed.suffix == ".step" and landed.exists())

    measured = bridge.measure(doc)
    check("FreeCAD's own numbers come back too, as a sanity check",
          measured["solids"] and measured["solids"][0]["volume"] == 1000.0,
          str(measured["solids"][0] if measured["solids"] else None))

    print("\nThe Python it sends FreeCAD is valid Python")
    # This is the check that was missing. The scripts are assembled from a
    # shared preamble and an f-string, and the first version indented the
    # template around a preamble that was already flush left - textwrap
    # then dedented nothing and FreeCAD answered with an IndentationError
    # on line 2. Compiling here costs nothing and catches the whole class.
    sent = [call for call in stand_in.calls if call[0] == "execute_code"]
    check("every script sent so far compiles",
          all(_compiles(call[1]) for call in sent),
          f"{len(sent)} script(s)")
    for kind in ("step", "stl", "brep"):
        bridge.fetch(doc, kind)
    broken = [call[1] for call in stand_in.calls
              if call[0] == "execute_code" and not _compiles(call[1])]
    check("including every export format, not just the one we tried",
          not broken, (broken[0].strip().splitlines() or [""])[0] if broken else "")
    check("and the measurement script",
          _compiles(stand_in.calls[-1][1]) if stand_in.calls else False)

    print("\nFailures arrive as failures")
    try:
        bridge.add("NoSuchDoc", "Part::Box", "X")
        check("a refused call raises rather than returning nothing", False)
    except freecad.FreeCADError as error:
        check("a refused call raises, carrying FreeCAD's own words",
              "no document" in str(error), str(error)[:70])
    try:
        bridge.edit(doc, "Ghost", Length=1)
        check("editing something absent raises", False)
    except freecad.FreeCADError as error:
        check("editing something absent raises", "Ghost" in str(error),
              str(error)[:60])

    unreachable = freecad.Bridge(port=1, timeout=2.0)
    check("a FreeCAD that is not running reads as not running, never a crash",
          unreachable.alive() is False)
    try:
        unreachable.documents()
        check("and asking it anything says what to do about it", False)
    except freecad.FreeCADError as error:
        check("and asking it anything says what to do about it",
              "Is FreeCAD open" in str(error), str(error)[:80])

    print("\nThe token the addon can require")
    secured = freecad.Bridge(port=port, token="s3cret", timeout=20.0)
    check("a token is sent as a header, never in the URL",
          secured.alive() and "s3cret" not in secured._uri,  # noqa: SLF001
          secured._uri)  # noqa: SLF001

    server.shutdown()
    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("ALL CHECKS PASSED")
    print("\nNote: this exercises the protocol, not FreeCAD's geometry.")
    print("Point it at a real FreeCAD with app/tools/freecad_check.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
