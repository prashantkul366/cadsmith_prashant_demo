"""What the part is made of, and therefore what it weighs.

The first question anyone asks about a bracket is what it weighs. It needs a
material, and the numbers belong to somebody who maintains them - FreeCAD
ships 145 cards with density, yield and tensile strength - so they are read
from there rather than written here.

What is checked: that a card's units survive the trip (a density arrives as
"2.7e-06 kg/mm^3" and a yield as kPa, so 276000 is the 276 MPa everybody
means by 6061-T6), that a request's words reach the right card, that a mass
is a measured volume times a density rather than an estimate, and that a
ceiling the request *set* is enforced while a weight nobody limited is only
reported.

FreeCAD is not needed: without it the built-in table answers, which is the
point of having one.

Run:  .venv/bin/python -m app.tests.test_materials
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.server import materials  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


def main() -> int:
    materials._CACHE = []           # noqa: SLF001 - start from the fallback
    library = materials.library(None)

    print("Without FreeCAD there is still an answer")
    check("the built-in table stands in", len(library) >= 5,
          f"{len(library)} materials")
    check("and every one of them carries a density",
          all(c["density"] > 0 for c in library))

    print("\nA card's units are FreeCAD's, not a person's")
    # A card says "276000 kg/(mm*s^2)", which is kPa. 6061-T6 yields at
    # 276 MPa, and that is the number a person expects to read.
    card = materials._as_card({                       # noqa: SLF001
        "name": "Aluminum-6061-T6", "density": "2.7e-06 kg/mm^3",
        "yield": "276000 kg/(mm*s^2)", "uts": "310000 kg/(mm*s^2)",
        "youngs": "6.89e+07 kg/(mm*s^2)"})
    check("a density comes through as kg/mm3", card["density"] == 2.7e-06,
          str(card["density"]))
    check("and a yield as the MPa everyone quotes",
          card["yield_mpa"] == 276.0, f"{card['yield_mpa']} MPa")
    check("Young's modulus as GPa", card["youngs_gpa"] == 68.9,
          f"{card['youngs_gpa']} GPa")
    check("a card with no density is not a material",
          materials._as_card({"name": "X"}) is None)   # noqa: SLF001

    print("\nThe words a request uses reach the right card")
    for text, wanted in [
        ("make it from 6061", "Aluminum-6061-T6"),
        ("7075 aluminium", "Aluminum-7075-T6"),
        ("a mild steel bracket", "Steel-1C22"),
        ("an ABS housing", "ABS-Generic"),
        ("titanium", "Ti-6Al-4V"),
    ]:
        found = materials.find(text, None)
        check(f"{text!r}", bool(found) and found["name"] == wanted,
              found["name"] if found else "nothing")
    # The important negative. A part reported as aluminium because nobody
    # said otherwise is a number presented as a fact.
    check("a request that names no material gets none",
          materials.find("a mounting bracket", None) is None)
    check("and neither does an empty one", materials.find("", None) is None)

    print("\nThe mass is a measured volume times a density")
    card = materials.find("6061", None)
    weighed = materials.weigh(133125.0, card)
    check("a 133,125 mm3 flange in 6061 weighs 359 g",
          abs(weighed["mass_g"] - 359.4) < 0.5, f"{weighed['mass_g']} g")
    check("reported in g/cm3, which is how a density is read",
          weighed["density_g_cm3"] == 2.7, str(weighed["density_g_cm3"]))
    check("and it carries the strength a later check would need",
          weighed["yield_mpa"] == 276.0, str(weighed["yield_mpa"]))
    check("no material, no mass", materials.weigh(1000.0, None) is None)

    print("\nOnly a ceiling somebody set is enforced")
    for text, wanted in [("under 2 kg", 2.0), ("no more than 800 g", 0.8),
                         ("lighter than 1.5kg", 1.5), ("at most 250 g", 0.25),
                         ("maximum of 3 kg", 3.0)]:
        check(f"{text!r} is a limit of {wanted} kg",
              materials.limit(text) == wanted, str(materials.limit(text)))
    for text in ("a 2 kg flywheel", "the 500 g counterweight",
                 "about 2 kg", ""):
        check(f"{text!r} sets no limit", materials.limit(text) is None,
              str(materials.limit(text)))

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
