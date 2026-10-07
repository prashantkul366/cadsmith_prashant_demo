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
    #: Surface roughness in micrometres, as the Ra figure a drawing prints
    #: beside the ISO 1302 tick. Separate from ``finish``, which is a
    #: treatment - "black anodised" is a finish and 1.6 is a roughness, and
    #: a part can want both.
    roughness: Optional[float] = None
    #: What an untoleranced dimension is held to when the request gave a
    #: figure rather than a class: "+/- 0.1" is not ISO 2768-anything.
    tolerance_mm: Optional[float] = None
    #: Whether a Planner proposed what is unconfirmed here, or this app did
    #: because the request said nothing. Only the wording of one note turns
    #: on it, and that note is the sheet's one disclaimer.
    by_planner: bool = False
    #: Whether the request asked for the edges to be broken. ISO 13715: a
    #: drawing that says nothing about edges is asking for whatever the
    #: machine leaves, which on an aluminium plate is sharp enough to cut.
    break_edges: bool = False

    @property
    def stated(self) -> bool:
        """Is there anything to put on the sheet at all?"""
        return bool(self.material or self.tolerance_class or self.fits
                    or self.roughness or self.tolerance_mm
                    or self.break_edges or self.finish)

    def sheet_notes(self, titled: bool = False,
                    shown: Any = ()) -> list[str]:
        """The lines under the views, in the order they should be read.

        ``titled`` says the title block is already carrying the material,
        which it is whenever the part was weighed. Printing it twice on one
        sheet is how a drawing starts to look auto-generated. ``shown`` is
        the sizes whose fit is already on a hole's leader, for the same
        reason: a drawing states a tolerance once, where the dimension is.

        Notes rather than title-block fields, which is where a general
        tolerance note belongs on an ISO sheet anyway. The title block here
        is a fixed four rows sized to sit clear of the isometric view, and
        material is not worth moving a view for.
        """
        lines: list[str] = []
        if self.material and not titled:
            material = self.material.upper()
            if self.process:
                material += f" · {self.process.upper()}"
            lines.append(f"MATERIAL: {material}")
        elif self.process:
            lines.append(f"PROCESS: {self.process.upper()}")
        if self.finish:
            lines.append(f"FINISH: {self.finish.upper()}")
        if self.tolerance_class:
            lines.append(
                f"GENERAL TOLERANCES TO {self.tolerance_class} UNLESS "
                f"OTHERWISE STATED")
        elif self.tolerance_mm:
            # A figure rather than a class. Written as the drawing office
            # writes it, which is on every dimension without one of its own.
            lines.append(
                f"UNTOLERANCED DIMENSIONS \u00b1{self.tolerance_mm:g} "
                f"UNLESS OTHERWISE STATED")
        else:
            lines.append("DIMENSIONS ARE AS MODELLED — NO TOLERANCES "
                         "ARE SPECIFIED")
        if self.roughness:
            lines.append(
                f"SURFACE ROUGHNESS Ra {self.roughness:g} \u00b5m MAXIMUM "
                f"ON ALL MACHINED SURFACES")
        if self.break_edges:
            # ISO 13715. 0.3 is what a drawing office writes when it means
            # "take the edge off", and it is small enough not to change a
            # dimension anybody checks.
            lines.append("BREAK ALL SHARP EDGES 0.3 MAX")
        said = set(shown or ())
        for fit in self.fits[:4]:
            if fit.size_mm is not None and round(fit.size_mm, 2) in said:
                continue
            mark = "" if fit.grounded else " (PROPOSED)"
            lines.append(f"{fit.render()}{mark}")
        if self.proposed:
            # The whole point of the original refusal to print a tolerance
            # note: never let the sheet imply an engineer signed this off.
            # Who proposed it depends on the road - a Planner on one, this
            # app's own fallback on the other - and the sheet says which,
            # because "confirm it with the model" and "confirm it with
            # nobody" are different instructions to the person reading.
            lines.append(
                "MATERIAL, PROCESS AND TOLERANCE CLASS ARE PROPOSED BY THE "
                "PLANNER — CONFIRM BEFORE MANUFACTURE" if self.by_planner
                else f"NO GENERAL TOLERANCE WAS STATED — "
                     f"{self.tolerance_class.upper()} ASSUMED, CONFIRM "
                     f"BEFORE MANUFACTURE")
        lines.extend(self.notes)
        return lines

    def to_dict(self) -> dict:
        return {
            "material": self.material, "process": self.process,
            "tolerance_class": self.tolerance_class, "finish": self.finish,
            "proposed": self.proposed,
            "by_planner": self.by_planner,
            "roughness": self.roughness,
            "tolerance_mm": self.tolerance_mm,
            "break_edges": self.break_edges,
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


#: What a drawing office writes, read out of what an engineer typed.
#: Each of these is a thing somebody puts on a request and expects to find
#: on the drawing, and every one of them was being dropped on the road that
#: skips the Planner - which is now the road most parts come down.

#: "Ra 1.6", "Ra1.6", "surface finish 3.2", "0.8 Ra". Micrometres always:
#: nobody writes a roughness in anything else, and the preferred series runs
#: 0.1 to 25.
_RA = re.compile(
    r"(?:\bRa\s*(?P<a>\d+(?:\.\d+)?)"
    r"|(?P<b>\d+(?:\.\d+)?)\s*(?:\u00b5m|um|microns?)?\s*Ra\b"
    r"|surface\s+(?:finish|roughness)\s+(?:of\s+)?(?:Ra\s*)?"
    r"(?P<c>\d+(?:\.\d+)?))", re.I)

#: "+/-0.1", "\u00b10.05", "to within 0.02", "tolerance of 0.1mm".
_PLUS_MINUS = re.compile(
    r"(?:\u00b1|\+\s*/\s*-|\+-)\s*(?P<a>\d+(?:\.\d+)?)"
    r"|\bto\s+within\s+(?P<b>\d+(?:\.\d+)?)\s*mm"
    r"|\btoleranc\w*\s+(?:of\s+)?(?P<c>\d+(?:\.\d+)?)\s*mm", re.I)

#: A general tolerance named in words rather than by class letter.
_CLASS_WORDS = [("fine", "f"), ("medium", "m"), ("coarse", "c")]
_GENERAL = re.compile(r"\bgeneral\s+toleranc\w*\b", re.I)

#: An ISO 286 fit against a size: "20H7", "\u00d820 H7", "a 25 H7 bore",
#: "30h6 shaft". The letter's case is the meaning, so nothing here folds it.
#: The lookbehind is what keeps a size chain out. "120x60x12" offers the
#: reader a 60 shaft to x12 - x is a real ISO 286 deviation letter and 12 a
#: real IT grade - and a sheet that calls the middle number of an overall
#: size a toleranced shaft is worse than one with no fits at all.
_FIT = re.compile(
    r"(?<![\w.])(?:\u00d8\s*)?(?P<size>\d+(?:\.\d+)?)\s*"
    r"(?P<fit>[A-HJ-Nac-hjk-nP-Zp-z]{1,2}\d{1,2})(?![\w.])")

#: Fit letters that are real ISO 286 deviations. Without this "20mm" reads
#: as a fit called "mm" and "4x8" as one called "x8".
_FIT_LETTERS = set("ABCDEFGHJKMNPRSTUVXYZabcdefghjkmnprstuvxyz")

#: Treatments a drawing names under FINISH. They are not roughness and not
#: a process: a part can be milled, held to 2768-m, finished Ra 1.6 and
#: then black anodised, and all four lines belong on the sheet.
_FINISHES = [
    ("hard anodis", "hard anodised"), ("hard anodiz", "hard anodised"),
    ("black anodis", "black anodised"), ("black anodiz", "black anodised"),
    ("anodis", "anodised"), ("anodiz", "anodised"),
    ("zinc plat", "zinc plated"), ("nickel plat", "nickel plated"),
    ("chrome plat", "chrome plated"), ("electroless nickel", "electroless nickel"),
    ("black oxide", "black oxide"), ("blacken", "black oxide"),
    ("powder coat", "powder coated"), ("passivat", "passivated"),
    ("galvanis", "galvanised"), ("galvaniz", "galvanised"),
    ("painted", "painted"), ("bead blast", "bead blasted"),
    ("shot blast", "shot blasted"), ("brush", "brushed"),
    ("polish", "polished"), ("tumbl", "tumbled"),
]

#: ISO 13715, written the dozen ways people write it.
_EDGES = re.compile(
    r"\b(?:break(?:ing)?\s+(?:all\s+)?(?:sharp\s+)?(?:edges|corners)"
    r"|deburr\w*|de-burr\w*|remove\s+(?:all\s+)?(?:sharp\s+)?burrs?"
    r"|no\s+sharp\s+edges)\b", re.I)

#: "3D printed" is a process and the word "printed" alone is in PROCESSES,
#: so the longer spellings are checked first.
_PROCESS_WORDS = [
    ("3d print", "printed"), ("3-d print", "printed"), ("fdm", "printed"),
    ("sls ", "printed"), ("additive", "printed"),
    ("cnc", "machined"), ("machin", "machined"), ("mill", "milled"),
    ("turn", "turned"), ("lathe", "turned"), ("cast", "cast"),
    ("injection mould", "moulded"), ("injection mold", "moulded"),
    ("mould", "moulded"), ("mold", "moulded"),
    ("laser cut", "sheet"), ("sheet metal", "sheet"), ("press brake", "sheet"),
    ("fold", "sheet"), ("weld", "fabricated"), ("extrud", "extruded"),
]


def _roughness(prompt: str) -> Optional[float]:
    match = _RA.search(prompt)
    if match is None:
        return None
    raw = match.group("a") or match.group("b") or match.group("c")
    value = _number(raw)
    # The preferred Ra series stops either side of this. A "surface finish
    # 50" is somebody talking about something else.
    return value if value and 0.0125 <= value <= 50 else None


def _general_tolerance(prompt: str) -> tuple[str, Optional[float]]:
    """The general tolerance as a class, as a figure, or as neither."""
    match = _CLASS_RE.search(prompt)
    if match:
        return TOLERANCE_CLASSES[match.group(1).lower()], None
    if _GENERAL.search(prompt):
        window = prompt[max(0, _GENERAL.search(prompt).start() - 30):
                        _GENERAL.search(prompt).end() + 40].lower()
        for word, letter in _CLASS_WORDS:
            if word in window:
                return TOLERANCE_CLASSES[letter], None
    found = _PLUS_MINUS.search(prompt)
    if found:
        value = _number(found.group("a") or found.group("b")
                        or found.group("c"))
        # A plus-or-minus bigger than a millimetre is somebody describing a
        # range, not a tolerance.
        if value and 0.001 <= value <= 1.0:
            return "", value
    return "", None


def _stated_fits(prompt: str) -> list[Fit]:
    """ISO 286 fits the request wrote out itself.

    "a 20H7 bore" is a dimension and a tolerance in one word, and it is how
    anybody who has made a part writes it. Carried as grounded: the engineer
    specified it, which is a stronger claim than a table lookup.
    """
    found: list[Fit] = []
    for match in _FIT.finditer(prompt):
        fit = match.group("fit")
        if fit[0] not in _FIT_LETTERS:
            continue
        grade = int(re.sub(r"\D", "", fit) or 0)
        # IT grades run 01 to 18; beyond that it is a part number.
        if not 1 <= grade <= 18:
            continue
        size = _number(match.group("size"))
        if size is None:
            continue
        where = "bore" if fit[0].isupper() else "shaft"
        found.append(Fit(feature=where, size_mm=size, fit=fit,
                         why="stated in the request", grounded=True))
    return found[:4]


def from_request(prompt: str, material: str = "") -> Specification:
    """The specification an engineer wrote into the request itself.

    ``read`` takes the Planner's specification block, and the road most
    parts come down now does not call a Planner: a request that states its
    own dimensions is read directly. Everything that made a sheet
    manufacturable - the tolerance class, the roughness, the finish, the
    fits - was arriving through a block nobody was filling in, so the sheet
    said "NO TOLERANCES ARE SPECIFIED" about a request that specified them.

    The one thing invented here is the fallback class. A drawing with no
    general tolerance is not a drawing a shop can quote, and ISO 2768-m is
    what a drawing office writes when nobody said otherwise - so it is
    written, and the whole specification is marked proposed, which is what
    puts "CONFIRM BEFORE MANUFACTURE" on the sheet. Nothing is claimed that
    is not also flagged.
    """
    body = " ".join(str(prompt or "").split())
    spec = Specification(material=_text(material))

    low = body.lower()
    for needle, name in _PROCESS_WORDS:
        if needle in low:
            spec.process = name
            break

    for needle, name in _FINISHES:
        if needle in low:
            spec.finish = name
            break

    spec.roughness = _roughness(body)
    spec.tolerance_class, spec.tolerance_mm = _general_tolerance(body)
    spec.break_edges = bool(_EDGES.search(body))

    stated_fits = _stated_fits(body)
    seen = {(f.size_mm, f.fit) for f in stated_fits}
    spec.fits = stated_fits + [f for f in ground_fits(body)
                               if (f.size_mm, f.fit) not in seen][:4]

    # Whether anything here was read or assumed. A request that named a
    # class, a figure or a roughness has been specified by a person; one
    # that named none has not, and the fallback below says so.
    spec.proposed = not (spec.tolerance_class or spec.tolerance_mm)
    if spec.proposed:
        spec.tolerance_class = DEFAULT_TOLERANCE

    floor = PROCESS_FLOOR.get(spec.process)
    if floor and spec.tolerance_class in _ORDER \
            and _ORDER.index(spec.tolerance_class) < _ORDER.index(floor):
        spec.notes.append(
            f"{spec.tolerance_class.upper()} IS TIGHT FOR A "
            f"{spec.process.upper()} PART — CHECK WITH THE SUPPLIER")
    return spec


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
    spec.by_planner = True

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
        by_planner=bool(raw.get("by_planner")),
        notes=[_text(n, 90) for n in (raw.get("notes") or []) if _text(n, 90)],
        roughness=_number(raw.get("roughness")),
        tolerance_mm=_number(raw.get("tolerance_mm")),
        break_edges=bool(raw.get("break_edges")),
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
