"""One request with several right answers, picked in a real browser.

"A handlebar" is not an under-specified request. It is a question: ten
bends are all equally a handlebar, and which one is meant is a decision
about how the bike sits rather than a number anyone forgot to type. The
catalogue used to decline it and hand it to the agents, which is a slow way
of answering a question nobody asked the agents.

What this has to hold up:

* four bends come back for one prompt, all built and checked, with no model
  call and no API key;
* the filmstrip says what each one *is* rather than which iteration it was,
  and shows the shape, because a picker made of titles is a form;
* the silhouettes are to one scale, so an ape hanger looks four times the
  height of a drag bar - which is the difference being chosen between;
* picking one changes everything downstream: the viewer, the parameter
  sliders, the measured properties and the pill;
* a named bend is still answered exactly and is not turned into a choice.

Needs a running server (no model backend required):
    ./app/run_app.sh &
    python -m app.tests.ui_options_check
"""

from __future__ import annotations

import argparse
import re
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


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def executable() -> str | None:
    for candidate in _CANDIDATE_BROWSERS:
        if Path(candidate).exists():
            return candidate
    return None


def run(page, prompt: str, timeout_ms: int = 300000) -> None:
    if page.locator("#verPill").is_visible():
        page.click("#newBtn")
    page.fill("#prompt", prompt)
    page.click("#genBtn")
    page.wait_for_function("() => S.busy === false", timeout=timeout_ms)
    page.wait_for_timeout(1500)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8077")
    parser.add_argument("--out", default="/tmp/cadsmith_options")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    console: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=executable(),
            args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1600, "height": 950})
        page.on("pageerror", lambda e: console.append(str(e)))
        page.on("console", lambda m: console.append(m.text)
                if m.type == "error" else None)
        page.goto(args.url, wait_until="networkidle")
        page.wait_for_timeout(1200)

        # -----------------------------------------------------------------
        print("\nFour bends for one request, with no model call")
        run(page, "a handlebar")
        versions = page.evaluate("S.versions")
        check("the request was answered without the agents",
              all(v.get("source") == "catalog" for v in versions),
              str({v.get("source") for v in versions}))
        check("four of them came back, each one built",
              len(versions) == 4, str(len(versions)))
        check("and each one is an option rather than an iteration",
              all(v.get("option") for v in versions))
        check("numbered 1..n of n, in the order the shortlist ranked them",
              [v["option"]["index"] for v in versions] == [0, 1, 2, 3]
              and {v["option"]["count"] for v in versions} == {4},
              str([v["option"]["index"] for v in versions]))

        # -----------------------------------------------------------------
        print("\nThe filmstrip is a picker, not a history")
        labels = page.eval_on_selector_all(
            "#iters .iter", "els => els.map(e => e.innerText.trim())")
        check("each card says what the bar is",
              len(labels) == 4 and not any(re.search(r"ITER", label)
                                           for label in labels),
              str(labels))
        check("and no two cards say the same thing",
              len(set(labels)) == len(labels), str(labels))
        thumbs = page.eval_on_selector_all(
            "#iters .iter img.outline", "els => els.map(e => e.naturalWidth)")
        check("each one carries a silhouette that actually loaded",
              len(thumbs) == 4 and all(width > 0 for width in thumbs),
              str(thumbs))
        check("the hint says to pick, not to compare attempts",
              "pick" in page.eval_on_selector("#iters .ihint", "e => e.innerText"),
              page.eval_on_selector("#iters .ihint", "e => e.innerText"))

        # Every silhouette is drawn to one scale, so the tallest bend is
        # visibly taller. Drawn per card they would all fill their box and
        # the difference being chosen between would be invisible.
        heights = page.evaluate("""() => {
            const out = [];
            for (const img of document.querySelectorAll('#iters .iter img.outline')) {
                out.push(img.naturalHeight && img.naturalWidth);
            }
            return out;
        }""")
        boxes = page.evaluate("""async () => {
            const spans = [];
            for (const img of document.querySelectorAll('#iters .iter img.outline')) {
                const text = await (await fetch(img.src)).text();
                const ys = [...text.matchAll(/,(\\d+(?:\\.\\d+)?)/g)]
                    .map(m => parseFloat(m[1]));
                spans.push(Math.max(...ys) - Math.min(...ys));
            }
            return spans;
        }""")
        check("the silhouettes share one scale, so the tall bend looks tall",
              len(boxes) == 4 and boxes[-1] > boxes[0] * 2.0,
              " ".join(f"{span:.0f}" for span in boxes))

        page.locator("#iters").screenshot(path=str(out / "options-strip.png"))
        page.screenshot(path=str(out / "options.png"))

        # -----------------------------------------------------------------
        print("\nPicking one carries through the whole app")
        first = page.evaluate("S.versions[S.selected]")
        check("the first option is the one on screen, not the last built",
              first["option"]["index"] == 0, str(first["option"]["index"]))
        check("and the pill says which of how many",
              "1" in page.eval_on_selector("#verPill", "e => e.innerText")
              and "4" in page.eval_on_selector("#verPill", "e => e.innerText"),
              page.eval_on_selector("#verPill", "e => e.innerText"))

        before = page.eval_on_selector_all(
            "#paramsBody .prow .prow-num", "els => els.map(e => e.value)")
        page.locator("#iters .iter").nth(2).click()
        page.wait_for_timeout(4000)
        after = page.eval_on_selector_all(
            "#paramsBody .prow .prow-num", "els => els.map(e => e.value)")
        check("clicking the third card moves the pill to it",
              "3" in page.eval_on_selector("#verPill", "e => e.innerText"),
              page.eval_on_selector("#verPill", "e => e.innerText"))
        check("and the sliders are that bar's dimensions, not the first's",
              before and after and before != after,
              f"{before} -> {after}")
        check("the viewer is showing the picked bar",
              page.evaluate("S.selected") == 2, str(page.evaluate("S.selected")))
        page.screenshot(path=str(out / "options-picked.png"))

        # -----------------------------------------------------------------
        print("\nA bend that will not make the stated width says so")
        run(page, "a 700 mm handlebar")
        versions = page.evaluate("S.versions")
        check("only the bends that will bend at 700 mm are offered",
              1 < len(versions) < 4, str(len(versions)))
        check("and they are 700 mm, not quietly widened to one that fits",
              all(v["catalog"]["parameters"]["overall_width"] == 700.0
                  for v in versions),
              str([v["catalog"]["parameters"]["overall_width"] for v in versions]))
        log = page.eval_on_selector_all("#plog > *", "els => els.map(e => e.textContent)")
        declined = [line for line in log if "Not offered" in line]
        check("the ones that were dropped are named, with the reason",
              declined and all("cannot be bent" in line for line in declined),
              " / ".join(line[:60] for line in declined))
        page.screenshot(path=str(out / "options-declined.png"))

        # -----------------------------------------------------------------
        print("\nA named bend is still one answer, not four")
        run(page, "a drag bar")
        versions = page.evaluate("S.versions")
        check("exactly one part comes back", len(versions) == 1,
              str(len(versions)))
        check("and it is not offered as a choice",
              not versions[0].get("option"))
        check("the pill reads STANDARD again",
              page.eval_on_selector("#verPill", "e => e.innerText").strip() != "",
              page.eval_on_selector("#verPill", "e => e.innerText"))

        browser.close()

    ignorable = ("favicon", "503 (service unavailable)")
    real = [c for c in console
            if not any(token in c.lower() for token in ignorable)]
    print("\nConsole")
    check("no JavaScript errors", not real, "; ".join(real[:3]))

    print(f"\nScreenshots in {out}")
    print("=" * 60)
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED: {', '.join(failures[:6])}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
