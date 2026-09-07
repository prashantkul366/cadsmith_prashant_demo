"""Japanese support: the dictionary, the plumbing, and what must stay English.

Three things are checked, and the third matters most.

**Nothing is half-translated.**  A key present in one language and missing in
the other shows up as one English sentence in an otherwise Japanese screen,
which reads as a bug in the app rather than a gap in a dictionary.  Both
catalogues - the server's and the browser's - are checked entry by entry, and
every key the interface actually asks for is checked against the dictionary
that has to answer it.

**A Japanese edit is understood without a model.**  ``server/edits.py``
matches English words, so 「厚さを 5mm にする」 would otherwise fall through to
the Refiner - slow with a backend configured, and refused outright without
one.  The refusals matter more than the patches: 「補強リブを追加する」 has to
still come out as a rib, or the patch path lands on whichever number happens
to match and reports a rib it never made.

**The model is still spoken to in English.**  The agents in autofab are
steered by English prompts, and the Refiner is handed English measurements.
Translating either would change what the pipeline does rather than what it
says, so no module that talks to a model may hold a Japanese literal.

Run:  .venv/bin/python -m app.tests.test_i18n
"""

from __future__ import annotations

import ast
import io
import re
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.server import edits, i18n, japanese  # noqa: E402
from app.server.jobs import JobOptions  # noqa: E402

WEB = ROOT / "app" / "web"

#: Keys whose Japanese is legitimately not Japanese: punctuation, and the
#: name of a product written the same way in both languages.
IDENTICAL_OK = {"code.empty", "diag.cadquery"}

CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿]")


# ---------------------------------------------------------------------------
# Reading the browser's dictionary from Python
# ---------------------------------------------------------------------------

