"""Check that the four right-hand panels never draw on top of one another.

Reasoning, Design Plan, Generated CadQuery and Validation share one flex
column. Each panel's header and button row are `flex:none`, so a panel
squeezed below that chrome does not shrink -- it overflows and paints over the
panel beneath it. That is what happened when the Reasoning panel was added:
`.rsec.code` declared `flex:1`, whose 0% flex-basis made it the only item the
shrink algorithm charged, so it collapsed to zero height and its header and
download row landed on top of Validation.

The bug only appears once the panels hold real content, so this drives a real
browser rather than reading the stylesheet.

Run:  .venv/bin/python -m app.tests.test_layout
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

# The page asks for its assets under /static, so mirror that shape on disk.
SEED = """(blocks) => {
  const think = document.getElementById('thinkBody');
  think.innerHTML = '';
  for (let i = 0; i < blocks; i++) {
    const b = document.createElement('div');
    b.className = 'tblock'; b.dataset.state = 'done';
    b.innerHTML = '<div class="thead"><b>Coder</b> <span>writing CadQuery</span></div>'
      + '<div class="tbody"><div class="ttext">'
      + 'Reasoning about the plate and its assumed thickness. '.repeat(12)
      + '</div></div>';
    think.appendChild(b);
  }
  document.getElementById('planBody').innerHTML = '<div class="dims">'
    + '<div class="dim"><span>length</span><b>80mm</b></div>'.repeat(8) + '</div>';
  document.getElementById('hl').textContent =
    Array.from({length: 40}, (_, i) => `line_${i} = cq.Workplane("XY").box(80, 40, 5)`).join('\\n');
  document.getElementById('valBody').innerHTML =
    '<div>' + 'The kernel rebuilt the solid and reports it watertight. '.repeat(20) + '</div>';
}"""

MEASURE = """() => {
  const rail = document.querySelector('.rsplit').getBoundingClientRect();
  const boxes = [...document.querySelectorAll('.rsplit > .rsec')].map(s => {
    const r = s.getBoundingClientRect();
    let painted = r.bottom;            // the lowest pixel any child actually paints
    for (const kid of s.children) {
      const k = kid.getBoundingClientRect();
      if (k.height && k.bottom > painted) painted = k.bottom;
    }
    return {name: s.className.replace('rsec ', ''), top: r.top, height: r.height, painted};
  });
  const problems = [];
  for (let i = 0; i < boxes.length - 1; i++) {
    const spill = Math.round(boxes[i].painted - boxes[i + 1].top);
    if (spill > 1) problems.push(`${boxes[i].name} paints ${spill}px over ${boxes[i + 1].name}`);
  }
  for (const b of boxes) {
    if (b.height < 35) problems.push(`${b.name} is ${Math.round(b.height)}px - its header is cut off`);
    if (b.top < rail.top - 1 || b.top > rail.bottom + 1)
      problems.push(`${b.name} starts outside the rail`);
  }
  return {sizes: boxes.map(b => `${b.name}=${Math.round(b.height)}`).join(' '), problems};
}"""

# Window sizes worth caring about: a large monitor, two common laptops, and a
# short window where the panels genuinely compete for room.
VIEWPORTS = [(1920, 1010), (1600, 900), (1440, 780), (1280, 720), (1280, 600)]
THINK_BLOCKS = [1, 3, 15]   # one step, one iteration, five refinement iterations


def _serve(root: Path):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args) -> None:      # the page 404s on /api/*; that is expected
            pass

    handler = functools.partial(Quiet, directory=str(root))

    class Reusable(socketserver.TCPServer):
        allow_reuse_address = True

    server = Reusable(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def _browser(playwright):
    """Launch Chromium, falling back to a prebuilt one if the versions differ."""
    try:
        return playwright.chromium.launch()
    except Exception:
        for candidate in sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome")):
            return playwright.chromium.launch(executable_path=str(candidate))
        raise


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP  playwright is not installed - layout is not checked")
        return 0

    failures = 0

    def check(label: str, problems: list[str], detail: str) -> None:
        nonlocal failures
        if problems:
            failures += 1
        print(f"  {'FAIL' if problems else 'PASS'}  {label} - {detail}")
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
                    print(f"SKIP  no usable Chromium ({type(exc).__name__}) - layout is not checked")
                    return 0

                print("The right-hand panels stay out of each other's way")
                for width, height in VIEWPORTS:
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page.goto(f"http://127.0.0.1:{port}/index.html", wait_until="load")
                    page.wait_for_timeout(350)
                    for blocks in THINK_BLOCKS:
                        page.evaluate(SEED, blocks)
                        page.wait_for_timeout(120)
                        report = page.evaluate(MEASURE)
                        check(f"{width}x{height}, {blocks} reasoning block(s)",
                              report["problems"], report["sizes"])
                    page.close()
                browser.close()
        finally:
            server.shutdown()
            server.server_close()

    print("\n" + "=" * 58)
    if failures:
        print(f"{failures} LAYOUT CHECK(S) FAILED")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
