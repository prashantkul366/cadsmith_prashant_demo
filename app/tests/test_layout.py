"""Check that nothing on the page paints over anything else.

The app is three columns - the conversation, the part, and the cards that
describe it - and each of them holds a stack of things that grow with the
run. Growth is where a layout fails: a reasoning block arrives, a card fills
with tiles, the generated script runs to a hundred lines, and some item that
was told to be
`flex:none` stops shrinking and overflows the thing beneath it instead.

That has happened twice. The first time, the reasoning panel's `flex:1` gave
it a 0% basis, so it was the only item the shrink algorithm charged and it
collapsed to nothing, putting its header on top of Validation. The second
time this file went stale: it was still measuring `.rsplit > .rsec`, a
structure the page had not had for some time, so it threw instead of
checking anything and the failure read as a browser problem.

So it measures by position rather than by class names that could be
renamed: everything inside a column has to stay inside that column, the
columns have to stay side by side, and the page must never scroll sideways.

Runs a real browser, because the bug only exists once the panels hold real
content.

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

# Fill every column with more than it will usually hold. The numbers are
# deliberately past what a normal run produces: a layout that survives a
# thirty-step build survives a six-step one.
SEED = """(blocks) => {
  // The conversation: what was asked, the plan, and the agents thinking.
  showAsk('A 120 x 60 x 12 mounting plate in 6061, four M8 tapped holes '
          + '15 in from each corner, R8 corners, and a 20 bore on centre.');
  renderPlan({
    description: 'A 120 x 60 x 12 mounting plate',
    dimensions: {key_dimensions: {
      '120 mm overall': 120, '60 mm overall': 60, '12 mm overall': 12,
      'bore 20': 20, 'corner radius': 8, 'M8 tapped x4': 6.8}},
    must_be_true: ['4 hole(s), as the request asks for', 'a 20 bore']});
  const think = document.getElementById('thinkBody');
  think.innerHTML = '';
  for (let i = 0; i < blocks; i++) {
    const b = document.createElement('details');
    b.className = 'tblock'; b.dataset.state = 'done'; b.open = true;
    b.innerHTML = '<summary class="thead"><b>Builder</b> '
      + '<span class="tms">1.2s</span></summary>'
      + '<div class="tbody"><div class="ttext">'
      + 'Padding the outline before the holes, so the holes are features of '
      + 'the pad rather than cuts in a block. '.repeat(6)
      + '</div></div>';
    think.appendChild(b);
  }

  // The centre: a script long enough to scroll. This branch's centre pane
  // is the generated CadQuery rather than a build record, so it is filled
  // through the element the page actually has.
  document.getElementById('codeScroll').innerHTML =
    '<pre class="code-inner">'
    + ('import cadquery as cq\\n\\nlength = 120.0\\nwidth = 60.0\\n'
       + 'result = cq.Workplane(\\'XY\\').box(length, width, 12.0)\\n').repeat(12)
    + '</pre>';
  document.getElementById('planBody').innerHTML =
    '<div>' + 'A padded outline, four tapped holes and a bore. '.repeat(14)
    + '</div>';
  showView('code');

  // The cards on the right, every one of them open and full.
  renderKernelFacts({
    source: 'freecad', passed: true,
    geometry: {bounding_box: {xlen: 120, ylen: 60, zlen: 12},
      volume: 83823.6, num_faces: 18, num_edges: 44, is_valid: true,
      mass: {material: 'Aluminium 6061-T6', mass_kg: 0.226, mass_g: 226},
      holes_as_meant: [{label: 'M8 THRU', diameter: 6.8},
                       {label: 'M8 THRU', diameter: 6.8},
                       {label: 'M8 THRU', diameter: 6.8},
                       {label: 'M8 THRU', diameter: 6.8},
                       {label: '\\u00d820 \\u2334\\u00d830 6 DEEP', diameter: 20}]}});
  document.getElementById('usage').hidden = false;
  document.getElementById('usage').innerHTML =
    '<div class="tile"><b>12.4k</b><span>in</span></div>'.repeat(4);
  document.getElementById('cardTokens').hidden = false;
  document.getElementById('cardParams').hidden = false;
  document.getElementById('paramsBody').innerHTML =
    '<div class="prow"><span>length</span><input type="range"></div>'.repeat(6);
  document.getElementById('valBody').innerHTML =
    '<div>' + 'The kernel rebuilt the solid and reports it watertight. '.repeat(14)
    + '</div>';
  document.querySelectorAll('.rcard').forEach(c => c.classList.remove('shut'));
}"""

# Everything is measured off the boxes the browser actually laid out, so a
# renamed class cannot make this pass by measuring nothing. It can only make
# it find no columns, which is itself a failure.
MEASURE = """() => {
  const problems = [];
  const box = el => el.getBoundingClientRect();
  const round = n => Math.round(n);

  const columns = [...document.querySelectorAll('.work > .col')];
  if (columns.length !== 3) {
    problems.push(`expected three columns, found ${columns.length}`);
    return {sizes: '', problems};
  }

  // The columns themselves: side by side, in order, none overlapping.
  for (let i = 0; i < columns.length - 1; i++) {
    const over = round(box(columns[i]).right - box(columns[i + 1]).left);
    if (over > 1) problems.push(`column ${i} overlaps column ${i + 1} by ${over}px`);
  }

  // Nothing may end up where it cannot be read. A column that scrolls is
  // allowed to hold more than fits - that is what scrolling is for - so
  // what is checked is whether scrolling reaches it. Measuring against the
  // column's visible box instead called every card below the fold an
  // escape, which is the difference between a layout bug and a long page.
  for (const [i, col] of columns.entries()) {
    const edge = box(col);
    // Only a column that can actually be scrolled gets the benefit of the
    // doubt. `overflow:hidden` also makes scrollHeight exceed clientHeight,
    // and content under that is not below the fold - it is gone.
    const style = getComputedStyle(col);
    const scrolls = axis => axis === "auto" || axis === "scroll";
    const spareY = scrolls(style.overflowY)
      ? col.scrollHeight - col.clientHeight - col.scrollTop : 0;
    const spareX = scrolls(style.overflowX)
      ? col.scrollWidth - col.clientWidth - col.scrollLeft : 0;
    for (const kid of col.children) {
      if (kid.hidden) continue;
      const k = box(kid);
      if (!k.width || !k.height) continue;
      const out = Math.max(
        round(k.right - edge.right) - spareX, round(edge.left - k.left),
        round(k.bottom - edge.bottom) - spareY, round(edge.top - k.top));
      if (out > 1) problems.push(
        `${kid.className || kid.id} escapes column ${i} by ${out}px`);
    }
  }

  // The cards on the right stack; none may paint over the next.
  const cards = [...document.querySelectorAll('.col.right > .rcard')]
    .filter(c => !c.hidden);
  if (cards.length < 4) problems.push(`only ${cards.length} card(s) on the right`);
  for (let i = 0; i < cards.length - 1; i++) {
    const spill = round(box(cards[i]).bottom - box(cards[i + 1]).top);
    if (spill > 1) problems.push(
      `card ${cards[i].dataset.card} paints ${spill}px over ${cards[i + 1].dataset.card}`);
    const head = box(cards[i].querySelector('.rhead'));
    if (round(head.bottom) > round(box(cards[i]).bottom) + 1)
      problems.push(`card ${cards[i].dataset.card} has its header cut off`);
  }

  // The composer is pinned at the foot of the conversation and must be
  // whole: it is the only way to type anything.
  const composer = document.querySelector('.composer');
  const left = box(columns[0]);
  if (round(box(composer).bottom) > round(left.bottom) + 1)
    problems.push(`the composer is ${round(box(composer).bottom - left.bottom)}px below the column`);
  if (box(composer).height < 60)
    problems.push(`the composer is ${round(box(composer).height)}px tall`);

  // The script panel scrolls down, never sideways: a long line hiding the
  // right-hand end of the code is the same bug as a sideways build panel.
  const code = document.getElementById('codeScroll');
  if (code && code.scrollWidth - code.clientWidth > 1)
    problems.push(`the script panel scrolls ${code.scrollWidth - code.clientWidth}px sideways`);

  // And the page itself never does.
  const sideways = document.documentElement.scrollWidth - window.innerWidth;
  if (sideways > 1) problems.push(`the page scrolls ${sideways}px sideways`);

  return {
    sizes: columns.map(c => round(box(c).width)).join('/')
           + ` cards=${cards.length}`,
    problems,
  };
}"""

# A large monitor, two common laptops, and a short window where things
# genuinely compete for room.
VIEWPORTS = [(1920, 1010), (1600, 900), (1440, 780), (1280, 720), (1280, 600)]
THINK_BLOCKS = [1, 3, 15]   # one step, one iteration, a long build
LANGS = ["en", "ja"]        # Japanese sets different line heights


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

                print("Nothing paints over anything else")
                for lang in LANGS:
                    for width, height in VIEWPORTS:
                        page = browser.new_page(viewport={"width": width, "height": height})
                        broke: list[str] = []
                        page.on("pageerror", lambda e: broke.append(str(e)))
                        page.goto(f"http://127.0.0.1:{port}/index.html",
                                  wait_until="load")
                        page.wait_for_timeout(350)
                        page.evaluate(f"I18N.set('{lang}')")
                        page.wait_for_timeout(120)
                        for blocks in THINK_BLOCKS:
                            page.evaluate(SEED, blocks)
                            page.wait_for_timeout(140)
                            report = page.evaluate(MEASURE)
                            check(f"{lang} {width}x{height}, {blocks} reasoning block(s)",
                                  report["problems"] + broke, report["sizes"])
                            broke.clear()
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
