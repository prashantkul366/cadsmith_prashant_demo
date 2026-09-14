"""The code panel's two views, in a real browser.

The claim is that someone who never opens the Code view can still work: the
Parameters view has to show every dimension the script declares, change the
source as a control moves, and rebuild the real part when it is let go. Not a
simplified model of the part - the same numbers, the same patcher, the same
kernel.

Also checked here: the right column. Every panel has to be reachable at any
window height, because a panel squeezed to its header hides its content
without looking like it is hiding anything.

Needs a running server (no model backend required - it drives a catalogue
part, which is built with no model call):

    ./app/run_app.sh &
    .venv/bin/python -m app.tests.ui_params_check
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

_CANDIDATE_BROWSERS = [
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/opt/pw-browsers/chromium/chrome-linux/chrome",
]

failures: list[str] = []
console: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def executable() -> str | None:
    for candidate in _CANDIDATE_BROWSERS:
        if Path(candidate).exists():
            return candidate
    return None


def js_errors() -> list[str]:
    skip = ("favicon", "failed to load resource")
    return [c for c in console if not any(s in c.lower() for s in skip)]


def build(page, prompt: str) -> None:
    page.fill("#prompt", prompt)
    page.click("#genBtn")
    page.wait_for_function(
        "() => S.busy === false && S.paramLoading === false && S.params.length",
        timeout=180000)
    page.wait_for_timeout(400)


def rows(page) -> list[dict]:
    return page.evaluate("""() =>
        [...document.querySelectorAll('#paramsBody .prow')].map(r => ({
          name: r.dataset.name,
          label: r.querySelector('.prow-name').textContent,
          value: parseFloat(r.querySelector('.prow-num').value),
          unit: r.querySelector('.prow-unit').textContent,
          min: parseFloat(r.querySelector('input[type=range]').min),
          max: parseFloat(r.querySelector('input[type=range]').max),
          dirty: r.classList.contains('dirty'),
        }))""")


def code_line(page, name: str) -> str:
    return page.evaluate(
        """name => ($('#hl').textContent.split('\\n')
                    .find(l => l.startsWith(name + ' ')) || '').trim()""", name)


def zlen(page):
    return page.evaluate("Viewer.extents ? Viewer.extents.z : null")


# One control per family: the parameter to move, the unit it should carry,
# and what the kernel should measure afterwards.
#
# `measure` is "xlen", "zlen" or "volume" - whichever the parameter actually
# governs. A spring's coil count is the reason that is a field and not an
# assumption: at a fixed free length, more coils is more wire, not a taller
# spring, so the bounding box is unchanged and the volume is not.
#
# `becomes` computes the expected value from the part's own geometry where
# there is a rule worth stating; None means only that it has to change.
FAMILIES = [
    ("a 20 tooth spur gear, module 2", "teeth_number", 28,
     {"unit": "", "measure": "xlen", "becomes": lambda v: 2 * (v + 2)}),
    ("an M8 flat washer", "outer_diameter", 22,
     {"unit": "mm", "measure": "xlen", "becomes": lambda v: v}),
    ("a 6203 bearing", "outer_diameter", 45,
     {"unit": "mm", "measure": "xlen", "becomes": lambda v: v}),
    ("an M8x30 socket head cap screw", "length", 45,
     {"unit": "mm", "measure": "zlen", "becomes": None}),
    ("a GT2 timing pulley with 20 teeth", "face_width", 12,
     {"unit": "mm", "measure": "zlen", "becomes": lambda v: v}),
    ("a compression spring, 2mm wire, 20mm od, 50mm long", "active_coils", 12,
     {"unit": "", "measure": "volume", "becomes": None}),
    ("a 4mm dowel pin, 20mm long", "length", 28,
     {"unit": "mm", "measure": "zlen", "becomes": lambda v: v}),
]


def measured(page, what: str):
    """What the kernel reported for the version on screen.

    The kernel's own numbers rather than the viewer's: the mesh is a
    triangulation of the solid, and `volume` is not on it at all.
    """
    return page.evaluate("""what => {
        const v = S.versions[S.selected];
        const g = (v && v.geometry) || {};
        return what === 'volume' ? g.volume
                                 : ((g.bounding_box || {})[what]);
    }""", what)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8077")
    parser.add_argument("--out", default="/tmp/cadsmith_params")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=executable(),
            args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": 1600, "height": 950})
        page = context.new_page()
        page.on("pageerror", lambda e: console.append(str(e)))
        page.on("console", lambda m: console.append(m.text)
                if m.type == "error" else None)
        page.goto(args.url, wait_until="networkidle")
        page.wait_for_timeout(1200)

        # -----------------------------------------------------------------
        print("\nEvery panel in the right column is reachable")
        # Four panels sharing one column: each has to keep enough height to
        # show something, and when they cannot all fit, the column scrolls
        # rather than crushing one of them to its header.
        for height in (950, 800, 700, 620):
            page.set_viewport_size({"width": 1600, "height": height})
            page.wait_for_timeout(350)
            state = page.evaluate("""() => {
                const split = document.querySelector('.rsplit');
                // Whichever of the code panel's two views is showing.
                const shown = document.getElementById('codeView').hidden
                  ? 'paramsBody' : 'codeScroll';
                const body = id => document.getElementById(id).clientHeight;
                return {
                  crushed: ['thinkBody', 'planBody', shown, 'valBody']
                    .filter(id => body(id) < 40),
                  scrolls: split.scrollHeight > split.clientHeight + 1,
                  fits: split.scrollHeight <= split.clientHeight + 1,
                };
            }""")
            check(f"at {height}px, no panel is crushed",
                  not state["crushed"], ", ".join(state["crushed"]) or "none")
            check(f"at {height}px, the column fits or scrolls",
                  state["fits"] or state["scrolls"],
                  "scrolls" if state["scrolls"] else "fits")
        page.set_viewport_size({"width": 1600, "height": 950})
        page.wait_for_timeout(300)

        # A body with more content than height must be scrollable, not clipped.
        build(page, "an M8 flat washer")
        overflow = page.evaluate("""() =>
            ['thinkBody', 'planBody',
             document.getElementById('codeView').hidden ? 'paramsBody' : 'codeScroll',
             'valBody']
              .filter(id => {
                const el = document.getElementById(id);
                return el.scrollHeight > el.clientHeight + 1
                  && !['auto', 'scroll'].includes(getComputedStyle(el).overflowY);
              })""")
        check("a panel with more to show can be scrolled to it",
              not overflow, ", ".join(overflow) or "all scrollable")

        # -----------------------------------------------------------------
        print("\nThe code panel flips between two views")
        # Parameters first: the point of the default is that a part can be
        # adjusted without anyone being told there is Python behind it.
        check("it opens on the controls, not the source",
              page.locator("#codeView").is_hidden()
              and not page.locator("#paramsView").is_hidden())
        check("and the panel is named for them",
              "arameter" in page.locator("#codeHeading").inner_text()
              or "パラメータ" in page.locator("#codeHeading").inner_text(),
              page.locator("#codeHeading").inner_text())
        page.click("#viewCodeBtn")
        page.wait_for_timeout(400)
        check("Code shows the source, one click away",
              not page.locator("#codeView").is_hidden()
              and "cadquery" in page.locator("#codeScroll").inner_text().lower(),
              page.locator("#codeScroll").inner_text().replace("\n", " ")[:50])
        page.click("#viewParamsBtn")
        page.wait_for_timeout(400)

        found = {r["name"]: r for r in rows(page)}
        check("every dimension the script declares has a control",
              {"inner_diameter", "outer_diameter", "thickness"} == set(found),
              ", ".join(sorted(found)))
        check("each is labelled, measured and bracketed",
              all(r["label"] and r["unit"] == "mm"
                  and r["min"] <= r["value"] <= r["max"]
                  for r in found.values()),
              str(found.get("thickness")))
        page.screenshot(path=str(out / "params-view.png"))

        # -----------------------------------------------------------------
        print("\nDragging changes the source, letting go changes the part")
        before_z = zlen(page)
        before_versions = page.evaluate("S.versions.length")
        slider = page.locator(
            '#paramsBody .prow[data-name="thickness"] input[type=range]')
        box = slider.bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.2,
                        box["y"] + box["height"] / 2)
        page.mouse.down()
        for fraction in (0.3, 0.4, 0.5, 0.6):
            page.mouse.move(box["x"] + box["width"] * fraction,
                            box["y"] + box["height"] / 2)
            page.wait_for_timeout(60)

        dragged = next(r for r in rows(page) if r["name"] == "thickness")
        check("the value moved", abs(dragged["value"] - 2.0) > 0.1,
              f"thickness {dragged['value']}")
        shown = code_line(page, "thickness")
        check("the source shows it while the slider is still held",
              shown.startswith("thickness = ")
              and abs(float(shown.split("=")[1]) - dragged["value"]) < 1e-9,
              shown or "(no assignment on screen)")
        check("the control says it is ahead of the part", dragged["dirty"])
        check("but nothing was rebuilt yet",
              page.evaluate("S.versions.length") == before_versions
              and zlen(page) == before_z,
              f"{page.evaluate('S.versions.length')} version(s)")
        page.screenshot(path=str(out / "params-dragging.png"))

        page.mouse.up()
        page.wait_for_timeout(400)
        check("letting go starts a rebuild", page.evaluate("S.paramBusy"))
        page.wait_for_function("() => S.busy === false", timeout=180000)
        page.wait_for_timeout(1200)

        check("one new version, not one per frame of the drag",
              page.evaluate("S.versions.length") == before_versions + 1,
              f"{page.evaluate('S.versions.length')} version(s)")
        check("the kernel built the thickness that was set",
              abs(zlen(page) - dragged["value"]) < 0.05,
              f"{zlen(page):.2f} vs {dragged['value']:g}")
        settled = next(r for r in rows(page) if r["name"] == "thickness")
        check("and the control now agrees with the part",
              abs(settled["value"] - dragged["value"]) < 1e-6
              and not settled["dirty"], str(settled["value"]))
        page.screenshot(path=str(out / "params-rebuilt.png"))

        # -----------------------------------------------------------------
        print("\nThe number field is the other way in")
        field = page.locator(
            '#paramsBody .prow[data-name="outer_diameter"] .prow-num')
        field.fill("24")
        check("typing moves the slider with it",
              page.evaluate("""() => parseFloat(document.querySelector(
                  '#paramsBody .prow[data-name="outer_diameter"] input[type=range]').value)""") == 24)
        field.press("Enter")
        page.wait_for_function("() => S.busy === false", timeout=180000)
        page.wait_for_timeout(1200)
        extents = page.evaluate(
            "Viewer.extents ? [Viewer.extents.x, Viewer.extents.y] : null")
        check("and the kernel built that too",
              extents and abs(extents[0] - 24.0) < 0.05,
              f"{extents[0]:.2f} mm across" if extents else "no geometry")

        # -----------------------------------------------------------------
        print("\nA value the kernel cannot use is refused, not built")
        versions_before = page.evaluate("S.versions.length")
        field = page.locator(
            '#paramsBody .prow[data-name="thickness"] .prow-num')
        field.fill("0")
        field.press("Enter")
        page.wait_for_timeout(1500)
        check("zero is not sent as a dimension",
              page.evaluate("S.versions.length") == versions_before,
              f"{page.evaluate('S.versions.length')} version(s)")
        check("and the part on screen is untouched",
              zlen(page) is not None and zlen(page) > 0,
              f"{zlen(page):.2f} mm thick")

        # -----------------------------------------------------------------
        print("\nThe choice of view is remembered")
        page.click("#viewCodeBtn")
        page.wait_for_timeout(300)
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(1500)
        check("choosing Code survives a reload",
              page.evaluate("S.paramView") == "code"
              and not page.locator("#codeView").is_hidden(),
              page.evaluate("S.paramView"))
        page.click("#viewParamsBtn")
        page.wait_for_timeout(300)
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(1500)
        check("and so does choosing Parameters again",
              page.evaluate("S.paramView") == "params"
              and not page.locator("#paramsView").is_hidden(),
              page.evaluate("S.paramView"))

        # -----------------------------------------------------------------
        print("\nA part with no declared dimensions says so")
        page.evaluate("() => { S.params = []; S.jobId = 'x'; "
                      "S.versions = [{iteration: 0}]; renderParameters(); }")
        page.wait_for_timeout(300)
        check("it explains rather than showing an empty panel",
              len(page.locator("#paramsBody").inner_text().strip()) > 20,
              page.locator("#paramsBody").inner_text().replace("\n", " ")[:60])

        # -----------------------------------------------------------------
        # A shallow pass over every family, after the deep pass over one.
        # Each part's script is written differently, and the controls are
        # only as good as what they read out of it: this is what caught a
        # spring's `active_coils = 8.0` being labelled "8 mm".
        print("\nEvery family, one move each")
        for prompt, name, target, expect in FAMILIES:
            label = prompt[:32]
            build(page, prompt)
            row = page.locator(f'#paramsBody .prow[data-name="{name}"]')
            if row.count() == 0:
                check(f"{label}: {name} has a control", False,
                      "controls are " + ", ".join(page.evaluate(
                          """() => [...document.querySelectorAll('#paramsBody .prow')]
                               .map(r => r.dataset.name)""")))
                continue
            unit = row.locator(".prow-unit").inner_text()
            check(f"{label}: {name} is in {expect['unit'] or 'no unit'}",
                  unit == expect["unit"], f"'{unit}'")

            what = expect["measure"]
            before = measured(page, what)
            versions = page.evaluate("S.versions.length")
            field = row.locator(".prow-num")
            field.fill(str(target))
            field.press("Enter")
            page.wait_for_function(
                "() => S.busy === false && S.paramLoading === false",
                timeout=180000)
            page.wait_for_timeout(600)
            after = measured(page, what)
            grew = page.evaluate("S.versions.length") == versions + 1

            if expect["becomes"] is None:
                ok = (grew and after is not None and before
                      and abs(after - before) / before > 0.05)
                detail = f"{what} {before:.1f} -> {after:.1f}"
            else:
                want = expect["becomes"](target)
                ok = grew and after is not None and abs(after - want) < 0.6
                detail = f"{what} = {after:.2f}, expected {want:g}"
            check(f"{label}: moving {name} rebuilt it", ok, detail)

        print("\nConsole")
        real = js_errors()
        check("no JavaScript errors", not real, "; ".join(real[:3]))

        print(f"\nScreenshots in {out}")
        browser.close()

    print("=" * 60)
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED:")
        for name in failures:
            print(f"   - {name}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
