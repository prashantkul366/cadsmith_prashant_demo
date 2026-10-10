"""Check that the progress strip says what the run is actually doing.

A stage with no clock cannot be told apart from a stage that has stopped.
A Planner call on a hard part is a minute of a model thinking with nothing
on screen yet, and a strip saying only "Planning the part" was read, more
than once, as a run that had hung.

`spec` - the kernel measuring the finished solid against the plan - was
mapped onto no stage either, so the strip sat out the one part of the run
that decides whether the part is right.

Drives the page's own event handler with the event stream a run really
emits, and reads the strip back out of the DOM.

Run:  .venv/bin/python -m app.tests.test_progress
"""

from __future__ import annotations

import functools
import http.server
import socketserver
import sys
import tempfile
import threading
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"

# What the server really sends, in order. Taken from freecad_run.serve and
# jobs.py rather than invented: the tool road emits PHASE_PLAN, then
# PHASE_CODE started, then one PHASE_FREECAD per operation, and the script
# road emits plan / code / execute / judge. RunContext.emit stamps `road`
# on all of them, which is the only thing that tells the two apart - every
# phase name here occurs on both roads except `freecad` itself.
SCRIPT_RUN = [
    {"phase": "job", "status": "started", "data": {}},
    {"phase": "plan", "status": "started", "data": {}},
    {"phase": "code", "status": "started", "data": {}},
    {"phase": "code", "status": "ok",
     "data": {"code": "import cadquery as cq\nresult = cq.Workplane()",
              "lines": 2}},
    {"phase": "execute", "status": "started", "data": {}},
    {"phase": "spec", "status": "ok", "data": {}},
    {"phase": "judge", "status": "started", "data": {}},
]

# Feed the page a run, then read the strip. Replies with the active stage's
# label and detail, every label in order, and whether the clock is running.
DRIVE = """(events) => {
  S.editing = false;
  renderStages("plan", t("detail.sending"));
  const seen = [];
  events.forEach((e, i) => {
    handleEvent({seq: i, ts: 0, message: "", ...e});
    const act = document.querySelector("#pipe .pstep.act .plabel");
    seen.push({
      phase: e.phase + "/" + e.status,
      label: act ? act.textContent.trim() : "",
      detail: (document.querySelector("#pipe .pstep.act .pdetail") || {}).textContent || "",
    });
  });
  return {
    seen,
    labels: [...document.querySelectorAll("#pipe .plabel")]
            .map(n => n.textContent.trim()),
    clock: !!stageClock,
  };
}"""


def _serve(root: Path):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args) -> None:      # the page 404s on /api/*
            pass

    handler = functools.partial(Quiet, directory=str(root))

    class Reusable(socketserver.TCPServer):
        allow_reuse_address = True

    server = Reusable(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def _browser(playwright):
    try:
        return playwright.chromium.launch()
    except Exception:
        for candidate in sorted(
                Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome")):
            return playwright.chromium.launch(executable_path=str(candidate))
        raise


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP  playwright is not installed - the strip is not checked")
        return 0

    failures = 0

    def check(label: str, problems: list[str], detail: str = "") -> None:
        nonlocal failures
        if problems:
            failures += 1
        print(f"  {'FAIL' if problems else 'PASS'}  {label}"
              + (f" - {detail}" if detail else ""))
        for problem in problems:
            print(f"          {problem}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "static").symlink_to(WEB)
        (root / "index.html").symlink_to(WEB / "index.html")
        server, port = _serve(root)
        try:
            with sync_playwright() as playwright:
                try:
                    browser = _browser(playwright)
                except Exception as exc:
                    print(f"SKIP  no usable Chromium ({type(exc).__name__})"
                          " - the strip is not checked")
                    return 0
                page = browser.new_page(viewport={"width": 1600, "height": 900})
                broke: list[str] = []
                page.on("pageerror", lambda e: broke.append(str(e)))
                page.goto(f"http://127.0.0.1:{port}/index.html",
                          wait_until="load")
                page.wait_for_timeout(350)

                print("The strip follows the run")
                report = page.evaluate(DRIVE, SCRIPT_RUN)
                steps = {row["phase"]: row for row in report["seen"]}
                problems = list(broke)
                broke.clear()
                for phase, want in (("plan/started", "Planning the part"),
                                    ("code/started", "Writing CadQuery"),
                                    ("execute/started", "Building the solid"),
                                    # The bug: spec left the strip where it was.
                                    ("spec/ok", "Validating geometry"),
                                    ("judge/started", "Validating geometry")):
                    if steps[phase]["label"] != want:
                        problems.append(f"{phase} shows "
                                        f"{steps[phase]['label']!r}, not {want!r}")
                if steps["code/ok"]["detail"] != "2 lines written":
                    problems.append("the detail line is lost: "
                                    f"{steps['code/ok']['detail']!r}")
                if not report["clock"]:
                    problems.append("no clock is running on the active stage")
                check("every phase moves the strip", problems,
                      " / ".join(report["labels"]))

                print("The clock counts, and stops when the run does")
                page.evaluate("""() => {
                  S.editing = false;
                  renderStages("plan", "");
                  S.stage.at = Date.now() - 42000;   // as if 42s had passed
                  paintClock();
                }""")
                ticked = page.evaluate(
                    "() => document.querySelector('#pipe .pstep.act .pms')"
                    ".textContent")
                problems = list(broke)
                broke.clear()
                if ticked.strip() != "42s":
                    problems.append(f"the clock reads {ticked!r}, not '42s'")
                page.evaluate("() => renderStages('done', '')")
                if page.evaluate("() => !!stageClock"):
                    problems.append("the clock is still running after the run")
                check("42s shown, then stopped", problems, ticked)

                browser.close()
        finally:
            server.shutdown()
            server.server_close()

    print("\n" + "=" * 58)
    print("ALL CHECKS PASSED" if not failures else f"{failures} CHECK(S) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
