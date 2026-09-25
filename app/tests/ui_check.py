"""Drive the real frontend in a browser and report what it renders.

Loads the page against a running server, opens a recorded run, and checks
that the panels are populated from backend data - the design plan, the
kernel-measured facts, the Judge's verdict, the iteration timeline and the
STL actually reaching the WebGL canvas.  Screenshots are written for review.

Usage:
    .venv/bin/python -m app.tests.ui_check [--url http://127.0.0.1:8077] [--out DIR]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DEFAULT_URL = "http://127.0.0.1:8077"

# Prefer a Chromium already on the machine over one Playwright would fetch;
# the pinned browser build and the installed client version need not agree.
_CANDIDATE_BROWSERS = [
    "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
    "/opt/pw-browsers/chromium/chrome-linux/chrome",
]


def settings(page):
    """Open the composer's settings menu if it is shut.

    Provider, both model ids, the iteration count and a pasted key moved
    behind the kebab beside the prompt, so a test that sets one opens it
    the way a person does.
    """
    if page.locator("#moreMenu").is_hidden():
        page.click("#moreBtn")
    page.wait_for_selector("#moreMenu:not([hidden])", timeout=5000)
    page.wait_for_timeout(120)


def _executable_path() -> str | None:
    for candidate in _CANDIDATE_BROWSERS:
        if Path(candidate).exists():
            return candidate
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--out", default="/tmp/cadsmith_ui")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # Record a fresh two-iteration run and drive the test against that exact
    # job. Reusing whatever happens to be in app/runs made the test depend on
    # earlier runs of itself, which had already added an edit version.
    print("\nRecording a run to test against")
    from app.server.jobs import JobManager
    from app.tools.seed_demo_run import RUNS_DIR, seed

    job_id = seed("bracket", JobManager(RUNS_DIR))

    failures: list[str] = []
    console_errors: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
        if not ok:
            failures.append(label)

    with sync_playwright() as pw:
        executable = _executable_path()
        browser = pw.chromium.launch(
            executable_path=executable,
            args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"],
        )
        page = browser.new_page(viewport={"width": 1600, "height": 950},
                                accept_downloads=True)
        page.on("console", lambda m: console_errors.append(m.text)
                if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))
        page.on("requestfailed",
                lambda r: console_errors.append(f"request failed: {r.url}"))
        page.on("response", lambda r: console_errors.append(
            f"HTTP {r.status}: {r.url}") if r.status >= 400 else None)

        print("\nPage load")
        page.goto(args.url, wait_until="networkidle")
        page.wait_for_timeout(1500)
        check("title", "CADSmith" in page.title(), page.title())
        check("three.js loaded", page.evaluate("typeof THREE !== 'undefined'"))
        check("viewer initialised", page.evaluate("typeof Viewer !== 'undefined'"))
        check("canvas present", page.locator("#gl canvas").count() == 1)

        # The chip is only on screen when it has something to report. Here
        # there is no model backend, so it should be showing and saying so;
        # the ready state is checked further down, where it is hidden.
        health = page.locator("#healthChip span").inner_text()
        check("the chip reports a state", health not in ("", "CHECKING…"), health)
        check("and only shows itself when there is something to say",
              page.evaluate("() => !S.health.ok")
              == (not page.locator("#healthChip").is_hidden()),
              f'ok={page.evaluate("() => S.health.ok")}, '
              f'shown={not page.locator("#healthChip").is_hidden()}')
        check("benchmark prompts listed",
              page.locator("#samples .sample").count() > 0,
              f"{page.locator('#samples .sample').count()} prompts")
        page.screenshot(path=str(out / "01-empty.png"))

        # A pixel ratio the machine running this does not have. The canvas is
        # transparent and is the one element sized in script rather than by
        # the layout, so at 2x it used to lay out at twice the stage: the
        # model's grid painted across the right-hand cards - which reads as
        # the panels being see-through - and clicks meant for a slider
        # landing on the canvas instead. None of it shows at 1x, which is
        # why it is measured rather than looked at.
        print("\nOn a 2x display")
        retina = browser.new_page(viewport={"width": 1600, "height": 950},
                                  device_scale_factor=2)
        retina.goto(args.url, wait_until="networkidle")
        retina.wait_for_timeout(1200)
        fit = retina.evaluate("""() => {
          const host = document.querySelector('#gl');
          const canvas = host.querySelector('canvas');
          const stage = host.getBoundingClientRect();
          const drawn = canvas.getBoundingClientRect();
          const rail = document.querySelector('.col.right').getBoundingClientRect();
          const over = document.elementFromPoint(rail.left + rail.width / 2,
                                                 rail.top + 120);
          return {canvas: [Math.round(drawn.width), Math.round(drawn.height)],
                  stage: [Math.round(stage.width), Math.round(stage.height)],
                  buffer: [canvas.width, canvas.height],
                  onTop: over ? over.tagName : null};
        }""")
        check("the canvas is laid out at the size of the stage",
              fit["canvas"] == fit["stage"], f'{fit["canvas"]} vs {fit["stage"]}')
        check("and still renders at the display's own resolution",
              fit["buffer"] == [fit["stage"][0] * 2, fit["stage"][1] * 2],
              str(fit["buffer"]))
        check("so the viewport does not paint over the right-hand rail",
              fit["onTop"] != "CANVAS", f'{fit["onTop"]} is on top of the rail')
        retina.close()

        print("\nModel backend picker")
        options = page.evaluate(
            "[...document.querySelectorAll('#optProvider option')].map(o => o.value)")
        for wanted in ("anthropic", "openai", "ollama", "lmstudio", "custom"):
            check(f"{wanted} offered", wanted in options, str(options))
        check("a provider is selected", bool(page.locator("#optProvider").input_value()))
        check("unconfigured providers say so",
              "needs setup" in page.evaluate(
                  "[...document.querySelectorAll('#optProvider option')]"
                  ".map(o => o.textContent).join('|')"))

        settings(page)
        page.select_option("#optProvider", "ollama")
        page.wait_for_timeout(500)
        note = page.locator("#providerNote").inner_text()
        check("an unreachable local provider is reported honestly",
              "Nothing is listening" in note, note[:70])
        check("generate stays available - the catalogue needs no backend",
              not page.locator("#genBtn").is_disabled())
        check("and the note says why it is still available",
              "catalogue" in note.lower(), note[:120])
        check("the key field appears when setup is needed",
              page.locator("#keyRow").is_visible())

        settings(page)
        page.select_option("#optProvider", "custom")
        page.wait_for_timeout(400)
        check("a custom backend exposes its base URL",
              page.locator("#providerBase").is_visible())

        settings(page)
        page.select_option("#optProvider", "anthropic")
        page.wait_for_timeout(400)
        check("model roles are prefilled per provider",
              page.locator("#optGenModel").input_value()
              != page.locator("#optJudgeModel").input_value(),
              f'{page.locator("#optGenModel").input_value()} / '
              f'{page.locator("#optJudgeModel").input_value()}')

        # Configure a backend through the UI, which is also how a key gets in.
        settings(page)
        page.select_option("#optProvider", "custom")
        page.wait_for_timeout(400)
        page.fill("#providerBase", "http://127.0.0.1:9/v1")
        page.fill("#providerKey", "ui-entered-key")
        page.click("#saveKeyBtn")
        page.wait_for_timeout(1200)
        check("the provider becomes usable once configured",
              "needs setup" not in page.evaluate(
                  "document.querySelector('#optProvider')"
                  ".selectedOptions[0].textContent"),
              page.evaluate("document.querySelector('#optProvider')"
                            ".selectedOptions[0].textContent"))
        check("the key field is cleared after use",
              page.locator("#providerKey").input_value() == "")
        # A row the script marks hidden has to actually go: an author
        # `display` beats the browser's own [hidden] rule whatever the
        # specificity, so the stylesheet has to say so for each such row.
        check("and the row goes away once a backend needs no setup",
              page.evaluate("""() => {
                  const el = document.querySelector('#keyRow');
                  const was = el.hidden;
                  el.hidden = true;
                  const shown = getComputedStyle(el).display;
                  el.hidden = was;
                  return shown;
              }""") == "none")

        check("a gateway with no declared default leaves the model empty",
              page.locator("#optGenModel").input_value() == "",
              page.locator("#optGenModel").input_value())
        settings(page)
        page.fill("#optGenModel", "same-model")
        page.fill("#optJudgeModel", "same-model")
        page.wait_for_timeout(400)
        check("using one model for both roles is flagged",
              "grades its own work" in page.locator("#providerNote").inner_text(),
              page.locator("#providerNote").inner_text()[:60])
        settings(page)
        page.fill("#optJudgeModel", "stronger-model")
        page.wait_for_timeout(400)
        check("a distinct judge model clears the warning",
              "grades its own work" not in page.locator("#providerNote").inner_text())
        check("the pane header names the judge model",
              "STRONGER-MODEL" in page.locator("#judgeModelLabel").inner_text(),
              page.locator("#judgeModelLabel").inner_text())
        page.screenshot(path=str(out / "12-providers.png"))

        print("\nReasoning effort")
        # The picker is worth having only where the parameter exists, so it
        # follows the chosen backend rather than sitting there inert.
        check("no picker for a backend with no effort parameter",
              page.locator("#effortRow").is_hidden())
        settings(page)
        page.select_option("#optProvider", "anthropic")
        page.wait_for_timeout(400)
        check("and it is on screen for a Claude backend",
              page.locator("#effortRow").is_visible())
        levels = page.evaluate(
            "[...document.querySelectorAll('#optEffort option')].map(o => o.value)")
        check("the levels come from the server, cheapest first",
              levels == ["low", "medium", "high"], str(levels))
        check("it opens on the level the API applies anyway",
              page.locator("#optEffort").input_value() == "high",
              page.locator("#optEffort").input_value())
        check("the fast one says so, so nobody has to guess",
              "fastest" in page.evaluate(
                  "document.querySelector('#optEffort option').textContent").lower(),
              page.evaluate(
                  "document.querySelector('#optEffort option').textContent"))
        page.select_option("#optEffort", "low")
        page.wait_for_timeout(200)
        check("choosing a level sticks",
              page.locator("#optEffort").input_value() == "low")
        settings(page)
        page.select_option("#optProvider", "custom")
        page.wait_for_timeout(400)
        page.select_option("#optProvider", "anthropic")
        page.wait_for_timeout(400)
        check("and survives a trip through another backend",
              page.locator("#optEffort").input_value() == "low",
              page.locator("#optEffort").input_value())
        page.select_option("#optEffort", "high")
        settings(page)
        page.select_option("#optProvider", "custom")
        page.wait_for_timeout(400)

        print("\nEnvironment panel")
        # Reachable from the settings menu whether or not the chip is up -
        # the chip used to be the only way in, and it is usually hidden now.
        settings(page)
        page.click("#optDiag")
        page.wait_for_timeout(400)
        check("diagnostics open from the settings menu",
              page.locator("#diag").is_visible())
        check("all checks listed", page.locator("#diag .drow").count() >= 4,
              f"{page.locator('#diag .drow').count()} rows")
        page.screenshot(path=str(out / "02-diagnostics.png"))
        page.keyboard.press("Escape")

        print("\nRecorded run")
        page.click("#histBtn")
        page.wait_for_timeout(900)
        runs = page.locator("#hlist .hitem")
        check("history lists runs", runs.count() > 0, f"{runs.count()} runs")
        page.screenshot(path=str(out / "03-history.png"))

        target = page.locator(f'#hlist .hitem[data-job="{job_id}"]')
        check("the run just recorded is listed", target.count() == 1, job_id)
        target.click()
        page.wait_for_timeout(3000)

        print("\nLoaded model")
        check("viewer has geometry",
              page.evaluate("Viewer.extents !== null && Viewer.extents !== undefined"))
        extents = page.evaluate(
            "Viewer.extents ? [Viewer.extents.x, Viewer.extents.y, Viewer.extents.z] : null")
        check("STL parsed to the right size",
              extents is not None and abs(extents[0] - 100) < 0.5
              and abs(extents[2] - 55) < 0.5,
              f"{[round(v, 1) for v in extents] if extents else None}")

        facts = page.locator("#mfacts").inner_text()
        check("kernel facts shown", "WATERTIGHT" in facts, facts.replace("\n", " ")[:90])

        plan = page.locator("#planBody").inner_text()
        check("design plan populated", "base plate" in plan.lower(),
              plan.replace("\n", " ")[:70])

        # A plan is model output and not every field in it is a number:
        # `symmetry` is free text in the schema. Rounding a sentence gave
        # NaN, and the panel printed it as though it were the answer.
        check("no plan field prints as NaN",
              "NaN" not in plan, plan.replace("\n", " ")[:120])

        # The rail is the conversation, so a run opened from History opens
        # with what was asked - the same as a live one - rather than putting
        # the old prompt in the box that now means "change this part".
        check("a loaded run shows the question it answered",
              not page.locator("#askTurn").is_hidden()
              and len(page.locator("#askText").inner_text()) > 10,
              page.locator("#askText").inner_text()[:60])
        check("and the composer is empty, ready for a change",
              page.locator("#prompt").input_value() == "",
              repr(page.locator("#prompt").input_value()))

        code = page.locator("#hl").inner_text()
        check("real CadQuery source shown", "import cadquery" in code)
        check("code is the refined version", "support_height + base_thickness" in code)
        # A chained-replace highlighter corrupts its own markup; make sure the
        # rendered text carries no leaked class attributes.
        check("syntax highlighting is not corrupted",
              'class="' not in code and '">' not in code,
              next((line for line in code.splitlines() if '">' in line), ""))
        check("comments survive highlighting", "# Base plate" in code,
              code.splitlines()[6] if len(code.splitlines()) > 6 else "")

        verdict = page.locator("#valBody").inner_text()
        check("judge verdict shown", "Accepted by the Judge" in verdict)
        check("three-view render displayed",
              page.locator("#rthumb").count() == 1)

        iters = page.locator("#iters .iter")
        check("iteration timeline built", iters.count() == 2, f"{iters.count()} cards")
        page.screenshot(path=str(out / "04-loaded.png"))

        print("\nComparing iterations")
        iters.first.click()
        page.wait_for_timeout(2500)
        first_extents = page.evaluate(
            "Viewer.extents ? [Viewer.extents.x, Viewer.extents.y, Viewer.extents.z] : null")
        check("first attempt loads its own geometry",
              first_extents is not None and abs(first_extents[2] - 45) < 0.5,
              f"z={round(first_extents[2], 1) if first_extents else None} (rejected attempt was 45mm)")
        rejected = page.locator("#valBody").inner_text()
        check("first attempt shows the rejection",
              "Rejected by the Judge" in rejected)
        page.screenshot(path=str(out / "05-rejected-iteration.png"))

        print("\nNatural-language edit (parameter patch, no API key needed)")
        # An edit applies to the version on screen, so select one explicitly
        # rather than relying on whichever was left selected.
        page.click('.iter[data-i="0"]')
        page.wait_for_timeout(2200)
        # Length is unambiguous: in this attempt the walls stand 45mm from
        # z=0, so thickening the base would not change the overall height.
        before = page.evaluate("Viewer.extents.x")
        page.fill("#prompt", "make the base length 140mm")
        page.click("#genBtn")
        page.wait_for_function(
            "() => document.querySelectorAll('#iters .iter').length === 3",
            timeout=180000)
        page.wait_for_timeout(2500)
        check("an edit version appears",
              page.locator("#iters .iter").count() == 3)
        labels = page.evaluate(
            "[...document.querySelectorAll('#iters .iter .ilabel')].map(e => e.textContent.trim())")
        # A parameter change is the next iteration of the same part, not a
        # separate kind of history entry, so the strip counts straight on.
        check("it is numbered on from the last one, not called an edit",
              all("EDIT" not in l.upper() for l in labels)
              and sum("ITER" in l.upper() for l in labels) >= 2,
              str(labels))
        after = page.evaluate("Viewer.extents.x")
        check("the kernel rebuilt it at the new length",
              abs(before - 100.0) < 0.5 and abs(after - 140.0) < 0.5,
              f"{round(before, 1)}mm -> {round(after, 1)}mm")
        code_now = page.locator("#hl").inner_text()
        check("the patched source is shown",
              "base_length = 140.0" in code_now,
              next((l for l in code_now.splitlines()
                    if "base_length" in l), ""))
        check("the edit was applied to the selected attempt, not the newest",
              "support_height + base_thickness" not in code_now)
        verdict_now = page.locator("#valBody").inner_text()
        check("a patch is not credited to the Judge",
              "Judge" not in verdict_now.split("\n")[0],
              verdict_now.split("\n")[0])
        check("it says the Judge was not re-run",
              "JUDGE NOT RE-RUN" in verdict_now)
        page.screenshot(path=str(out / "09-edited.png"))

        print("\nEngineering drawing")
        page.click('.iter[data-i="1"]')
        page.wait_for_timeout(2000)
        page.click('#viewSeg .vsegb[data-view="drawing"]')
        page.wait_for_selector("#paper svg", timeout=90000)
        page.wait_for_timeout(600)
        check("sheet opens", page.locator("#sheet.on").count() == 1)
        # SVG <text> has no innerText; read textContent from the DOM instead.
        labels = page.evaluate(
            "[...document.querySelectorAll('#paper svg text')].map(t => t.textContent)")
        for view in ("FRONT", "VIEW FROM ABOVE", "VIEW FROM LEFT", "ISOMETRIC"):
            check(f"{view} projected", view in labels)
        check("title block carries the measured size",
              any("100 x 60 x 55" in t for t in labels),
              next((t for t in labels if " x " in t), ""))
        check("the sheet states its scale",
              any(re.fullmatch(r"\d+:\d+", t or "") for t in labels),
              next((t for t in labels
                    if re.fullmatch(r"\d+:\d+", t or "")), "none"))
        check("and which projection it is drawn in",
              "PROJECTION" in labels
              and page.locator("#paper svg circle").count() == 2,
              f'{page.locator("#paper svg circle").count()} symbol circle(s)')
        check("projection geometry present",
              page.locator("#paper svg polyline").count() > 8,
              f'{page.locator("#paper svg polyline").count()} polylines')
        # The DXF is the drawing rather than a picture of it, so the button
        # has to be there and has to hand back a file a CAD can open.
        with page.expect_download(timeout=120000) as caught:
            page.click("#expDxf")
        download = caught.value
        saved = out / "sheet.dxf"
        download.save_as(str(saved))
        body = saved.read_text(encoding="utf-8", errors="replace")
        check("the sheet downloads as DXF",
              saved.stat().st_size > 10000 and "DIMENSION" in body,
              f"{saved.stat().st_size} bytes, "
              f"{body.count('DIMENSION')} dimension record(s)")

        check("the whole sheet fits the panel",
              page.evaluate("""() => {
                  const s = document.querySelector('.sheet-scroll');
                  return s.scrollHeight <= s.clientHeight + 1;
              }"""))
        page.screenshot(path=str(out / "08-drawing.png"))
        page.click("#back3d")
        page.wait_for_timeout(400)

        print("\nReplay")
        page.click("#histBtn")
        page.wait_for_timeout(600)
        replay_buttons = page.locator("#hlist .hreplay")
        rows = page.locator("#hlist .hrow")
        check("every run offers a replay",
              rows.count() > 0 and replay_buttons.count() == rows.count(),
              f"{replay_buttons.count()} buttons for {rows.count()} runs")
        # Replay the two-iteration run: the last row is the oldest.
        row = page.locator(f'#hlist .hrow:has(.hitem[data-job="{job_id}"])')
        check("the recorded run can be replayed", row.count() == 1)
        row.locator(".hreplay").click()
        page.wait_for_timeout(1200)
        check("the header marks it as a replay",
              "REPLAY" in page.locator("#enginePill").inner_text(),
              page.locator("#enginePill").inner_text())
        page.screenshot(path=str(out / "10-replaying.png"))

        # The run has three versions by now: two iterations plus the edit.
        page.wait_for_function(
            "() => document.querySelectorAll('#iters .iter').length === 3",
            timeout=180000)
        page.wait_for_timeout(2500)
        check("the replay reproduced every version",
              page.locator("#iters .iter").count() == 3)
        page.click('.iter[data-i="1"]')
        page.wait_for_timeout(2200)
        replay_extents = page.evaluate(
            "Viewer.extents ? [Viewer.extents.x, Viewer.extents.z] : null")
        check("replayed geometry matches the original",
              replay_extents is not None
              and abs(replay_extents[0] - 100) < 0.5
              and abs(replay_extents[1] - 55) < 0.5,
              str([round(v, 1) for v in replay_extents] if replay_extents else None))
        replay_verdict = page.locator("#valBody").inner_text()
        check("the original Judge text is replayed",
              "Accepted by the Judge" in replay_verdict)
        page.screenshot(path=str(out / "11-replay-done.png"))

        print("\nViews")
        # The gizmo lives in the viewport, and by now the run has been
        # through the code view and the drawing. Come back to the model
        # first, the way a person would before reaching for a view control.
        if page.locator("#sheet.on").count():
            page.click("#back3d")
        page.click('#viewSeg .vsegb[data-view="model"]')
        page.wait_for_timeout(400)
        # The model spins by default, and the gizmo turns with the camera,
        # so nothing in the viewport holds still enough to be clicked. Stop
        # it first - which is what the chip is for.
        if page.evaluate("() => Viewer.spin"):
            page.click("#spinBtn")
            page.wait_for_timeout(400)
        page.click('#axes .axhit[data-view="front"]')
        page.wait_for_timeout(900)
        page.screenshot(path=str(out / "06-front-view.png"))
        page.click("#wireBtn")
        page.wait_for_timeout(600)
        page.screenshot(path=str(out / "07-wireframe.png"))
        page.click("#wireBtn")

        print("\nThe left rail is one panel, not a stack of them")
        shape = page.evaluate("""() => {
          const rail = document.querySelector('#rail');
          const cs = el => getComputedStyle(el);
          const inner = [];
          rail.querySelectorAll('*').forEach(el => {
            const o = cs(el).overflowY;
            if ((o === 'auto' || o === 'scroll')
                && el.scrollHeight > el.clientHeight + 4)
              inner.push(el.id || el.className);
          });
          return {
            innerScrollers: inner,
            planBg: cs(document.querySelector('#planBody')).backgroundColor,
            thinkBg: cs(document.querySelector('#thinkBody')).backgroundColor,
            headingLines: Math.round(
              document.querySelector('#planSec .eyebrow')
                      .getBoundingClientRect().height),
          };
        }""")
        check("the thread and the reasoning share one scroll",
              page.locator("#rail").count() == 1
              and not shape["innerScrollers"], str(shape["innerScrollers"]))
        check("the plan reads as text, not as an inset box",
              shape["planBg"] in ("rgba(0, 0, 0, 0)", "transparent"),
              shape["planBg"])
        check("and so does the reasoning",
              shape["thinkBg"] in ("rgba(0, 0, 0, 0)", "transparent"),
              shape["thinkBg"])
        check("a long model id does not break the heading onto two lines",
              shape["headingLines"] < 20, f'{shape["headingLines"]}px tall')

        # The reason the rail has to be one scroll and the composer pinned:
        # five agents on a hard part run to tens of thousands of characters,
        # and that has to push past without taking the prompt off screen.
        def stream(count):
            page.evaluate("""(count) => {
              const line = 'Working through the wall thickness and the fillet '
                         + 'radius against the bore, and what that leaves. ';
              ['planner', 'coder', 'judge'].forEach(agent => {
                for (let i = 0; i < count; i++)
                  thinkAppend(agent, 0, 'thinking', line + i + '\\n');
              });
            }""", count)
            page.wait_for_timeout(500)

        # A reader watching the run is at the bottom, so the stream follows.
        page.evaluate("() => { const r = $('#rail'); r.scrollTop = r.scrollHeight; }")
        page.wait_for_timeout(200)
        stream(60)
        flow = page.evaluate("""() => {
          const rail = document.querySelector('#rail');
          const composer = document.querySelector('.composer');
          const inner = [];
          rail.querySelectorAll('*').forEach(el => {
            const o = getComputedStyle(el).overflowY;
            if ((o === 'auto' || o === 'scroll')
                && el.scrollHeight > el.clientHeight + 4)
              inner.push(el.id || el.className);
          });
          return {railScrolls: rail.scrollHeight > rail.clientHeight + 4,
                  innerScrollers: inner,
                  gap: Math.round(rail.scrollHeight - rail.scrollTop
                                  - rail.clientHeight),
                  atBottom: rail.scrollHeight - rail.scrollTop
                            - rail.clientHeight < 80,
                  top: Math.round(rail.scrollTop),
                  composerOnScreen: composer.getBoundingClientRect().bottom
                                    <= window.innerHeight + 1,
                  chars: document.querySelector('#thinkBody').innerText.length};
        }""")
        check("a long run makes the one rail scroll",
              flow["railScrolls"], f'{flow["chars"]} characters shown')
        check("and still nothing scrolls inside it",
              not flow["innerScrollers"], str(flow["innerScrollers"]))
        # It used to stop following the moment an agent spoke its first
        # line: the check for "is the reader at the bottom" was made after
        # the text went in, and a newly inserted agent block is taller than
        # the threshold, so the answer was always no from then on.
        check("it follows the stream to the bottom", flow["atBottom"],
              f'{flow["gap"]}px from the foot, at {flow["top"]}')
        check("the composer never leaves the screen",
              flow["composerOnScreen"])

        # But a reader who has scrolled back to read something is not yanked
        # away from it by the next thing the model says.
        page.evaluate("() => { $('#rail').scrollTop = 0; }")
        page.wait_for_timeout(200)
        stream(20)
        held = page.evaluate("() => Math.round($('#rail').scrollTop)")
        check("and a reader who scrolled up is left where they were",
              held < 120, f"scrollTop {held}")
        page.screenshot(path=str(out / "12-rail-flow.png"))

        print("\nThe composer grows with what is typed")
        one_line = page.evaluate(
            "() => Math.round($('#prompt').getBoundingClientRect().height)")
        page.fill("#prompt", "\n".join(
            f"line {i}: an L bracket, 60 by 40 by 6mm, 5mm fillet"
            for i in range(14)))
        page.wait_for_timeout(250)
        grown = page.evaluate(
            "() => Math.round($('#prompt').getBoundingClientRect().height)")
        check("a long prompt grows the box", grown > one_line + 40,
              f"{one_line} -> {grown}")
        check("but it stops before eating the rail, and scrolls instead",
              grown <= 205 and page.evaluate(
                  "() => { const b = $('#prompt'); "
                  "return b.scrollHeight > b.clientHeight + 2; }"),
              f"{grown}px")
        page.fill("#prompt", "")
        page.wait_for_timeout(300)
        shrunk = page.evaluate(
            "() => Math.round($('#prompt').getBoundingClientRect().height)")
        # Not back to exactly where it started: an empty textarea is sized to
        # its placeholder, and the edit hint is three lines where the first
        # prompt's is two. That is the behaviour wanted - the hint is what
        # the box is for when it is empty - so the check is that the rail
        # gets its room back, not that the number matches.
        check("and it gives the room back when the text goes",
              shrunk < grown - 100 and shrunk <= 90,
              f"{grown} -> {shrunk} (started at {one_line})")

        print("\nConsole")
        real_errors = [e for e in console_errors if "favicon" not in e.lower()]
        check("no JavaScript errors", not real_errors,
              "; ".join(real_errors[:3]))

        browser.close()

    print(f"\nScreenshots in {out}")
    print("=" * 58)
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED: {', '.join(failures)}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
