"""What the part is made of, how, and to what tolerance.

``drawing.py`` opens by explaining why its sheet carries no tolerances:

    nothing in the pipeline has specified either, and a general tolerance
    note on a drawing nobody has toleranced would be a claim rather than
    a fact

That was the correct call and it named the real gap, which is not in the
drawing at all - it is that the plan had nowhere to put a material, a
process or a tolerance class, so there was nothing true for the sheet to
say.  A watertight solid with correct dimensions and no specification is a
shape.  A part is a shape plus what it is made of and how closely.

This module is that missing half.  Three rules govern it:

**It proposes; it does not decide.**  The Planner suggests a material and a
tolerance class the way it suggests a dimension, and it can be as wrong.
Everything here is labelled on the sheet as proposed and unconfirmed, which
keeps the original honesty - the drawing still never claims more than it
knows, it just now knows more.

**Fits are looked up, not invented.**  A 6203 bearing sits in an H7 housing
bore because ISO 286 says so, and ``catalog/standards.py`` already carries
the numbers.  Where the request names a standard part, the fit comes from
the table.  Where it does not, the Planner's suggestion is carried as a
suggestion and marked as one.

**A value that cannot be trusted is dropped rather than guessed.**  A
tolerance class the Planner invented ("ISO 2768-x") becomes no class at
all, and the sheet goes back to saying nothing - which is where it started,
and no worse.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.catalog import standards

#: General tolerance classes, coarsest last. ISO 2768-1 covers linear and
#: angular dimensions without individual tolerances - the note that makes a
#: drawing complete without toleranceing every feature on it.
TOLERANCE_CLASSES = {
    "f": "ISO 2768-f",       # fine
    "m": "ISO 2768-m",       # medium - the usual default for machined work
    "c": "ISO 2768-c",       # coarse
    "v": "ISO 2768-v",       # very coarse
}
DEFAULT_TOLERANCE = "ISO 2768-m"

#: Processes the app is willing to name on a drawing. Anything else the
#: Planner invents is carried as free text under MATERIAL instead, because
#: a process drives the tolerance a shop can hold and a made-up one misleads.
PROCESSES = ("machined", "turned", "milled", "cast", "moulded", "printed",
             "sheet", "fabricated", "extruded")

#: Roughly what each process can hold without special measures. Used only to
#: say when the Planner's tolerance class looks optimistic for its own
#: choice of process - never to overrule it.
PROCESS_FLOOR = {
    "cast": "ISO 2768-c", "moulded": "ISO 2768-c", "printed": "ISO 2768-c",
    "sheet": "ISO 2768-c", "fabricated": "ISO 2768-c",
}

_CLASS_RE = re.compile(r"(?:ISO\s*)?2768\s*[-–]?\s*([fmcv])\b", re.I)
_ORDER = ["ISO 2768-f", "ISO 2768-m", "ISO 2768-c", "ISO 2768-v"]


@dataclass
class Fit:
    """One place two parts meet, and how closely."""
    feature: str
    size_mm: Optional[float]
    fit: str
    why: str = ""
    grounded: bool = False       # from a published table, not proposed

    def render(self) -> str:
        """The note as it goes on the sheet.

        The fit designation is never case-folded, however much the rest of a
        drawing shouts. In ISO 286 the letter's case *is* the meaning - H7 is
        a hole and h7 a shaft - so uppercasing a shaft tolerance silently
        turns it into a bore one, and a machinist works to what is written.
        """
        size = f"Ø{self.size_mm:g} " if self.size_mm else ""
        return f"{size}{self.fit} - {self.feature}"


@dataclass
class Specification:
    """What a drawing needs to say beyond the geometry."""
    material: str = ""
    process: str = ""
    tolerance_class: str = ""
    finish: str = ""
    fits: list[Fit] = field(default_factory=list)
    #: True when anything here came from the Planner rather than a table.
    proposed: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def stated(self) -> bool:
        """Is there anything to put on the sheet at all?"""
        return bool(self.material or self.tolerance_class or self.fits)

    def sheet_notes(self) -> list[str]:
        """The lines under the views, in the order they should be read.

        Notes rather than title-block fields, which is where a general
        tolerance note belongs on an ISO sheet anyway. The title block here
        is a fixed four rows sized to sit clear of the isometric view, and
        material is not worth moving a view for.
        """
        lines: list[str] = []
        if self.material:
            material = self.material.upper()
            if self.process:
                material += f" · {self.process.upper()}"
            lines.append(f"MATERIAL: {material}")
        if self.finish:
            lines.append(f"FINISH: {self.finish.upper()}")
        if self.tolerance_class:
            lines.append(
                f"GENERAL TOLERANCES TO {self.tolerance_class} UNLESS "
                f"OTHERWISE STATED")
        else:
            lines.append("DIMENSIONS ARE AS MODELLED — NO TOLERANCES "
                         "ARE SPECIFIED")
        for fit in self.fits[:4]:
            mark = "" if fit.grounded else " (PROPOSED)"
            lines.append(f"{fit.render()}{mark}")
        if self.proposed:
            # The whole point of the original refusal to print a tolerance
            # note: never let the sheet imply an engineer signed this off.
            lines.append("MATERIAL, PROCESS AND TOLERANCE CLASS ARE PROPOSED "
                         "BY THE PLANNER — CONFIRM BEFORE MANUFACTURE")
        lines.extend(self.notes)
        return lines

    def to_dict(self) -> dict:
        return {
            "material": self.material, "process": self.process,
            "tolerance_class": self.tolerance_class, "finish": self.finish,
            "proposed": self.proposed,
            "fits": [{"feature": f.feature, "size_mm": f.size_mm,
                      "fit": f.fit, "why": f.why, "grounded": f.grounded}
                     for f in self.fits],
            "notes": list(self.notes),
        }


def _text(value: Any, limit: int = 60) -> str:
    if value is None or isinstance(value, bool):
        return ""
    body = " ".join(str(value).split())
    if body.lower() in ("", "none", "null", "n/a", "unknown", "tbd"):
        return ""
    return body[:limit]


def _tolerance_class(value: Any) -> str:
    """A real ISO 2768 class, or "" for anything else.

    A class the Planner invented is worse than no class: a shop reads it and
    works to it.
    """
    match = _CLASS_RE.search(_text(value, 40))
    return TOLERANCE_CLASSES[match.group(1).lower()] if match else ""


def _process(value: Any) -> str:
    body = _text(value, 40).lower()
    for name in PROCESSES:
        if name in body:
            return name
    return ""


def _number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if 0 < number < 10000 else None


def ground_fits(prompt: str) -> list[Fit]:
    """Fits the standards tables can settle for what the request names.

    Only the cases where a published table gives the answer outright. A
    bearing has a housing seat and a shaft seat and ISO 286 names both; a
    dowel has an interference fit in one hole and a location fit in the
    other. Those are facts. Everything else is left to the Planner and
    marked as proposed.
    """
    found: list[Fit] = []
    for designation in sorted(set(re.findall(r"\b(6\d{3})\b", prompt))):
        bearing = standards.BEARINGS.get(designation)
        if bearing is None:
            continue
        found.append(Fit(
            feature=f"housing bore for the {designation} outer ring",
            size_mm=float(bearing.outer_diameter), fit="H7",
            why=f"ISO 286 location fit for a {designation} outer ring in a "
                f"non-rotating housing",
            grounded=True))
        found.append(Fit(
            feature=f"shaft seat for the {designation} inner ring",
            size_mm=float(bearing.bore), fit="k6",
            why=f"ISO 286 interference fit for a {designation} inner ring on "
                f"a rotating shaft",
            grounded=True))

    for raw in sorted(set(re.findall(r"\bM\s?(\d+(?:\.\d+)?)\b", prompt,
                                     re.I))):
        size = f"M{raw.rstrip('.0') if raw.endswith('.0') else raw}"
        try:
            thread = standards.THREADS[size]
        except KeyError:
            continue
        found.append(Fit(
            feature=f"clearance hole for {size}",
            size_mm=float(thread.clearance_normal), fit="normal fit",
            why=f"ISO 273 normal-series clearance for {size}",
            grounded=True))
    return found[:6]


def read(plan: Any, prompt: str = "") -> Specification:
    """The specification for one run, from the plan and the standards.

    Never raises and never refuses a run: a plan with no specification block
    at all yields an empty Specification, and the sheet says what it said
    before.
    """
    block = plan.get("specification") if isinstance(plan, dict) else None
    block = block if isinstance(block, dict) else {}

    spec = Specification(
        material=_text(block.get("material")),
        process=_process(block.get("process")),
        tolerance_class=_tolerance_class(block.get("tolerance_class")),
        finish=_text(block.get("finish"), 40),
    )
    spec.proposed = bool(spec.material or spec.tolerance_class)

    grounded = ground_fits(prompt)
    seen = {(f.feature.lower(), f.size_mm) for f in grounded}
    proposed: list[Fit] = []
    for raw in (block.get("fits") or [])[:6]:
        if not isinstance(raw, dict):
            continue
        feature = _text(raw.get("feature"), 48)
        fit = _text(raw.get("fit"), 16)
        if not feature or not fit:
            continue
        size = _number(raw.get("size_mm"))
        if (feature.lower(), size) in seen:
            continue
        proposed.append(Fit(feature=feature, size_mm=size, fit=fit,
                            why=_text(raw.get("why"), 90), grounded=False))
    spec.fits = grounded + proposed

    # A process that cannot hold the class the Planner asked for is worth
    # saying out loud. Not overruled: a casting held to 2768-m is possible
    # with machining after, and the Planner may know that.
    floor = PROCESS_FLOOR.get(spec.process)
    if floor and spec.tolerance_class and spec.tolerance_class in _ORDER \
            and _ORDER.index(spec.tolerance_class) < _ORDER.index(floor):
        spec.notes.append(
            f"{spec.tolerance_class.upper()} IS TIGHT FOR A "
            f"{spec.process.upper()} PART — CHECK WITH THE SUPPLIER")
    return spec


def from_dict(raw: Any) -> Optional[Specification]:
    """Rebuild a Specification written to disk by a finished run."""
    if not isinstance(raw, dict):
        return None
    spec = Specification(
        material=_text(raw.get("material")),
        process=_text(raw.get("process"), 40),
        tolerance_class=_tolerance_class(raw.get("tolerance_class")),
        finish=_text(raw.get("finish"), 40),
        proposed=bool(raw.get("proposed")),
        notes=[_text(n, 90) for n in (raw.get("notes") or []) if _text(n, 90)],
    )
    for item in (raw.get("fits") or []):
        if not isinstance(item, dict):
            continue
        feature, fit = _text(item.get("feature"), 48), _text(item.get("fit"), 16)
        if feature and fit:
            spec.fits.append(Fit(feature=feature, size_mm=_number(item.get("size_mm")),
                                 fit=fit, why=_text(item.get("why"), 90),
                                 grounded=bool(item.get("grounded"))))
    return spec if spec.stated else None
