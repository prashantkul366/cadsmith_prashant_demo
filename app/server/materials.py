"""What the part is made of, and therefore what it weighs.

The first question anyone asks about a bracket is what it weighs, and the
second is whether it will hold. Neither is answerable from geometry alone -
both need a material - and this app had no notion of one.

FreeCAD ships the answer: 146 material cards carrying density, yield
strength, ultimate tensile strength and Young's modulus, maintained by
people who care about them. Aluminium 6061-T6 at 2.70 g/cm3 and 276 MPa;
7075-T6 at 503. Reading those out of FreeCAD is better than a table written
here, which would be a guess at numbers somebody else keeps properly.

Three things this is careful about.

**The mass is measured, not estimated.** The volume comes off the solid the
kernel exported, so a mass here is a density multiplied by a measured
volume, and it belongs with the other measured facts rather than with the
model's claims about the part.

**The units are FreeCAD's, and they are not the ones a person uses.** A card
says ``2.7e-06 kg/mm^3`` and ``276000 kg/(mm*s^2)``; the second is kPa, so a
yield of 276 MPa arrives as 276000. Converted once, here, rather than
wherever it is read.

**It works without FreeCAD.** A small built-in table covers the materials a
request is likely to name, so the generated path and a machine with no
FreeCAD running can still answer "what does it weigh".
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

#: Enough to answer the common request when FreeCAD is not there to ask.
#: Densities in kg/mm3 and strengths in MPa, to match what a card gives once
#: it has been converted.
FALLBACK = [
    {"name": "Aluminum-6061-T6", "density": 2.70e-06, "yield_mpa": 276.0,
     "uts_mpa": 310.0, "youngs_gpa": 68.9},
    {"name": "Aluminum-7075-T6", "density": 2.81e-06, "yield_mpa": 503.0,
     "uts_mpa": 572.0, "youngs_gpa": 71.7},
    {"name": "Steel-1C22", "density": 7.80e-06, "yield_mpa": 230.0,
     "uts_mpa": 430.0, "youngs_gpa": 210.0},
    {"name": "Steel-Generic", "density": 7.90e-06, "yield_mpa": 235.0,
     "uts_mpa": 360.0, "youngs_gpa": 200.0},
    {"name": "Ti-6Al-4V", "density": 4.43e-06, "yield_mpa": 880.0,
     "uts_mpa": 950.0, "youngs_gpa": 114.0},
    {"name": "ABS-Generic", "density": 1.06e-06, "yield_mpa": 44.1,
     "uts_mpa": 38.8, "youngs_gpa": 2.3},
    {"name": "PA6-Generic", "density": 1.15e-06, "yield_mpa": 70.5,
     "uts_mpa": 78.0, "youngs_gpa": 2.9},
]

#: The words a request uses, and the card they mean. Longest first, so
#: "6061" wins over "aluminium" in "aluminium 6061".
ALIASES = [
    ("6061", "Aluminum-6061-T6"),
    ("7075", "Aluminum-7075-T6"),
    ("ti-6al-4v", "Ti-6Al-4V"),
    ("grade 5", "Ti-6Al-4V"),
    ("titanium", "Ti-6Al-4V"),
    ("stainless", "Steel-X5CrNi18-10"),
    ("mild steel", "Steel-1C22"),
    ("carbon steel", "Steel-1C22"),
    ("steel", "Steel-Generic"),
    ("aluminium", "Aluminum-6061-T6"),
    ("aluminum", "Aluminum-6061-T6"),
    ("alloy", "Aluminum-6061-T6"),
    ("abs", "ABS-Generic"),
    ("nylon", "PA6-Generic"),
    ("pa6", "PA6-Generic"),
]

_CACHE: list[dict] = []


# ---------------------------------------------------------------------------
# Reading FreeCAD's library
# ---------------------------------------------------------------------------

_NUMBER = re.compile(r"^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)")


def quantity(raw: Any) -> Optional[float]:
    """The number out of a FreeCAD card's value, whatever unit trails it."""
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
    if not isinstance(raw, str):
        return None
    found = _NUMBER.match(raw)
    return float(found.group(1)) if found else None


