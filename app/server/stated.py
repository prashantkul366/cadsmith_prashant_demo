"""Dimensions the person actually stated, kept out of the Planner's reach.

The Planner is told, in its own system prompt, to "estimate reasonable
engineering dimensions" when a request does not give them.  That is the right
instruction for a request that leaves them open.  It is the wrong one for
"a cylinder 150mm diameter and 50mm long": there is nothing to estimate, and
yet the number the Planner writes into its plan is the one everything
downstream treats as the target - the Coder builds to it and ``spec`` grades
against it.  A plan that quietly rounds 150 to 140 is then measured correct,
because the plan is both the claim and the scoring key.

So the numbers a person wrote are read straight out of the prompt, before any
agent sees it, and carried separately from the plan.  Two things follow: the
Planner is handed them as settled rather than as suggestions, and ``spec``
can gate on some of them **hard**, which it can never do with a number the
Planner derived.

**What may be gated hard is narrower than what is read**, and the difference
is the whole design.  A stepped shaft "20mm diameter for 40mm long, then 12mm
diameter for 30mm long" states four numbers, and three of them - 40, 12, 30 -
appear nowhere in the finished part's bounding box, which measures 20 x 20 x
70.  Gating on all four would reject a perfectly correct shaft, and a gate
that rejects correct parts gets switched off.  So:

* **Hard**: bore diameters, hole counts, and overall sizes written in the one
  form that can only mean the overall size - "100mm by 60mm by 8mm".
* **Advisory**: every other stated number.  Still measured, still reported,
  still shown to the Judge as evidence - but it does not block on its own.

Both kinds go to the Planner in full, which is where most of the value is:
the common failure is not a part that misses a gate, it is a plan that
invented 140 where the request said 150.

Reading is deliberately timid.  Only phrases carrying both a number and its
role are read.  "50mm" alone, in a sentence about a bracket, is not read at
all: it could be anything, and guessing would put an invented requirement in
front of the person who wrote the prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from app.catalog import japanese

#: Roles checked against the holes in the solid rather than its extents.
BORE_ROLES = ("bore",)

#: Roles whose phrasing can only be describing the overall size, and which
#: may therefore block a run. "100mm by 60mm by 8mm" is one; "12mm diameter",
#: which might be a step on a shaft, is not.
HARD_ROLES = ("extent",)

#: Anything bigger than a building or smaller than a thou is a misread, not a
#: requirement: reading "2026mm" out of a date would be worse than reading
#: nothing at all.
MIN_MM, MAX_MM = 0.05, 5000.0

#: Longest spellings first, so "mm" is never read as a stray "m".
_UNIT = (r"(?:millimet(?:er|re)s?|centimet(?:er|re)s?|met(?:er|re)s?"
         r"|mm|cm|m)")
_TO_MM = {"mm": 1.0, "millimeter": 1.0, "millimetre": 1.0,
          "cm": 10.0, "centimeter": 10.0, "centimetre": 10.0,
          "m": 1000.0, "meter": 1000.0, "metre": 1000.0}

_V = r"(?P<v>\d+(?:\.\d+)?)"
_U = rf"\s*(?P<u>{_UNIT})\b"

#: Each pattern carries the number, its unit and its role in one phrase, so a
#: match cannot mean something else.
_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("diameter", re.compile(
        rf"{_V}{_U}\s*(?:outside\s+|outer\s+|o\.?d\.?\s+)?(?:diameter|dia)\b", re.I)),
    ("diameter", re.compile(
        rf"(?:outside\s+|outer\s+)?(?:diameter|dia)\b\s*(?:of\s*|is\s*)?{_V}{_U}", re.I)),
    ("diameter", re.compile(rf"[Ø⌀]\s*{_V}(?:{_U})?", re.I)),
    ("bore", re.compile(
        rf"{_V}{_U}\s*(?:inside\s+diameter|internal\s+diameter|i\.?d\.?\b|bore)", re.I)),
    ("bore", re.compile(
        rf"(?:inside\s+diameter|internal\s+diameter|bore)\s*(?:of\s*)?{_V}{_U}", re.I)),
    ("length", re.compile(rf"{_V}{_U}\s*(?:long\b|in\s+length)", re.I)),
    ("length", re.compile(rf"length\s*(?:of\s*|is\s*)?{_V}{_U}", re.I)),
    ("width", re.compile(rf"{_V}{_U}\s*(?:wide\b|in\s+width)", re.I)),
    ("width", re.compile(rf"width\s*(?:of\s*|is\s*)?{_V}{_U}", re.I)),
    ("height", re.compile(rf"{_V}{_U}\s*(?:tall\b|high\b|in\s+height)", re.I)),
    ("height", re.compile(rf"height\s*(?:of\s*|is\s*)?{_V}{_U}", re.I)),
    ("thickness", re.compile(rf"{_V}{_U}\s*(?:thick\b|wall\b)", re.I)),
    ("thickness", re.compile(rf"thickness\s*(?:of\s*|is\s*)?{_V}{_U}", re.I)),
    ("across", re.compile(rf"{_V}{_U}\s*across\s+(?:the\s+)?flats", re.I)),
]

#: "100mm by 60mm by 8mm", "100 x 60 x 8mm". At least one unit must appear,
#: so "20 tooth x 2 module" is not read as a size.
_CHAIN = re.compile(
    rf"(?P<a>\d+(?:\.\d+)?)\s*(?P<ua>{_UNIT})?\s*(?:by|x|×|\*)\s*"
    rf"(?P<b>\d+(?:\.\d+)?)\s*(?P<ub>{_UNIT})?"
    rf"(?:\s*(?:by|x|×|\*)\s*(?P<c>\d+(?:\.\d+)?)\s*(?P<uc>{_UNIT})?)?",
    re.I)
_SQUARE = re.compile(rf"{_V}{_U}\s*square\b", re.I)

#: Words that turn a chain into something other than an overall size.
#: "four 3.4mm holes in a 70mm x 50mm pattern" states a hole pitch, and the
#: pitch appears nowhere in the finished part's bounding box - gating on it
#: would reject a plate that is exactly right. Checked in the words just
#: after the chain, which is where the qualifier is written.
_NOT_A_SIZE = re.compile(
    r"^\s*(?:\w+\s+){0,2}?(?:pattern|pitch|grid|array|spacing|spaced|centres|"
    r"centers|apart|pcd|bolt\s+circle"
    # A finishing callout is written as a chain and is not the part's size.
    # "0.5 mm x 45 deg chamfer" was read as a part 45 mm across - and every
    # prompt in a dimensioned library ends with one, so every part failed
    # the gate for a number that was an angle.
    r"|deg\b|degree|chamfer|countersink|counterbore|c'?bore|csk"
    # "counterbored Dia 17.5 x 11 deep" is a hole's depth, not an extent.
    r"|deep\b)\b", re.I)

#: A chain introduced by a diameter or a radius describes one feature, not
#: the part. "Dia 14 x 3 deep", "R12.5 x 8" - the first number is already
#: read as a diameter by its own pattern, and neither is an overall size.
_FEATURE_CHAIN = re.compile(
    r"(?:\bdia\b|\bdiameter\b|\bradius\b|\bbore\b|\bthread\b|"
    r"\bM\d|[\u00d8\u2300R])\s*[\d.]*\s*$", re.I)

_WORD_COUNT = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
               "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
               "eleven": 11, "twelve": 12}

#: "four 6mm holes", "six 9mm bolt holes", "4 x 6mm holes". The unit is
#: required: without it "four 6 holes" is as likely to be a typo as a size.
_HOLES = re.compile(
    rf"(?<![\d.])\b(?P<count>\d{{1,3}}|{'|'.join(_WORD_COUNT)})\s*(?:x\s*)?"
    rf"(?P<dia>\d+(?:\.\d+)?)\s*(?P<u>{_UNIT})\b\s*"
    rf"(?:[\w-]+\s+){{0,3}}?holes\b", re.I)
#: "a 5mm diameter hole", "a single 8mm hole"
_ONE_HOLE = re.compile(
    rf"\b(?:a|an|one|single)\s+(?:single\s+)?{_V}{_U}\s*"
    rf"(?:[\w-]+\s+){{0,3}}?hole\b", re.I)
#: "with a hole in the centre" - counted, size unknown.
_BARE_HOLE = re.compile(r"\b(?:a|an|one|single)\s+(?:[\w-]+\s+){0,2}?hole\b", re.I)
#: "the four mounting holes" - a count with no size. Worth reading on its
#: own: how many holes a part carries is the claim that fails most visibly,
#: and it is checked as a shortfall, so reading it can only tighten.
_COUNT_HOLES = re.compile(
    rf"(?<![\d.])\b(?P<count>\d{{1,3}}|{'|'.join(_WORD_COUNT)})\s+"
    rf"(?:[\w-]+\s+){{0,3}}?holes\b", re.I)


#: What makes a number in front of "holes" a diameter rather than a count.
#: "Two Dia 8 H7 dowel holes" offers the reader an 8 and a Two, and the
#: nearest number wins - so a part with two holes was failed for not having
#: eight. The gate blocks on a shortfall, so an over-count is the one
#: direction that costs a correct part.
_NOT_A_COUNT = re.compile(
    r"(?:\bdia\b|\bdiameter\b|\bradius\b|\bbore\b|\bM|[\u00d8\u2300R])"
    r"\s*$", re.I)


def _is_a_count(text: str, start: int) -> bool:
    """Whether the number at ``start`` is a quantity and not a size."""
    return not _NOT_A_COUNT.search(text[max(0, start - 14):start])


@dataclass(frozen=True)
class Stated:
    """One dimension the request gave, and the phrase it came from."""
    value: float
    role: str
    phrase: str

    @property
    def is_bore(self) -> bool:
        return self.role in BORE_ROLES

    @property
    def is_hard(self) -> bool:
        """May this number block a run on its own?"""
        return self.role in HARD_ROLES or self.is_bore

    def describe(self) -> str:
        return f"{self.role} {self.value:g} mm"


def _to_mm(raw: str, unit: Optional[str]) -> Optional[float]:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if unit:
        key = unit.lower().rstrip("s")
        value *= _TO_MM.get(key, 1.0)
    return value if MIN_MM <= value <= MAX_MM else None


def _english(prompt: str) -> str:
    text = japanese.to_english(prompt) if japanese.has_japanese(prompt) else prompt
    return " ".join(text.split())


def _dedupe(found: Iterable[Stated]) -> list[Stated]:
    seen: set[tuple[str, float]] = set()
    out: list[Stated] = []
    for item in found:
        key = (item.role, round(item.value, 4))
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def read(prompt: str) -> list[Stated]:
    """Every dimension the request states outright."""
    text = _english(prompt)
    found: list[Stated] = []

    for match in _CHAIN.finditer(text):
        unit = match.group("ua") or match.group("ub") or match.group("uc")
        if not unit:
            continue                    # no unit anywhere: not a size
        phrase = match.group(0).strip()
        # A chain qualified as a pattern or pitch is not the overall size.
        # It is still worth telling the Planner about, so it is kept - just
        # not as something that can block.
        before = text[max(0, match.start() - 24):match.start()]
        role = ("pitch" if (_NOT_A_SIZE.match(text[match.end():])
                            or _FEATURE_CHAIN.search(before))
                else "extent")
        for name in ("a", "b", "c"):
            raw = match.group(name)
            if raw is None:
                continue
            value = _to_mm(raw, unit)
            if value is not None:
                found.append(Stated(value, role, phrase))

    for match in _SQUARE.finditer(text):
        value = _to_mm(match.group("v"), match.group("u"))
        if value is not None:
            found.append(Stated(value, "extent", match.group(0).strip()))

    for role, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            value = _to_mm(match.group("v"), match.groupdict().get("u"))
            if value is not None:
                found.append(Stated(value, role, match.group(0).strip()))

    return _dedupe(found)


def holes(prompt: str) -> tuple[Optional[int], list[float]]:
    """How many holes the request asks for, and at what diameters.

    Diameters repeat, one per hole, so a request for four 6mm holes cannot be
    satisfied by a part carrying one of them.
    """
    text = _english(prompt)
    total = 0
    diameters: list[float] = []
    spans: list[tuple[int, int]] = []

    for match in _HOLES.finditer(text):
        if not _is_a_count(text, match.start("count")):
            continue
        raw = match.group("count").lower()
        count = _WORD_COUNT.get(raw)
        if count is None:
            try:
                count = int(raw)
            except ValueError:
                continue
        if not 1 <= count <= 200:
            continue
        value = _to_mm(match.group("dia"), match.group("u"))
        total += count
        spans.append(match.span())
        if value is not None:
            diameters.extend([value] * count)

    def overlaps(span: tuple[int, int]) -> bool:
        return any(span[0] < end and start < span[1] for start, end in spans)

    for match in _ONE_HOLE.finditer(text):
        if overlaps(match.span()):
            continue
        value = _to_mm(match.group("v"), match.group("u"))
        total += 1
        spans.append(match.span())
        if value is not None:
            diameters.append(value)

    for match in _COUNT_HOLES.finditer(text):
        if overlaps(match.span()):
            continue
        if not _is_a_count(text, match.start("count")):
            continue
        raw = match.group("count").lower()
        count = _WORD_COUNT.get(raw)
        if count is None:
            try:
                count = int(raw)
            except ValueError:
                continue
        if 1 <= count <= 200:
            total += count
            spans.append(match.span())

    for match in _BARE_HOLE.finditer(text):
        if not overlaps(match.span()):
            total += 1
            spans.append(match.span())

    return (total or None), diameters


#: A thread named in a request, and whether the hole is tapped for it or
#: clears it. The two are nothing alike: a tapped M8 hole is drilled 6.8 and
#: a clearance M8 hole is drilled 9, so a request that says which one it
#: wants has stated a diameter without writing a number down.
_THREAD = re.compile(r"\bM(?P<size>3|4|5|6|8|10|12|16|20|24)\b", re.I)

#: The words that make it a clearance hole rather than a tapped one, read
#: either side of the thread: "M8 clearance", "clearance for M8", "a hole an
#: M8 passes through".
_CLEARS = re.compile(r"\bclear(?:ance|ing)?\b|\bpass(?:es)?\s+through\b"
                     r"|\bfree\s+fit\b|\bthrough\s+hole\s+for\b", re.I)
_TAPS = re.compile(r"\btapp?ed\b|\bthreaded?\b|\bscrew(?:s|ed)?\s+into\b"
                   r"|\bfemale\s+thread\b", re.I)

#: ISO 262 tapping drills and ISO 273 medium clearance, which is what the
#: numbers above actually are. Kept here as well as in freecad_tools so that
#: reading a request does not need FreeCAD.
TAP_DRILL = {3: 2.5, 4: 3.3, 5: 4.2, 6: 5.0, 8: 6.8, 10: 8.5, 12: 10.2,
             16: 14.0, 20: 17.5, 24: 21.0}
CLEARANCE_DRILL = {3: 3.4, 4: 4.5, 5: 5.5, 6: 6.6, 8: 9.0, 10: 11.0,
                   12: 13.5, 16: 17.5, 20: 22.0, 24: 26.0}

#: "4 off", "6 off Ø8.5" - the drawing-office way of saying how many.
_OFF = re.compile(r"\b(?P<n>\d{1,2})\s*off\b", re.I)


def threads(prompt: str) -> list[dict]:
    """Every thread the request names, and the hole each one means.

    A request saying "two M8 tapped holes" has stated a diameter - 6.8 - and
    written no number at all. Without this the gate has a hole count and
    nothing to check the holes against, which is how a part came back with
    the right number of wrong holes.
    """
    found: list[dict] = []
    text = prompt or ""

    def nearest(pattern, at: int) -> Optional[int]:
        """How far the closest such word is from this thread, or None.

        Distance rather than presence, because one sentence names several
        threads - "two M8 tapped holes and an M10 clearance hole" - and
        whichever qualifier happens to be in a fixed window would give both
        of them the same answer, which is wrong for one of them.
        """
        best = None
        for word in pattern.finditer(text):
            gap = (at - word.end()) if word.end() <= at else (word.start() - at)
            if gap < 0 or gap > 45:
                continue
            best = gap if best is None else min(best, gap)
        return best

    for match in _THREAD.finditer(text):
        size = int(match.group("size"))
        at = match.start()
        clears, taps = nearest(_CLEARS, at), nearest(_TAPS, at)
        if clears is None and taps is None:
            continue        # an M8 screw is a fastener, not a hole
        if taps is None or (clears is not None and clears <= taps):
            kind, drilled = "clearance", CLEARANCE_DRILL.get(size)
        else:
            kind, drilled = "tapped", TAP_DRILL.get(size)
        if drilled:
            found.append({"spec": f"M{size}", "kind": kind, "drilled": drilled})
    return found


def requirements(prompt: str) -> dict:
    """Everything read from one request, in a shape the plan can carry."""
    dimensions = read(prompt)
    count, hole_dia = holes(prompt)
    bores = sorted([s.value for s in dimensions if s.is_bore] + list(hole_dia))
    # A "5mm diameter hole" reads as both a diameter and a bore. It is the
    # bore that is meant, so it must not also be advised as an extent - the
    # advisory check looks for extents, and would report a hole missing from
    # the outside of the part.
    bore_values = {round(d, 4) for d in bores}
    named = threads(prompt)
    if count is None:
        # "4 off" is how a drawing office writes a quantity, and it is the
        # only thing in the sentence that is one.
        off = _OFF.search(prompt or "")
        if off:
            count = int(off.group("n"))
    return {
        "extents": sorted({round(s.value, 4) for s in dimensions
                           if s.role in HARD_ROLES} - bore_values),
        "advisory": sorted({round(s.value, 4) for s in dimensions
                            if not s.is_hard} - bore_values),
        "bores": [round(d, 4) for d in bores],
        "hole_count": count,
        # The threads the request named, with the hole each one means.
        # Additive: nothing that already read this dictionary sees a
        # difference, and the gate on the FreeCAD road folds them into the
        # bores it checks.
        "threads": named,
        "read": [{"value": s.value, "role": s.role, "phrase": s.phrase,
                  "hard": s.is_hard} for s in dimensions],
    }


def note(prompt: str) -> str:
    """The paragraph handed to the Planner, or "" when nothing was stated.

    Written as a constraint rather than as information: the Planner's own
    instructions tell it to estimate, and this has to read as the case where
    there is nothing left to estimate.
    """
    dimensions = read(prompt)
    count, hole_dia = holes(prompt)
    if not dimensions and count is None:
        return ""

    lines = ["", "DIMENSIONS THE REQUEST STATES - use these exactly. Do not "
                 "re-derive, round or adjust them:"]
    for item in dimensions:
        lines.append(f"  - {item.describe()}  (from \"{item.phrase}\")")
    if count is not None:
        sizes = ", ".join(f"{d:g} mm" for d in sorted(set(hole_dia)))
        lines.append(f"  - {count} hole(s)" + (f", at {sizes}" if sizes else ""))
    lines.append("These are measured against the built solid. Estimate only "
                 "what is not listed here.")
    return "\n".join(lines) + "\n"
