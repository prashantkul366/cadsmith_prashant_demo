"""The feature tree panel, in a real browser against a real FreeCAD.

The claim this checks is the one YMRI asked for: the tree in the panel is
the tree in the document, a number changed here changes the part, and a
number the part cannot be rebuilt with is refused and put back.

Nothing is mocked except where FreeCAD lives. The server normally talks to
a FreeCAD with the addon running; here it is pointed at a headless
``freecadcmd`` that holds the same document, so the whole path - route,
module, script inside FreeCAD, answer, panel - is the real one.

Needs freecadcmd and a browser. Skips where either is missing.

    .venv/bin/python -m app.tests.ui_tree_check [--shot out.png]
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

_CANDIDATE_BROWSERS = [
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/opt/pw-browsers/chromium/chrome-linux/chrome",
]
_CANDIDATE_FREECAD = [os.environ.get("CADSMITH_FREECADCMD", ""),
                      "freecadcmd", "FreeCADCmd",
                      "/tmp/claude-0/fc/bin/freecadcmd"]

#: One body with a history: a sketch, a pad over it, a pocket through it.
#: The same fixture test_tree uses, because the panel and the module must
#: be looking at the same thing for either check to mean anything.
DOCUMENT = '''
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
pad.Length = %(length)s
doc.recompute()
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
pocket.Type = 1
pocket.Reversed = True
pocket.Label = "Bolt hole"
doc.recompute()
'''

failures: list[str] = []
console: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}"
          + (f" - {detail}" if detail else ""))
    if not ok:
        failures.append(label)


def found(candidates) -> str:
    for candidate in candidates:
        if not candidate:
            continue
        hit = shutil.which(candidate) or (
            candidate if Path(candidate).exists() else "")
        if hit:
            return hit
    return ""


class CmdBridge:
    """The bridge surface, backed by freecadcmd, holding one length.

    freecadcmd is a fresh process per call, so the document has to be
    rebuilt each time. The one number the panel changes is carried in the
    fixture, which is what makes an edit visible on the next read.
    """

    #: The health panel names where FreeCAD is, so this has to be able to
    #: answer that the way the real bridge does.
    host, port = "freecadcmd", 0

    def __init__(self, binary: str) -> None:
        self.binary = binary
        self.length = 12.0
        self.lock = threading.Lock()
        self.exported: dict = {}

    def status(self) -> dict:
        return {"version": "freecadcmd", "gui": False}

    def documents(self) -> list:
        return ["Part"]

    def objects(self, document: str) -> list:
        return []

    def measure(self, document: str) -> dict:
        return {"solids": []}

    def alive(self, timeout: float = 0.0) -> bool:
        return True

    def run(self, code: str, timeout: float = 120.0) -> str:
        with self.lock:
            setup = DOCUMENT % {"length": self.length}
            # An accepted edit has to stick, or the next read undoes it.
            before = self.length
            script = tempfile.NamedTemporaryFile(
                "w", suffix=".py", delete=False, encoding="utf-8")
            script.write("# -*- coding: utf-8 -*-\n" + setup + code)
            script.close()
            try:
                done = subprocess.run([self.binary, script.name],
                                      capture_output=True, text=True,
                                      timeout=timeout)
                printed = done.stdout + done.stderr
            finally:
                os.unlink(script.name)
            if '"Length"' in code and '"ok": true' in printed.lower():
                import json as _json
                for line in printed.splitlines():
                    if line.startswith("CADSMITH_TREE "):
                        answer = _json.loads(line[len("CADSMITH_TREE "):])
                        kept = (answer.get("set") or {}).get("Length")
                        self.length = float(kept) if kept else before
            return printed

    def fetch(self, document: str, kind: str = "step",
              timeout: float = 120.0) -> bytes:
        """The exported solid, remembered per length.

        A live FreeCAD exports from the document it already has open; this
        harness rebuilds it in a fresh process first, which is seconds. The
        document has not changed between two exports at the same length, so
        neither has the answer, and caching it keeps the browser check from
        timing out behind its own viewport refresh.
        """
        key = (document, kind, self.length)
        if key not in self.exported:
            from app.server import freecad as freecad_mod
            self.exported[key] = freecad_mod.Bridge.fetch(
                self, document, kind, timeout)
        return self.exported[key]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def settled(page, wanted: str, seconds: int = 150):
    """Wait for the field to come back from FreeCAD reading `wanted`.

    Each call rebuilds the document in a fresh freecadcmd, so a round trip
    is seconds. A fixed sleep would either flake or make the check slow on
    every machine that is not this one.
    """
    try:
        page.wait_for_function(
            "want => { const f = document.querySelector("
            "'[data-field=\"Plate.Length\"]'); "
            "return f && String(Number(f.value)) === want; }",
            arg=wanted, timeout=seconds * 1000)
    except Exception:
        pass
    value = page.eval_on_selector_all(
        '[data-field="Plate.Length"]', "ns => ns.map(n => n.value)")
    return float(value[0]) if value else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shot", default="")
    args = parser.parse_args()

    binary = found(_CANDIDATE_FREECAD)
    browser_path = found(_CANDIDATE_BROWSERS)
    if not binary or not browser_path:
        print("No freecadcmd or no browser - skipping, as a missing tool is "
              "not a failing test.")
        return 0

    from playwright.sync_api import sync_playwright   # noqa: PLC0415
    import uvicorn                                    # noqa: PLC0415

    from app.server import app as app_module          # noqa: PLC0415
    from app.server import freecad_run, jobs          # noqa: PLC0415

    bridge = CmdBridge(binary)
    # Where FreeCAD lives, and only that. Every other part of the path -
    # the route, the module, the script, the panel - is the shipping one.
    freecad_run.bridge_from_env = lambda *a, **k: bridge
    app_module.freecad_run.bridge_from_env = lambda *a, **k: bridge
    app_module.FREECAD_DEFAULT = True
    jobs.FREECAD_DEFAULT = True

    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app_module.app, host="127.0.0.1",
                                           port=port, log_level="warning"))
    # uvicorn installs signal handlers, which only the main thread may do.
    server.install_signal_handlers = lambda: None
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # Startup restores every past run and runs the health checks, which on
    # a well-used checkout is seconds rather than milliseconds.
    for _ in range(600):
        try:
            with socket.create_connection(("127.0.0.1", port), 0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        print("the server did not come up")
        return 1

    base = f"http://127.0.0.1:{port}"
    try:
        with sync_playwright() as play:
            chrome = play.chromium.launch(executable_path=browser_path)
            page = chrome.new_page(viewport={"width": 1480, "height": 940})
            page.on("console", lambda m: console.append(
                f"{m.type}: {m.text}") if m.type == "error" else None)
            page.goto(base, wait_until="networkidle")

            print("The tree, in the panel")
            # The document picker is what tells the panel which document to
            # read, and it is filled from the server.
            page.wait_for_selector('#viewSeg .vsegb[data-view="tree"]')
            page.evaluate(
                "async () => { await loadDocuments(); "
                "S.freecadDocument = 'Part'; showView('tree'); }")
            page.wait_for_selector(".trow", timeout=30000)
            rows = page.eval_on_selector_all(
                ".trow .trow-name", "ns => ns.map(n => n.textContent.trim())")
            check("the body and its features are listed",
                  any("Body" in r for r in rows) and
                  any("Plate" in r for r in rows), ", ".join(rows[:6]))
            check("a feature shows the label the engineer gave it",
                  any("Bolt hole" in r for r in rows), ", ".join(rows[:8]))

            print("\nWhat the panel offers to change")
            page.click('[data-tree-toggle="Plate"]')
            page.wait_for_selector('[data-field="Plate.Length"]')
            value = page.input_value('[data-field="Plate.Length"]')
            check("the pad's length is an editable field with its value",
                  abs(float(value) - 12.0) < 1e-6, value)
            kinds = page.eval_on_selector_all(
                ".tprop.ro .tprop-name",
                "ns => ns.map(n => n.textContent.trim())")
            check("and what FreeCAD will not let it write is shown, not "
                  "offered", bool(kinds), ", ".join(kinds[:4]))

            print("\nChanging it")
            # The row stays open across the re-read, so the field is still
            # there afterwards: waiting for its value to change is what
            # says the panel went to the document and came back.
            page.fill('[data-field="Plate.Length"]', "20")
            page.dispatch_event('[data-field="Plate.Length"]', "change")
            took = settled(page, "20")
            check("the document took it and the panel re-read it",
                  took is not None and abs(took - 20.0) < 1e-6, str(took))

            print("\nWhat must be refused")
            page.fill('[data-field="Plate.Length"]', "0")
            page.dispatch_event('[data-field="Plate.Length"]', "change")
            back = settled(page, "20")
            check("a value the part cannot be rebuilt with does not stick",
                  back is not None and abs(back - 20.0) < 1e-6, str(back))

            if args.shot:
                page.click('[data-tree-toggle="Plate"]')
                page.wait_for_timeout(500)
                page.screenshot(path=args.shot)
                print(f"\n  wrote {args.shot}")

            noise = [c for c in console if "favicon" not in c.lower()]
            check("no JavaScript errors", not noise, "; ".join(noise[:2]))
            chrome.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)

    print("\n" + "=" * 58)
    print("ALL CHECKS PASSED" if not failures
          else f"{len(failures)} CHECK(S) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