def _as_card(row: dict) -> Optional[dict]:
    """One of FreeCAD's cards, in the units a person reads.

    A card's pressures are in kg/(mm*s^2), which is kPa - so 276000 is the
    276 MPa everyone means by 6061-T6. Divided here once rather than
    wherever somebody reads it.
    """
    density = quantity(row.get("density"))
    if not density or density <= 0:
        return None
    card = {"name": str(row.get("name") or "?"), "density": density}
    for key, out in (("yield", "yield_mpa"), ("uts", "uts_mpa")):
        value = quantity(row.get(key))
        card[out] = round(value / 1000.0, 1) if value else None
    youngs = quantity(row.get("youngs"))
    card["youngs_gpa"] = round(youngs / 1e6, 1) if youngs else None
    return card


READ_LIBRARY = """
import json, Materials
rows = []
for uuid, card in Materials.MaterialManager().Materials.items():
    props = dict(card.Properties) if hasattr(card, "Properties") else {}
    if not props.get("Density"):
        continue
    rows.append({"name": card.Name,
                 "density": props.get("Density"),
                 "yield": props.get("YieldStrength"),
                 "uts": props.get("UltimateTensileStrength"),
                 "youngs": props.get("YoungsModulus")})
"""


def library(bridge: Any = None) -> list[dict]:
    """Every material with a density, FreeCAD's if it is reachable.

    Cached for the life of the process: the library does not change while
    the app is running, and asking FreeCAD on every part would put a round
    trip in front of a number that never moves.
    """
    global _CACHE
    if _CACHE:
        return _CACHE
    if bridge is not None:
        try:
            from app.server import freecad

            raw = json.loads(bridge.value(
                READ_LIBRARY + freecad.marked("json.dumps(rows)")))
            cards = [c for c in (_as_card(row) for row in raw) if c]
            if cards:
                _CACHE = sorted(cards, key=lambda c: c["name"])
                return _CACHE
        except Exception:
            pass        # FreeCAD is not there, or has no material library
    _CACHE = list(FALLBACK)
    return _CACHE


def find(text: str, bridge: Any = None) -> Optional[dict]:
    """The material a request names, or nothing if it names none.

    Nothing rather than a default on purpose: a part reported as aluminium
    because nobody said otherwise is a number presented as a fact.
    """
    if not text:
        return None
    lowered = text.lower()
    cards = library(bridge)
    by_name = {c["name"].lower(): c for c in cards}

    # An exact card name, which is what the builder sends back.
    if lowered.strip() in by_name:
        return by_name[lowered.strip()]
    for alias, name in ALIASES:
        if alias in lowered:
            wanted = name.lower()
            if wanted in by_name:
                return by_name[wanted]
            # The alias names a card this library does not carry. Look for
            # one named after the same thing, by the stem of the alias and
            # then by the word the request used - FreeCAD calls titanium
            # "Ti-6Al-4V", which starts with neither.
            stem = wanted.split("-")[0]
            for guess in (stem, alias.split()[0]):
                near = [c for c in cards
                        if c["name"].lower().startswith(guess)
                        or guess in c["name"].lower()]
                if near:
                    return sorted(near, key=lambda c: len(c["name"]))[0]
    return None


# ---------------------------------------------------------------------------
# What it weighs
# ---------------------------------------------------------------------------

def weigh(volume_mm3: float, card: Optional[dict]) -> Optional[dict]:
    """The mass of a measured volume in a named material."""
    if not card or not volume_mm3:
        return None
    kilograms = float(volume_mm3) * float(card["density"])
    return {
        "material": card["name"],
        "density_g_cm3": round(card["density"] * 1e6, 3),
        "mass_kg": round(kilograms, 4),
        "mass_g": round(kilograms * 1000.0, 1),
        "yield_mpa": card.get("yield_mpa"),
        "uts_mpa": card.get("uts_mpa"),
    }


#: A mass the request asks the part to come in under.
_LIMIT = re.compile(
    r"(?:under|below|less\s+than|lighter\s+than|no\s+more\s+than|at\s+most|max(?:imum)?\s*(?:of)?)"
    r"\s*([-+]?\d+(?:\.\d+)?)\s*(kg|kilograms?|g|grams?)\b", re.IGNORECASE)


def limit(text: str) -> Optional[float]:
    """A mass ceiling the request states, in kilograms.

    Only a ceiling. "about 2 kg" is a hope and "2 kg" alone is usually a
    description of something else in the sentence; a part is refused only
    for a number somebody actually set as a limit.
    """
    found = _LIMIT.search(text or "")
    if not found:
        return None
    value = float(found.group(1))
    return value / 1000.0 if found.group(2).lower().startswith("g") else value
