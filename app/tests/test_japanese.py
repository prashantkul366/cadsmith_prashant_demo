"""A Japanese run, read end to end in Japanese.

The window was already Japanese - the stage names, the view labels, the
title block. What was not: everything the model had written, and everything
derived from what the model had written. The Planner reasoned in English,
described the part in English and named its key dimensions in English, the
sliders were labelled with the script's English identifiers, and the notes
under the drawing - the part of a sheet that is prose rather than geometry -
were English on an otherwise Japanese drawing.

Four things stay English on purpose, and each is checked here, because each
one is read by a program rather than by a person:

  * JSON keys, which the pipeline parses by name;
  * Python identifiers, which are parsed back out of the generated script to
    build the sliders - a non-ASCII one takes that panel out entirely;
  * `material`, `process` and `tolerance_class`, which are looked up in
    tables by their English names;
  * designations written the same everywhere: M8x1.25, H7, ISO 2768-m,
    6061-T6 - and in ISO 286 a fit's letter case *is* its meaning.

Run:  .venv/bin/python -m app.tests.test_japanese
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.server import drawing, edits, glossary, i18n, instrument  # noqa: E402
from app.server.specification import Fit, Specification  # noqa: E402

#: Anything in these ranges is Japanese: kana, or a CJK ideograph.
_JAPANESE = re.compile(r"[぀-ヿ一-鿿]")

#: The script the flexible-strip part was built from, trimmed to its
#: parameters. Real names from a real run - this is the part whose sliders
#: were read in English in a Japanese window.
CODE = """import cadquery as cq

thickness = 0.15
pad_diameter = 12.0
pad_pitch = 22.5
pad_count = 5
strip_length = 90.0
strip_width = 7.0
slit_width = 0.5
slit_length = 10.0

result = cq.Workplane("XY").box(strip_length, strip_width, thickness)
"""


def main() -> int:
    failures = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        if not ok:
            failures += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}"
              + (f" - {detail}" if detail else ""))

    print("The sliders are labelled in Japanese")
    described = {d["name"]: d for d in edits.describe_parameters(CODE, "ja")}
    for name, want in (("pad_diameter", "パッド径"),
                       ("pad_pitch", "パッドピッチ"),
                       ("pad_count", "パッド数"),
                       ("slit_width", "スリット幅"),
                       ("slit_length", "スリット長さ"),
                       ("strip_width", "ストリップ幅"),
                       ("strip_length", "ストリップ長さ"),
                       ("thickness", "厚さ")):
        got = described[name]["label"]
        check(f"{name} -> {want}", got == want, got)
    # The identifier has to survive beside the label: it is what the code
    # calls the value, and the control shows it on hover.
    check("and each one still carries its identifier",
          all(d["name"] == n for n, d in described.items()))
    english = {d["name"]: d for d in edits.describe_parameters(CODE)}
    check("while an English run is unchanged",
          english["pad_diameter"]["label"] == "Pad diameter",
          english["pad_diameter"]["label"])

    print("\nA name the glossary does not know reads back in English")
    check("rather than half-translated, which looks like a fault",
          glossary.label("frobnicator_width", "ja") == "Frobnicator width",
          glossary.label("frobnicator_width", "ja"))

    print("\nThe notes under the drawing are in Japanese")
    spec = Specification(
        material="stainless steel 301", process="sheet",
        tolerance_class="ISO 2768-f", finish="as rolled", proposed=True,
        fits=[Fit(feature="locating bore", size_mm=8.0, fit="H7",
                  why="dowel", grounded=False)])
    notes = drawing.note_lines({"is_valid": True}, spec, None, "ja")
    body = "\n".join(notes)
    check("every line of prose is Japanese",
          all(_JAPANESE.search(line) for line in notes),
          " / ".join(line for line in notes if not _JAPANESE.search(line))
          or f"{len(notes)} line(s)")
    # The designations inside that prose are not touched.
    for mark in ("ISO 2768-f", "STAINLESS STEEL 301", "H7", "Ø8"):
        check(f"{mark} is written as it is written", mark in body)
    check("the process is spelled in Japanese", "板金" in body, body[:40])
    check("and the sheet still says the Planner proposed this",
          i18n.t("note.proposed", "ja") in notes)
    english_notes = "\n".join(drawing.note_lines({"is_valid": True}, spec))
    check("while an English sheet is unchanged",
          "ALL DIMENSIONS IN MILLIMETRES" in english_notes
          and "MATERIAL: STAINLESS STEEL 301 · SHEET" in english_notes)

    print("\nThe agents are told to answer in Japanese")
    speak = instrument._REPLY_LANGUAGE["ja"]
    check("the instruction is added, not substituted",
          speak.startswith("\n\n") and "Reply in Japanese" in speak)
    for keep in ("JSON key", "ASCII snake_case", "`material`", "H7",
                 "ISO 2768-m"):
        check(f"and it protects {keep}", keep in speak)
    check("English runs are told nothing at all",
          instrument._REPLY_LANGUAGE.get("en") is None)

    print("\n" + "=" * 58)
    print("ALL CHECKS PASSED" if not failures else f"{failures} CHECK(S) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
