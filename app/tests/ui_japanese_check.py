"""Drive the whole app in Japanese, with a real model behind it.

``ui_lang_check`` proves the switch works: the interface redraws, the choice
survives a reload, a Japanese catalogue request is served.  What it never
does is *use* the app in Japanese - describe a part, watch the agents work,
change it, read the verdict, take the drawing.  Those panels are written
from model output and from run state, not from the dictionary, so they are
exactly where an English string survives unnoticed.

So this runs a Japanese session end to end against whatever backend is
configured, and checks at every stop that nothing English has leaked into a
place a Japanese reader is meant to read.

    .venv/bin/python -m app.tests.ui_japanese_check --url http://127.0.0.1:8077
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

CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿]")

#: A token nobody translates: a number, a unit, a designation, a model id,
#: a file format, a proper noun. Checked per token rather than per line so
#: that one identifier in a sentence does not excuse the sentence, and a
#: line made only of identifiers is not reported as untranslated prose.
_NUMERIC = re.compile(r"^[\d.,:%×xX/+\-()\[\]°·—–…]+$")
_IDENTIFIER = re.compile(r"^[A-Za-z][\w.\-]*[\d/][\w./\-]*$")
_NAMES = {
    "mm", "mm³", "mm3", "iso", "din", "step", "stl", "dxf", "png", "svg",
    "csv", "json", "py", "cad", "cadsmith", "en", "claude", "gpt", "qwen",
    "ollama", "anthropic", "openai", "bedrock", "amazon", "lm", "studio",
    "local", "compatible", "ok", "ng", "id", "url", "api", "no.", "a3",
}


def _translatable(token: str) -> bool:
    """True when a Latin token is prose someone should have translated."""
    bare = token.strip("()[]（）「」、。:：,.").lower()
    if not bare:
        return False
    if _NUMERIC.match(bare) or _IDENTIFIER.match(bare):
        return False
    return bare not in _NAMES


failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def executable() -> str | None:
    return next((b for b in _CANDIDATE_BROWSERS if Path(b).exists()), None)


def english_leaks(text: str) -> list[str]:
    """Lines of a Japanese panel that are still prose in English.

    A line counts as a leak when it carries no kana or kanji at all and
    holds at least one word that is not a number, a unit, a designation, a
    file format, a model id or a proper noun.
    """
    leaks = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line or CJK.search(line):
            continue
        if any(_translatable(token) for token in line.split()):
            leaks.append(line)
    return leaks


def to_japanese(page) -> None:
    page.click('#langSw [data-lang="ja"]')
    page.wait_for_timeout(700)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8077")
    parser.add_argument("--out", default="/tmp/cadsmith_ja")
    parser.add_argument("--base-url", default="",
                        help="OpenAI-compatible endpoint to run the agents on")
    parser.add_argument("--key", default="")
    parser.add_argument("--model", default="")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    console: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=executable(),
            args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": 1600, "height": 950},
                                accept_downloads=True)
        page.on("pageerror", lambda e: console.append(str(e)))
        page.on("console", lambda m: console.append(m.text)
                if m.type == "error" else None)
        page.goto(args.url, wait_until="networkidle")
        page.wait_for_timeout(1200)

        # ---------------------------------------------------------------
        print("\nThe interface, in Japanese and empty")
        to_japanese(page)
        page.screenshot(path=str(out / "01-empty.png"))
        # The language switch is excluded on purpose: 日本語 is the label of
        # the button that selects Japanese and stays Japanese in either
        # interface, exactly as EN stays Latin.
        # The language switch is excluded on purpose: 日本語 is the label of
        # the button that selects Japanese and stays Japanese in either
        # interface, exactly as EN stays Latin.
        def panel_text(selector: str) -> str:
            return page.evaluate("""(sel) => {
              const el = document.querySelector(sel).cloneNode(true);
              el.querySelectorAll('#langSw').forEach(n => n.remove());
              return el.innerText;
            }""", selector)

        for name, selector in (("the header", "header"),
                               ("the left rail", ".col.left"),
                               ("the right column", ".col.right"),
                               ("the viewport chips", ".vtools")):
            leaks = english_leaks(panel_text(selector))
            check(f"{name} is in Japanese", not leaks, "; ".join(leaks[:3]))

        check("the prompt asks in Japanese",
              CJK.search(page.get_attribute("#prompt", "placeholder") or ""),
              page.get_attribute("#prompt", "placeholder"))

        # ---------------------------------------------------------------
        print("\nA standard part, asked for in Japanese")
        page.fill("#prompt", "20歯 モジュール2 の平歯車")
        page.click("#genBtn")
        page.wait_for_function("() => S.busy === false && S.versions.length >= 1",
                               timeout=180000)
        page.wait_for_timeout(2000)
        check("it was served from the catalogue, not generated",
              page.evaluate("() => S.catalog !== null && S.catalog !== undefined"))
        check("the part is the gear that was asked for",
              abs((page.evaluate("Viewer.extents ? Viewer.extents.x : 0")) - 44.0)
              < 0.5, str(page.evaluate("Viewer.extents ? Viewer.extents.x : None")))
        for name, selector in (("the plan", "#planBody"),
                               ("the verdict", "#valBody"),
                               ("the measurements", "#mfacts")):
            leaks = english_leaks(page.locator(selector).inner_text())
            check(f"{name} is in Japanese", not leaks, "; ".join(leaks[:3]))
        page.screenshot(path=str(out / "02-catalogue.png"))

        # ---------------------------------------------------------------
        print("\nChanging it, in Japanese")
        page.fill("#prompt", "歯数を40にして")
        page.click("#genBtn")
        page.wait_for_function("() => S.busy === false && S.versions.length >= 2",
                               timeout=180000)
        page.wait_for_timeout(2000)
        check("the edit produced a new version",
              page.evaluate("S.versions.length") >= 2,
              str(page.evaluate("S.versions.length")))
        check("and the kernel really rebuilt it at 40 teeth",
              abs(page.evaluate("Viewer.extents.x") - 84.0) < 0.5,
              f'{page.evaluate("Viewer.extents.x"):.2f} mm across')
        leaks = english_leaks(page.locator("#iters").inner_text())
        check("the version strip is in Japanese", not leaks, "; ".join(leaks[:3]))
        page.screenshot(path=str(out / "03-edited.png"))

        # ---------------------------------------------------------------
        print("\nThe parameter controls, in Japanese")
        rows = page.locator("#paramsBody .prow").count()
        check("the controls are there", rows > 0, f"{rows} rows")
        # Deliberately exempt, and worth saying out loud rather than
        # quietly passing: a control's label is the identifier the script
        # assigns - `module`, `teeth_number` - and edits.py keeps it that way
        # so the value you drag is named the same as the line it rewrites.
        # The unit beside it is a symbol in either language. Printed so the
        # decision stays visible every time this suite runs.
        names = page.evaluate("""() => [...document.querySelectorAll('#paramsBody .prow-name')]
            .map(e => e.textContent.trim()).slice(0, 4)""")
        print(f"  ....  labels are the script's own identifiers, untranslated "
              f"by design: {', '.join(names)}")
        body = page.locator("#paramsBody").inner_text()
        header_line = body.splitlines()[0] if body.splitlines() else ""
        check("but the panel's own words are Japanese",
              not english_leaks(header_line), header_line)

        # ---------------------------------------------------------------
        print("\nThe drawing, in Japanese")
        page.click('#viewSeg .vsegb[data-view="drawing"]', timeout=120000)
        page.wait_for_function(
            "() => document.querySelector('#sheet') && "
            "document.querySelector('#sheet').innerHTML.includes('svg')",
            timeout=180000)
        page.wait_for_timeout(600)
        sheet = page.locator("#sheet").inner_text()
        check("a sheet was produced", len(sheet) > 0)
        check("and it is lettered in Japanese", bool(CJK.search(sheet)),
              sheet.replace("\n", " ")[:70])
        page.screenshot(path=str(out / "04-drawing.png"))
        page.click("#back3d")
        page.wait_for_timeout(600)

        # ---------------------------------------------------------------
        print("\nHistory, in Japanese")
        page.click("#histBtn")
        page.wait_for_timeout(900)
        # Only the panel's own words. Every row carries a prompt somebody
        # typed, and a prompt typed in English stays in English - it is what
        # was asked, not something for the dictionary to rewrite.
        chrome = page.evaluate("""() => {
          const panel = document.querySelector('#hist').cloneNode(true);
          panel.querySelectorAll('.hitem').forEach(row => row.remove());
          return panel.innerText;
        }""")
        leaks = english_leaks(chrome)
        check("the history panel's own words are Japanese", not leaks,
              "; ".join(leaks[:3]))
        dates = page.evaluate("""() => [...document.querySelectorAll('#hlist .htime')]
            .map(e => e.textContent.trim()).filter(Boolean).slice(0, 3)""")
        check("and its dates are written the Japanese way",
              all("AM" not in d and "PM" not in d for d in dates),
              "; ".join(dates) or "no dated rows")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # ---------------------------------------------------------------
        print("\nA part the catalogue cannot serve goes to the agents")
        if args.base_url:
            if page.locator("#moreMenu").is_hidden():
                page.click("#moreBtn")
            page.wait_for_selector("#moreMenu:not([hidden])", timeout=5000)
            page.select_option("#optProvider", "custom")
            page.wait_for_timeout(500)
            page.fill("#providerBase", args.base_url)
            page.fill("#providerKey", args.key or "x")
            page.click("#saveKeyBtn")
            page.wait_for_timeout(1800)
            if page.locator("#moreMenu").is_hidden():
                page.click("#moreBtn")
            page.wait_for_timeout(300)
            if args.model:
                page.fill("#optGenModel", args.model)
                page.fill("#optJudgeModel", args.model)
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

            page.click("#newBtn")
            page.wait_for_timeout(500)
            page.fill("#prompt", "一辺40mm、厚さ8mmの正方形の板。中央に直径10mmの穴。")
            page.click("#genBtn")
            page.wait_for_function("() => S.busy === false", timeout=300000)
            page.wait_for_timeout(2500)
            check("the agents produced a part",
                  page.evaluate("S.versions.length") >= 1,
                  f'{page.evaluate("S.versions.length")} version(s)')
            check("and it was not the catalogue",
                  page.evaluate("() => S.catalog !== true"))
            # What the app writes has to be Japanese. What the *model* wrote
            # is a different question: the agents are prompted in English on
            # purpose - translating their instructions would change what the
            # pipeline does, not just what it says - so a Planner asked in
            # Japanese still answers in English, and that answer is shown as
            # it came. The two are checked apart so the line between them
            # stays visible.
            ours = page.evaluate("""() => {
              const pick = sel => [...document.querySelectorAll(sel)]
                .map(e => e.textContent.trim()).filter(Boolean);
              return pick('#valBody .verdict b')
                .concat(pick('#valBody .speclabel'))
                .concat(pick('#valBody .judge-src'))
                .concat(pick('#planBody .eyebrow'))
                .join('\\n');
            }""")
            leaks = english_leaks(ours)
            check("the words the app writes are Japanese", not leaks,
                  "; ".join(leaks[:3]))

            model_said = page.evaluate("""() => {
              const one = sel => (document.querySelector(sel) || {}).textContent;
              return [one('#planBody .plan-desc'), one('#valBody .verdict p')]
                .filter(Boolean).map(s => s.trim().slice(0, 60));
            }""")
            for line in model_said:
                print(f"  ....  the model's own words, shown as written: "
                      f"{line}")

            leaks = english_leaks(page.locator("#thinkBody").inner_text())
            check("the reasoning panel's own words are Japanese", not leaks,
                  "; ".join(leaks[:3]))
            page.screenshot(path=str(out / "05-generated.png"))
        else:
            print("  ....  skipped - no --base-url given, so no agents to run")

        # ---------------------------------------------------------------
        print("\nBack to English, with the part still on screen")
        page.click('#langSw [data-lang="en"]')
        page.wait_for_timeout(800)
        header = page.locator("header").inner_text()
        check("the header came back to English",
              not CJK.search(re.sub(r"EN|日本語", "", header)),
              header.replace("\n", " ")[:60])
        check("the part is still there",
              page.evaluate("Viewer.extents !== null"))
        page.screenshot(path=str(out / "06-back-to-english.png"))

        print("\nConsole")
        real = [e for e in console if "favicon" not in e.lower()]
        check("no JavaScript errors", not real, "; ".join(real[:3]))
        browser.close()

    print(f"\n{'=' * 58}")
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED: {', '.join(failures[:6])}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