def parse_js_dict(source: str) -> dict[str, list[str]]:
    """Every ``"key": [english, japanese]`` entry in i18n.js.

    A real parse rather than a regex over the whole entry: the strings are
    written as concatenations across several lines, and a pattern that tried
    to match the closing bracket would stop at the first ``]`` inside one.
    """
    entries: dict[str, list[str]] = {}
    for match in re.finditer(r'"([\w.]+)":\s*\[', source):
        key = match.group(1)
        i = match.end()
        depth, in_string, quote, escaped = 1, False, "", False
        parts, current = [], []
        while i < len(source) and depth:
            ch = source[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote:
                    in_string = False
                else:
                    current.append(ch)
            elif ch in "\"'":
                in_string, quote = True, ch
            elif ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if not depth:
                    parts.append("".join(current))
            elif ch == "," and depth == 1:
                parts.append("".join(current))
                current = []
            i += 1
        entries[key] = parts
    return entries


def japanese_strings(path: Path) -> list[str]:
    """Japanese found in a module's string constants, ignoring docstrings.

    Comments never reach a model, and the ones in ``edits.py`` quote the very
    instructions they exist to explain. Parsing rather than scanning the text
    is what lets those stand while still failing on a hardcoded message.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef,
                             ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr)
                    and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                docstrings.add(id(first.value))
    return [node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
            and id(node) not in docstrings and CJK.search(node.value)]


def literal_keys(source: str) -> set[str]:
    """Keys the interface asks for by name: t("x"), I18N.has("x")."""
    # The closing quote must be followed by a comma or the closing bracket:
    # t("think." + agent) builds its key at draw time and the literal there is
    # a prefix, not a key. Those families are listed out separately below.
    found = set()
    for call in (r"\bt", r"I18N\.has"):
        found |= set(re.findall(call + r'\(\s*"([\w.]+)"\s*[,)]', source))
    # A ternary inside the call - t(passed ? "a" : "b") - and the label fields
    # of the STAGES and EDIT_STEPS tables, which are keys rather than text.
    found |= set(re.findall(r'\?\s*"([\w.]+)"\s*:\s*"([\w.]+)"', source)[0]
                 ) if False else found
    for a, b in re.findall(r'\?\s*"([\w.]+)"\s*\n?\s*:\s*"([\w.]+)"', source):
        found |= {a, b}
    found |= set(re.findall(r'label:\s*"([\w.]+)"', source))
    return {k for k in found if "." in k}


def markup_keys(source: str) -> set[str]:
    """Keys the markup asks for: data-i18n, -ph, -title, -alt, -label."""
    return set(re.findall(r'data-i18n(?:-(?:ph|title|alt|label))?="([\w.]+)"',
                          source))


def main() -> int:  # noqa: C901 - a checklist, not a branchy function
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}"
              f"{(' - ' + detail) if detail else ''}")
        if not ok:
            failures.append(label)

    # -- the server's catalogue --------------------------------------------
    print("\nThe server speaks both languages")
    missing = i18n.check()
    check("every server message has both languages", not missing,
          ", ".join(missing[:6]))
    untranslated = [key for key, entry in i18n.MESSAGES.items()
                    if not CJK.search(entry["ja"])]
    check("and the Japanese is actually Japanese", not untranslated,
          ", ".join(untranslated[:6]))

    check("a bare tag resolves", i18n.normalise("ja") == "ja")
    check("a region-qualified tag resolves", i18n.normalise("ja-JP") == "ja")
    check("case does not matter", i18n.normalise("JA") == "ja")
    check("a language we do not have falls back to English",
          i18n.normalise("fr") == "en")
    check("so does nothing at all", i18n.normalise(None) == "en")
    check("a browser asking for Japanese gets it",
          i18n.from_header("ja-JP,ja;q=0.9,en-US;q=0.8") == "ja")
    check("a browser asking for English gets it",
          i18n.from_header("en-GB,en;q=0.9") == "en")
    check("an unknown key returns itself rather than raising",
          i18n.t("no.such.key") == "no.such.key")
    check("a missing placeholder does not lose the message",
          "could not be built" in i18n.t("edit.unbuildable", "en"))

    japanese_refusal = i18n.t("edit.unbuildable", "ja", error_type="OCCTError")
    check("a failed edit explains itself in Japanese",
          CJK.search(japanese_refusal) is not None
          and "OCCTError" in japanese_refusal, japanese_refusal[:44])
    check("and still in English",
          not CJK.search(i18n.t("edit.unbuildable", "en", error_type="X")))

    print("\nA run carries the language it was started in")
    options = JobOptions.from_dict({"lang": "ja-JP"})
    check("the client's language reaches the job", options.lang == "ja")
    check("and survives being written to disk and read back",
          JobOptions.from_dict(asdict(options)).lang == "ja")
    check("a language we do not have does not break a run",
          JobOptions.from_dict({"lang": "xx"}).lang == "en")
    check("and neither does none at all", JobOptions().lang == "en")

    # -- the browser's catalogue -------------------------------------------
    print("\nThe interface speaks both languages")
    dictionary = parse_js_dict(io.open(WEB / "i18n.js", encoding="utf-8").read())
    check("the browser dictionary was read", len(dictionary) > 150,
          f"{len(dictionary)} keys")

    lopsided = [key for key, parts in dictionary.items()
                if len(parts) != 2 or not parts[0].strip() or not parts[1].strip()]
    check("every interface string has both languages", not lopsided,
          ", ".join(lopsided[:6]))

    same = [key for key, parts in dictionary.items()
            if len(parts) == 2 and not CJK.search(parts[1])
            and key not in IDENTICAL_OK]
    check("and none of them was left in English", not same,
          ", ".join(same[:6]))

    app_js = io.open(WEB / "app.js", encoding="utf-8").read()
    html = io.open(WEB / "index.html", encoding="utf-8").read()

    asked = literal_keys(app_js) | markup_keys(html)
    unknown = sorted(k for k in asked if k not in dictionary)
    check("every key the interface asks for exists", not unknown,
          ", ".join(unknown[:8]))
    check("and the interface asks for a lot of them", len(asked) > 100,
          f"{len(asked)} keys")

    # Built at draw time from a variable, so a regex over the source cannot
    # see them; each family is listed here instead.
    print("\nThe keys built from a variable are all present")
    families = {
        "stage.": ["plan", "code", "execute", "judge", "done"],
        "edit.step.": ["read", "apply", "rebuild", "validate", "done"],
        # The Reasoning panel: one block per agent, each with a caption.
        "think.": ["plan", "plan.sub", "code", "code.sub",
                   "error_fix", "error_fix.sub", "judge", "judge.sub",
                   "refine", "refine.sub"],
        "diag.": ["cadquery", "vision_render", "model_backend", "metrics",
                  "tls_trust"],
        "prov.hint.": ["anthropic", "bedrock", "openai", "ollama", "lmstudio",
                       "custom", "unreachable"],
    }
    for prefix, names in families.items():
        gaps = [prefix + name for name in names
                if prefix + name not in dictionary]
        check(f"{prefix}* is complete", not gaps, ", ".join(gaps))

    # The Reasoning panel labels every agent the pipeline can emit; a phase
    # with no entry would show its raw id in both languages.
    agents = set(re.findall(r'AGENT_KEYS = \[([^\]]+)\]', app_js))
    emitted = set(re.findall(r'"(\w+)"', "".join(agents)))
    gaps = sorted(a for a in emitted if f"think.{a}" not in dictionary)
    check("every agent the Reasoning panel knows has a label",
          emitted and not gaps, ", ".join(gaps) or f"{len(emitted)} agents")

    # The server names its provider hints by key; each must have an entry, or
    # the setup line silently falls back to English inside Japanese.
    providers_py = io.open(ROOT / "app" / "server" / "providers.py",
                           encoding="utf-8").read()
    ids = set(re.findall(r'\bid="(\w+)"', providers_py))
    gaps = sorted(i for i in ids if f"prov.hint.{i}" not in dictionary)
    check("every provider's setup hint has a label", ids and not gaps,
          ", ".join(gaps) or f"{len(ids)} providers")

    # -- a Japanese edit, without a model ----------------------------------
    print("\nA Japanese edit instruction is understood without a model")
    washer = ("import cadquery as cq\n\n"
              "inner_diameter = 10.5\nouter_diameter = 20.0\nthickness = 2.0\n\n"
              "result = (cq.Workplane('XY').circle(outer_diameter / 2)\n"
              "          .circle(inner_diameter / 2).extrude(thickness))\n")
    for instruction, name, value in (
            ("厚さを 5mm にする", "thickness", 5.0),
            ("外径を 30mm にする", "outer_diameter", 30.0),
            ("内径を 12mm に変更", "inner_diameter", 12.0)):
        plan = edits.plan_edit(washer, instruction)
        got = [(c.name, c.new) for c in plan.changes]
        check(f"{instruction} patches {name} to {value:g}",
              got == [(name, value)], f"{got or plan.reason}")

    # The refusals matter more than the patches: a structural request that
    # slipped through would patch some unrelated number and report it as a rib.
    for instruction, word in (("補強リブを追加する", "rib"),
                              ("面取りを 2mm 追加してください", "chamfer"),
                              ("フィレットを 3mm にする", "fillet"),
                              ("肉抜きする", "shell")):
        plan = edits.plan_edit(washer, instruction)
        check(f"{instruction} is refused as a shape change",
              not plan.changes and word in plan.reason, plan.reason)

    print("\nAn English instruction is untouched by any of it")
    check("English text is never rewritten",
          not japanese.has_japanese("make it 15 mm thick"))
    check("and still patches what it always did",
          [(c.name, c.new) for c in
           edits.plan_edit(washer, "make it 15 mm thick").changes]
          == [("thickness", 15.0)])
    check("an English shape change is refused as before",
          not edits.plan_edit(washer, "add a reinforcing rib").changes)

    # -- what must not be translated ---------------------------------------
    print("\nWhat the model reads is still English")
    # The two modules allowed to hold Japanese are the dictionary and the
    # rewriter; anywhere else it would be text on its way to a model. Only
    # string constants count - a comment explaining why 「補強リブを追加する」
    # must be refused is documentation, and never reaches anything.
    for module in ("instrument.py", "jobs.py", "app.py", "edits.py",
                   "providers.py", "drawing.py", "replay.py"):
        found = japanese_strings(ROOT / "app" / "server" / module)
        check(f"server/{module} holds no Japanese string of its own",
              not found, ", ".join(found[:3]))
    for module in ("agents.py", "validator.py", "executor.py", "pipeline.py"):
        path = ROOT / "autofab" / module
        if not path.exists():
            continue
        found = japanese_strings(path)
        check(f"autofab/{module} is written to the model in English",
              not found, ", ".join(found[:3]))
    check("the rewriter's output is a lookup key, not a translation",
          not CJK.search(japanese.to_english_instruction("厚さを 5mm にする")))

    print(f"\n{'=' * 58}")
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED: {', '.join(failures[:8])}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
