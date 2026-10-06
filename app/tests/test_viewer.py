"""The mesh the viewer draws is the solid the kernel exported.

One bug, and the whole of why this file exists. The ASCII STL parser read a
number with the pattern ``[\\d.eE+]+``, which cannot cross the minus sign in
``e-14``. FreeCAD writes every coordinate in scientific notation, so a line
like ``vertex 75.0 -1.836970198721e-14 15.0`` did not match at all - and the
vertex was dropped rather than reported. The vertices after it shifted up
into each other's triangles, which draws as long thin sails spanning the
part: a flange with its holes in the right places and spikes across its
face.

Nothing caught it because nothing exercised it. CadQuery writes *binary*
STL, so every part this app had ever shown took the other branch; the ASCII
path only woke up when parts started arriving from FreeCAD.

So both branches are driven here, in a real browser, against meshes exported
by the kernel: a binary one as CadQuery writes it, and an ASCII one with the
exponents that broke it. What is asserted is the thing the person actually
cares about - that the shape on screen is the size of the shape that was
built.

Needs Chromium. Skips rather than fails without one.

Run:  .venv/bin/python -m app.tests.test_viewer
"""

from __future__ import annotations

import functools
import http.server
import socketserver
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "app" / "web"
sys.path.insert(0, str(ROOT))

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


#: Everything viewer.js reaches for, and nothing else. It is a module that
#: binds to the app's page, so a page is what it needs.
PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>html,body{margin:0}#gl{width:800px;height:560px;position:relative}
#axes{position:absolute;left:8px;top:8px;width:90px;height:90px}</style>
</head><body>
<div id="gl"><canvas id="axes"></canvas></div>
<svg id="axG"></svg><span id="scaleTxt"></span><button id="spinBtn"></button>
<script src="three.min.js"></script>
<script src="viewer.js"></script>
</body></html>
"""


#: What a kernel writes where the arithmetic should have given zero. Taken
#: from a real FreeCAD export of a flange: the top face lies on Z=0 and its
#: vertices come out at -1.836970198721e-14, not at 0. Every one of those is
#: a line the old pattern could not read.
ALMOST_ZERO = -1.836970198721e-14


def ascii_stl(solid) -> str:
    """The same mesh, written the way FreeCAD writes one.

    Scientific notation throughout, and - the part that matters - a true
    zero is written as the tiny negative value a kernel actually produces,
    because an exact 0.0 formats as 0.000000e+00 and sails through the
    broken pattern. A fixture that writes clean zeros tests nothing.
    """
    def number(value: float) -> str:
        return f"{ALMOST_ZERO if value == 0.0 else value:.12e}"

    lines = ["solid part"]
    for face in solid.Faces():
        for triangle in _triangles(face):
            normal, points = triangle
            lines.append("  facet normal " + " ".join(number(v) for v in normal))
            lines.append("    outer loop")
            for point in points:
                lines.append("      vertex " + " ".join(number(v) for v in point))
            lines.append("    endloop")
            lines.append("  endfacet")
    lines.append("endsolid part")
    return "\n".join(lines) + "\n"


def _triangles(face):
    """Tessellate one face into (normal, three points)."""
    points, facets = face.tessellate(0.1)
    for a, b, c in facets:
        pa, pb, pc = points[a], points[b], points[c]
        u = (pb.x - pa.x, pb.y - pa.y, pb.z - pa.z)
        v = (pc.x - pa.x, pc.y - pa.y, pc.z - pa.z)
        normal = (u[1] * v[2] - u[2] * v[1],
                  u[2] * v[0] - u[0] * v[2],
                  u[0] * v[1] - u[1] * v[0])
        length = sum(n * n for n in normal) ** 0.5 or 1.0
        yield ([n / length for n in normal],
               [(p.x, p.y, p.z) for p in (pa, pb, pc)])


def _serve(root: Path):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args) -> None:
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
        for candidate in sorted(Path("/opt/pw-browsers").glob(
                "chromium-*/chrome-linux/chrome")):
            return playwright.chromium.launch(executable_path=str(candidate))
        raise


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP  playwright is not installed - the viewer is not checked")
        return 0

    import cadquery as cq

    root = Path(tempfile.mkdtemp(prefix="cadsmith_viewer_"))
    (root / "viewer.js").write_bytes((WEB / "viewer.js").read_bytes())
    (root / "three.min.js").write_bytes((WEB / "vendor" / "three.min.js").read_bytes())
    (root / "page.html").write_text(PAGE, encoding="utf-8")

    # A flange: a disc, a central bore and six bolt holes. Chosen because it
    # is the part the bug was found on, and because a face with several
    # inner wires is where a dropped vertex shows.
    part = (cq.Workplane("XY").circle(75).extrude(15)
            .faces(">Z").workplane().hole(50)
            .faces(">Z").workplane().polarArray(60, 0, 360, 6).hole(12))
    cq.exporters.export(part, str(root / "binary.stl"), exportType="STL",
                        tolerance=0.1, angularTolerance=0.2)
    (root / "ascii.stl").write_text(ascii_stl(part.val()), encoding="utf-8")

    text = (root / "ascii.stl").read_text(encoding="utf-8")
    facets = text.count("facet normal")
    broken_lines = sum(1 for line in text.splitlines()
                       if line.strip().startswith("vertex") and "e-" in line)
    print("Two meshes of one flange, 150 x 150 x 15 mm")
    check("the binary one is written the way CadQuery writes it",
          (root / "binary.stl").read_bytes()[:5] != b"solid",
          f"{(root / 'binary.stl').stat().st_size:,} bytes")
    check("and the ASCII one carries the exponents that broke the parser",
          broken_lines > 100,
          f"{broken_lines:,} of {facets:,} facets have one in a vertex line")

    server, port = _serve(root)
    try:
        with sync_playwright() as playwright:
            try:
                browser = _browser(playwright)
            except Exception as exc:
                print(f"SKIP  no usable Chromium ({type(exc).__name__})")
                return 0

            print("\nBoth draw the part that was built")
            for name in ("binary.stl", "ascii.stl"):
                page = browser.new_page(viewport={"width": 800, "height": 560})
                broke: list[str] = []
                page.on("pageerror", lambda error: broke.append(str(error)))
                page.goto(f"http://127.0.0.1:{port}/page.html", wait_until="load")
                page.wait_for_timeout(300)
                drawn = page.evaluate(
                    """async (file) => {
                        await Viewer.load(file);
                        const e = Viewer.extents;
                        return {size: e ? [e.x, e.y, e.z] : null,
                                triangles: Viewer.triangles};
                    }""", name)
                page.close()
                size = drawn["size"]
                check(f"{name} loads without an error", not broke,
                      (broke[0][:70] if broke else ""))
                check(f"{name} is the size of the part",
                      size is not None
                      and abs(size[0] - 150) < 1 and abs(size[1] - 150) < 1
                      and abs(size[2] - 15) < 0.5,
                      " x ".join(f"{v:.2f}" for v in size) if size else "nothing")
                # The check that matters. A parser that drops vertices still
                # draws something the right size - the spikes it makes are
                # inside the part - so the bounding box above would pass on
                # a mesh nobody could use. Every facet in the file has to
                # reach the screen.
                check(f"{name} draws every facet in the file",
                      drawn["triangles"] == facets,
                      f"{drawn['triangles']:,} of {facets:,}")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()

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
