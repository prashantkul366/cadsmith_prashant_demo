"""Decide whether a request is a standard part, and which one.

The whole catalogue meets the pipeline here.  Three rules govern it:

**Only an unambiguous request routes.**  "An M8x30 socket head cap screw" is
a standard part.  "A bracket that takes four M8 screws" is a custom bracket
that happens to mention one, and must still be generated - substituting the
screw would hand back confidently wrong hardware.  When in doubt, return
None and let the pipeline do its job; a slower correct answer beats a fast
wrong one.

**Nothing is served without being built first.**  Every candidate goes
through ``verify.check``.  This is not belt-and-braces: cq_warehouse 0.8.0
returns washers as non-closed shells with twice the correct volume, and a
part like that reaching the Judge would be reported as a broken solid and
blamed on the pipeline. A part that fails verification is dropped and the
request falls through to the model.

**Missing libraries degrade, they do not break.**  cq_gears and cq_warehouse
are optional git dependencies; without them the catalogue is smaller and
everything still runs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from app.catalog import (handlebars, japanese, library, parts,
                         standards, verify)
from app.catalog.parts import CatalogPart

# A standard part named inside a bigger noun is a component of a custom part,
# not the deliverable. Shared with parts.select, and extended for the
# families the libraries add.
_CUSTOM_CONTEXT = parts._CUSTOM_CONTEXT + (
    "gearbox", "gear box", "reducer", "drivetrain", "transmission",
    "assembly", "for a gear", "gear train", "tensioner", "idler bracket",
)

_TEETH = re.compile(r"(\d+)\s*(?:-)?\s*(?:tooth|teeth|t\b)", re.I)
_MODULE = re.compile(r"\bmod(?:ule)?\.?\s*(\d+(?:\.\d+)?)", re.I)
_HELIX = re.compile(r"(\d+(?:\.\d+)?)\s*(?:deg|degree)", re.I)
_FACE_WIDTH = re.compile(r"(\d+(?:\.\d+)?)\s*mm\s*(?:wide|face|thick)", re.I)
_BORE = re.compile(r"(\d+(?:\.\d+)?)\s*mm\s*bore", re.I)
_WIRE = re.compile(r"(\d+(?:\.\d+)?)\s*mm\s*wire", re.I)
_OD = re.compile(r"(\d+(?:\.\d+)?)\s*mm\s*(?:od|outside diameter|outer diameter)",
                 re.I)
_FREE_LENGTH = re.compile(r"(\d+(?:\.\d+)?)\s*mm\s*(?:free length|long|length)",
                          re.I)
_COILS = re.compile(r"(\d+(?:\.\d+)?)\s*coils?", re.I)
_BELT = re.compile(r"\b(gt2|gt3|htd\s*5m|htd5m|htd|t5|t10)\b", re.I)

# A gear can be specified by diameter instead of by tooth count, and usually
# is: "a 50mm gear" is how people ask, because the diameter is the thing you
# can measure. Which diameter matters - tip and pitch differ by two modules -
# so the qualified forms are read first, and an unqualified one is taken as
# the tip diameter, which is what a caliper across the gear reads.
_PITCH_DIA = re.compile(
    r"pitch\s*(?:circle\s*)?dia(?:meter)?\.?\s*(?:of\s*|=\s*)?(\d+(?:\.\d+)?)"
    r"|(\d+(?:\.\d+)?)\s*(?:mm)?\s*pitch\s*(?:circle\s*)?dia(?:meter)?", re.I)
_TIP_DIA = re.compile(
    r"(?:tip|outside|outer|overall|major)\s*dia(?:meter)?\.?\s*(?:of\s*|=\s*)?"
    r"(\d+(?:\.\d+)?)"
    r"|(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:tip|outside|outer|overall|major)\s*"
    r"dia(?:meter)?", re.I)
_ANY_DIA = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*dia(?:meter)?\b"
    r"|dia(?:meter)?\.?\s*(?:of\s*|=\s*)?(\d+(?:\.\d+)?)", re.I)
#: "a 100mm spur gear" - a size sitting in front of the noun, with no word
#: saying which size it is. It is the diameter; nothing else about a gear is
#: quoted that way. The mm is required, so "a 20 tooth spur gear" cannot
#: match its own tooth count here.
_GEAR_SIZED = re.compile(
    r"(\d+(?:\.\d+)?)\s*mm\s+(?:\w+\s+){0,2}?(?:gear|pinion)\b", re.I)


def _first_group(pattern, text):
    """The first group that actually matched, for either-order patterns."""
    found = pattern.search(text)
    if not found:
        return None
    for value in found.groups():
        if value is not None:
            return float(value)
    return None


_GEAR_WORDS = ("gear", "pinion", "sprocket", "cog")


@dataclass
class Routed:
    """A catalogue part that has been built and checked."""
    part: CatalogPart
    report: verify.Report
    source: str          # which backend produced it


def _number(pattern, text, default=None, cast=float):
    found = pattern.search(text)
    return cast(found.group(1)) if found else default


#: Gear kinds that only cq_gears can build. Anything naming one of these is
#: declined without it rather than quietly served as a plain spur gear, which
#: would be the wrong part with the right tooth count.
_LIBRARY_ONLY_GEARS = ("helical", "herringbone", "bevel", "rack",
                       "ring gear", "internal gear", "annulus", "sprocket",
                       "worm", "hypoid")


def _is_plain_spur(lowered: str) -> bool:
    return not any(word in lowered for word in _LIBRARY_ONLY_GEARS)


def _gear(text: str) -> Optional[CatalogPart]:
    """A gear, if the request names one specifically enough."""
    lowered = text.lower()
    if not any(word in lowered for word in _GEAR_WORDS):
        return None
    # Spur gears are built here (app/catalog/parts.py) when cq_gears is
    # absent, so the commonest gear request is always answerable. The other
    # gear types genuinely need the library and are declined without it.
    if not library.HAVE_GEARS and "sprocket" not in lowered:
        if not _is_plain_spur(lowered):
            return None

    teeth = _number(_TEETH, text, cast=int)
    module = _number(_MODULE, text)
    face_width = _number(_FACE_WIDTH, text)
    bore = _number(_BORE, text)
    from_diameter = False

    if "sprocket" in lowered:
        if not library.HAVE_WAREHOUSE or teeth is None:
            return None
        return library.sprocket(teeth=teeth)

    # A rack has no tooth count, so it is allowed through without one.
    if "rack" in lowered:
        return library.rack_gear(module=module or 2.0)

    if teeth is None and _is_plain_spur(lowered):
        # A tooth count is one way to specify a gear; a diameter is another,
        # and the commoner one. Tip diameter is module x (teeth + 2), so a
        # diameter plus a preferred module from ISO 54 gives a whole tooth
        # count - or does not, in which case the gear really is unspecified
        # and the Planner should size it. See gear_teeth_for_diameter.
        pitch_dia = _first_group(_PITCH_DIA, text)
        tip_dia = _first_group(_TIP_DIA, text)
        plain_dia = (_first_group(_ANY_DIA, text)
                     or _number(_GEAR_SIZED, text))
        if plain_dia is not None and plain_dia in (bore, face_width, module):
            plain_dia = None         # "12mm bore diameter" is not the gear
        wanted, kind = ((pitch_dia, "pitch") if pitch_dia is not None
                        else (tip_dia, "tip") if tip_dia is not None
                        else (plain_dia, "tip"))
        if wanted is not None and wanted >= 8.0:
            derived = standards.gear_teeth_for_diameter(
                wanted, kind, min_teeth=17 if module is None else 5)
            if module is not None:
                # An explicit module is not ours to round away.
                offset = 2 if kind == "tip" else 0
                exact = wanted / module - offset
                derived = ((round(exact), module)
                           if abs(exact - round(exact)) < 0.02 and round(exact) >= 5
                           else None)
            if derived:
                teeth, module = derived
                from_diameter = True

    if teeth is None:
        # Neither a tooth count nor a diameter that lands on one. The Planner
        # can pick sensible numbers; the catalogue should not guess them.
        return None

    if "bevel" in lowered:
        return library.bevel_gear(module=module or 2.0, teeth=teeth,
                                  face_width=face_width or 8.0)
    if "herringbone" in lowered or "double helical" in lowered:
        return library.herringbone_gear(module=module or 2.0, teeth=teeth,
                                        face_width=face_width or 14.0,
                                        bore=bore or 8.0)
    if "ring gear" in lowered or "internal gear" in lowered or "annulus" in lowered:
        return library.ring_gear(module=module or 2.0, teeth=teeth,
                                 face_width=face_width or 10.0)
    if "helical" in lowered:
        angle = _number(_HELIX, text, 20.0)
        return library.spur_gear(module=module or 2.0, teeth=teeth,
                                 face_width=face_width or 12.0,
                                 bore=bore or 8.0, helix_angle=angle)
    if "spur" in lowered or "gear" in lowered or "pinion" in lowered:
        if library.HAVE_GEARS:
            return library.spur_gear(module=module or 2.0, teeth=teeth,
                                     face_width=face_width or 10.0,
                                     bore=bore or 8.0)
        chosen = module or 2.0
        # A gear asked for by tooth count keeps the defaults it always had -
        # five modules of face and an 8mm bore - because changing them would
        # quietly resize every gear anyone already asks for. A gear derived
        # from a diameter has no such history and nothing else to go on, so
        # it is proportioned to the size that was asked for: a 50mm gear on
        # an 8mm shaft is not what anyone means.
        if from_diameter:
            face_width = face_width or max(4.0, round(chosen * 4.0 * 2) / 2.0)
            bore = bore or standards.nearest_shaft(
                chosen * (teeth + 2) / 4.0)
        return parts.spur_gear(teeth=teeth, module=chosen,
                               face_width=face_width or 10.0,
                               bore=bore or 8.0)
    return None


def _spring(text: str) -> Optional[CatalogPart]:
    lowered = text.lower()
    if "spring" not in lowered:
        return None
    if "compression" not in lowered and "helical" not in lowered:
        # Extension and torsion springs need ends this builder does not make.
        return None
    wire = _number(_WIRE, text)
    outer = _number(_OD, text)
    if wire is None or outer is None:
        return None
    return parts.compression_spring(
        wire_diameter=wire, outer_diameter=outer,
        free_length=_number(_FREE_LENGTH, text, 50.0),
        coils=_number(_COILS, text, 8.0))


def _pulley(text: str) -> Optional[CatalogPart]:
    lowered = text.lower()
    if "pulley" not in lowered and "sheave" not in lowered:
        return None
    belt = _BELT.search(text)
    if not belt:
        return None  # a plain "pulley" is a V-belt or flat pulley, not this
    teeth = _number(_TEETH, text, cast=int)
    if teeth is None:
        return None
    key = belt.group(1).upper().replace(" ", "").replace("-", "")
    if key == "HTD":
        key = "HTD5M"
    if key not in parts.BELT_PROFILES:
        return None
    return parts.timing_pulley(
        teeth=teeth, belt=key,
        face_width=_number(_FACE_WIDTH, text, 7.0),
        bore=_number(_BORE, text, 5.0))


def _fastener(text: str) -> Optional[CatalogPart]:
    """Screws and nuts, preferring cq_warehouse for its far wider coverage.

    It carries 12 head types across M1.6-M64 where parts.py has two across
    M2-M24, so it leads. Falling back keeps the app working uninstalled.
    """
    lowered = text.lower()
    if not library.HAVE_WAREHOUSE:
        return parts.select(text)

    size_match = parts._SIZE.search(text)
    if not size_match:
        return parts.select(text)
    try:
        size = standards._normalise(size_match.group(1))
    except KeyError:
        return None
    if size not in standards.ISO_4762:
        return parts.select(text)

    threaded = "thread" in lowered and "no thread" not in lowered
    length = (_number(parts._LENGTH, text)
              or _number(parts._LENGTH_WORDS, text))

    if "nut" in lowered:
        for word, kind in (("flange", "hex_flange"), ("square", "square"),
                           ("cap nut", "domed_cap"), ("dome", "domed_cap"),
                           ("heat set", "heat_set"), ("heat-set", "heat_set")):
            if word in lowered:
                return library.nut(size, kind=kind, threaded=threaded)
        return library.nut(size, kind="hex", threaded=threaded)

    if "screw" in lowered or "bolt" in lowered:
        length = length or parts.size_lengths(size)
        for word, kind in (("countersunk", "countersunk"),
                           ("countersink", "countersunk"),
                           ("flat head", "countersunk"),
                           ("button", "button_head"),
                           ("cheese", "cheese_head"),
                           ("pan head", "pan_head"),
                           ("set screw", "set_screw"),
                           ("grub", "set_screw"),
                           ("hex head", "hex_head"),
                           ("hex bolt", "hex_head")):
            if word in lowered:
                return library.screw(size, length, kind=kind, threaded=threaded)
        if any(w in lowered for w in
               ("cap screw", "socket head", "shcs", "allen", "hex socket")):
            return library.screw(size, length, kind="socket_head",
                                 threaded=threaded)
        # Unqualified: a cap screw is the common case in machine design.
        return library.screw(size, length, kind="socket_head",
                             threaded=threaded)

    return parts.select(text)


# ── shafts and what goes on them ────────────────────────────────────────
#
# These run before the fastener finders because two of them would otherwise
# be answered wrongly rather than not at all: "M6 set screw" reaches a branch
# that serves a cap screw, and "a 12mm plain bearing" reaches one that looks
# for a 6203 and gives up. A wrong part is worse than no part.

#: The words that name each family, used to work out which one a request is
#: actually for - see _family_of. "A bearing for a 20mm shaft" is a bearing
#: request that mentions a shaft, and answering it with a shaft would be
#: silently wrong.
_FAMILY_WORDS = {
    "shaft": ("shaft", "axle"),
    "collar": ("collar",),
    "coupling": ("coupling", "coupler"),
    "key": ("parallel key", "machine key", "keystock", "key stock",
            "woodruff"),
    "bushing": ("bushing", "bush ", "sleeve bearing", "plain bearing",
                "journal bearing"),
    "ring": ("circlip", "retaining ring", "snap ring", "e-clip", "c-clip"),
    "rod": ("threaded rod", "studding", "all-thread", "allthread"),
    "setscrew": ("set screw", "setscrew", "grub screw", "grubscrew"),
    "gear": ("gear", "pinion", "sprocket"),
    "pulley": ("pulley", "sheave"),
    "spring": ("spring",),
    "bearing": ("ball bearing", "deep groove"),
}

_DIAMETER = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:dia(?:meter)?\b|\u00f8)"
    r"|(?:dia(?:meter)?\.?|\u00f8)\s*(?:of\s*|=\s*)?(\d+(?:\.\d+)?)", re.I)
_BORE_WORD = re.compile(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*bore"
                        r"|bore\s*(?:of\s*|=\s*)?(\d+(?:\.\d+)?)", re.I)
_LONG = re.compile(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:long\b|length)"
                   r"|length\s*(?:of\s*|=\s*)?(\d+(?:\.\d+)?)", re.I)
_ANY_MM = re.compile(r"(\d+(?:\.\d+)?)\s*mm\b", re.I)
#: "a 20mm shaft", "a 20 mm keyed shaft" - the size sitting in front of the
#: noun, which is how these are actually asked for. %s is the noun.
_SIZED = r"(\d+(?:\.\d+)?)\s*(?:mm)?\s+(?:\w+\s+){0,2}?%s"

#: What turns the rest of a sentence into a reference rather than the ask.
#: "A collar for a 12mm shaft" is a collar; "a 20mm shaft with a keyway" is a
#: shaft. Without this, whichever family word came last won both.
_REFERENCE = re.compile(
    r"\b(?:for|with|to fit|to suit|that fits|onto|on)\s+(?:a|an|the|its)?\b",
    re.I)


def _head(text: str) -> str:
    """The part of the request that names what is wanted."""
    found = _REFERENCE.search(text)
    return text[:found.start()] if found and found.start() > 0 else text


def _family_of(text: str) -> Optional[str]:
    """Which family this request is actually for.

    The last family word in the head of the request wins, because English
    puts the head noun last: a "shaft collar" is a collar, a "shaft coupling"
    is a coupling, and a "20mm shaft" is a shaft. Anything after "for a" or
    "with a" is a reference to another part and does not count - otherwise
    "a collar for a 12mm shaft" would be a shaft.
    """
    head = _head(text).lower()
    best, at = None, -1
    for family, words in _FAMILY_WORDS.items():
        for word in words:
            where = head.rfind(word)
            if where > at:
                best, at = family, where
    return best


#: A size and its optional unit, used to scan the words in front of a noun.
_SIZE_NEAR = re.compile(r"(\d+(?:\.\d+)?)\s*(?:mm)?", re.I)


def _sized_for(text: str, nouns: tuple[str, ...]) -> Optional[float]:
    """The size given for one of these nouns, however it was worded.

    The one nearest the noun wins. Taking the first number in the sentence
    read "150mm long 20mm shaft" as a 150mm shaft and declined it for being
    off the end of the table - which is what 「全長150mmの20mmシャフト」
    becomes, so the Japanese word order met an English pattern that had only
    ever been given the English one. The size that describes a noun is the
    size written against it.
    """
    lowered = text.lower()
    for noun in nouns:
        at = lowered.find(noun.strip().lower())
        if at < 0:
            continue
        # Far enough back for "20 mm keyed", not so far that it reaches the
        # size of whatever the sentence was talking about before this.
        found = _SIZE_NEAR.findall(text[max(0, at - 28):at])
        if found:
            return float(found[-1])
    return (_first_group(_BORE_WORD, text)
            or _first_group(_DIAMETER, text)
            or _number(_ANY_MM, text))


def _mentions(lowered: str, family: str) -> bool:
    return any(word in lowered for word in _FAMILY_WORDS[family])


def _set_screw(text: str) -> Optional[CatalogPart]:
    """A cup-point set screw. Deliberately ahead of the screw branches, which
    would otherwise hand back a cap screw with a head on it."""
    lowered = text.lower()
    if not _mentions(lowered, "setscrew"):
        return None
    if library.HAVE_WAREHOUSE:
        return None          # it cuts a real thread; let _fastener have it
    size = parts._SIZE.search(text)
    if not size:
        return None
    try:
        designation = standards._normalise(size.group(1))
    except KeyError:
        return None
    if designation not in standards.SET_SCREW_KEYS:
        return None
    length = (_number(parts._LENGTH, text) or _first_group(_LONG, text)
              or round(standards.THREADS[designation].diameter * 1.5, 1))
    return parts.set_screw(designation, length)


def _threaded_rod(text: str) -> Optional[CatalogPart]:
    lowered = text.lower()
    if not _mentions(lowered, "rod"):
        return None
    size = parts._SIZE.search(text)
    if not size:
        return None
    try:
        designation = standards._normalise(size.group(1))
    except KeyError:
        return None
    length = (_number(parts._LENGTH, text) or _first_group(_LONG, text))
    if length is None:
        return None          # studding with no length is not a part yet
    return parts.threaded_rod(designation, length)


def _shaft(text: str) -> Optional[CatalogPart]:
    """A plain, keyed or grooved shaft.

    Strict on purpose: "shaft" appears inside most requests that are about
    something else entirely, so a request only counts as a shaft request when
    it names no other family and gives a diameter.
    """
    lowered = text.lower()
    if _family_of(text) != "shaft":
        return None
    diameter = _sized_for(text, _FAMILY_WORDS["shaft"])
    if diameter is None or diameter < 3.0 or diameter > 50.0:
        return None
    length = _first_group(_LONG, text) or round(diameter * 6.0, 0)
    keyway = "keyway" in lowered or "keyed" in lowered or "keyslot" in lowered
    groove = ("groove" in lowered or "circlip" in lowered
              or "retaining ring" in lowered or "snap ring" in lowered)
    try:
        return parts.shaft(standards.nearest_shaft(diameter), length,
                           keyway=keyway, ring_groove=groove)
    except KeyError:
        return None


def _shaft_collar(text: str) -> Optional[CatalogPart]:
    lowered = text.lower()
    if _family_of(text) != "collar":
        return None
    bore = _sized_for(text, _FAMILY_WORDS["collar"])
    if bore is None or bore < 4.0 or bore > 50.0:
        return None
    clamp = "set screw" not in lowered and "grub" not in lowered
    return parts.shaft_collar(standards.nearest_shaft(bore), clamp=clamp)


def _coupling(text: str) -> Optional[CatalogPart]:
    lowered = text.lower()
    if _family_of(text) != "coupling":
        return None
    # A coupling joining two different shafts carries both sizes, and which
    # end is which does not matter - it is symmetric.
    pair = re.search(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:to|x|\u00d7|and)\s*"
                     r"(\d+(?:\.\d+)?)\s*(?:mm)?", text, re.I)
    if pair:
        first, second = float(pair.group(1)), float(pair.group(2))
    else:
        first = _sized_for(text, _FAMILY_WORDS["coupling"])
        second = first
    if first is None or not (4.0 <= first <= 50.0) or not (4.0 <= second <= 50.0):
        return None
    if "flexible" in lowered or "jaw" in lowered or "oldham" in lowered \
            or "bellows" in lowered or "spider" in lowered:
        return None          # a different part, and not one built here
    return parts.rigid_coupling(standards.nearest_shaft(first),
                                standards.nearest_shaft(second))


def _parallel_key(text: str) -> Optional[CatalogPart]:
    lowered = text.lower()
    if _family_of(text) != "key":
        return None
    if "woodruff" in lowered:
        return None          # a different profile, not built here
    shaft_size = _sized_for(text, ("shaft",)) or _first_group(_DIAMETER, text)
    if shaft_size is None or shaft_size > 85.0:
        return None
    length = _first_group(_LONG, text)
    try:
        return parts.parallel_key(shaft_size, length)
    except KeyError:
        return None


def _bushing(text: str) -> Optional[CatalogPart]:
    lowered = text.lower()
    if _family_of(text) != "bushing":
        return None
    if parts._BEARING.search(text):
        return None          # a designation means a ball bearing
    bore = _sized_for(text, ("bushing", "bush", "bearing"))
    if bore is None:
        return None
    length = _first_group(_LONG, text)
    try:
        return parts.plain_bushing(bore, length)
    except KeyError:
        return None


def _retaining_ring(text: str) -> Optional[CatalogPart]:
    lowered = text.lower()
    if _family_of(text) != "ring":
        return None
    if "internal" in lowered or "bore" in lowered:
        return None          # DIN 472 internal rings are not built here
    shaft_size = _sized_for(text, ("shaft", "circlip", "retaining ring",
                                   "snap ring"))
    if shaft_size is None:
        return None
    try:
        return parts.retaining_ring(shaft_size)
    except KeyError:
        return None


def select(text: str) -> Optional[Routed]:
    """The standard part this request asks for, built and checked.

    Returns None for anything custom, anything under-specified, and anything
    that fails verification.
    """
    # The backends are part of the cache key, not just the text: what the
    # catalogue can answer depends on which libraries are loaded, and keying
    # on text alone returned a cq_gears part after cq_gears was switched off.
    found = _select_cached(text, library.HAVE_GEARS, library.HAVE_WAREHOUSE)
    if found is not None or not japanese.has_japanese(text):
        return found

    # Every pattern below reads English, so a Japanese request matches none of
    # them and a Japanese user loses the catalogue entirely. Rewriting the
    # request into the vocabulary those patterns already speak recovers it.
    # Second, never first: an English request cannot reach this, and a
    # Japanese one that already matched is not rewritten either, so the
    # rewrite can only add matches - it can never change an existing one.
    return _select_cached(japanese.to_english(text),
                          library.HAVE_GEARS, library.HAVE_WAREHOUSE)


@lru_cache(maxsize=64)
def _select_cached(text: str, have_gears: bool,
                   have_warehouse: bool) -> Optional[Routed]:
    """Cached: the request handler asks whether the catalogue can answer
    before accepting a job, and the worker asks again when it runs it.
    Building a sprocket twice for one request is pure waste."""
    lowered = text.lower()
    if any(word in lowered for word in _CUSTOM_CONTEXT):
        return None

    for finder in (_gear, _pulley, _spring, _set_screw, _threaded_rod,
                   _shaft, _shaft_collar, _coupling, _parallel_key,
                   _bushing, _retaining_ring, _fastener, parts.select):
        try:
            candidate = finder(text)
        except Exception:
            continue  # a bad parse must never take the request down
        if candidate is None:
            continue
        report = verify.check(candidate)
        if not report.ok:
            # Built and unsound: drop it rather than serving it. The request
            # falls through to the model, which is slower but not wrong.
            continue
        return Routed(part=candidate, report=report,
                      source=_provenance(candidate))
    return None


def _provenance(part: CatalogPart) -> str:
    """Which backend actually built this, read from what the code imports.

    Taking the label from whichever finder matched was wrong: _fastener
    hands washer requests to parts.py, and they were still being reported as
    coming from cq_warehouse. The emitted code cannot misreport itself.
    """
    if "cq_gears" in part.code:
        return "cq_gears"
    if "cq_warehouse" in part.code:
        return "cq_warehouse"
    return "cadsmith"


def describe() -> dict:
    """What the catalogue can serve right now, for the health panel."""
    backends = library.available()
    families = ["washers", "o-rings", "dowel pins", "bearings",
                "compression springs", "timing pulleys", "spur gears",
                "shafts (keyed, grooved)", "parallel keys", "shaft collars",
                "shaft couplings", "plain bushings", "retaining rings",
                "set screws", "threaded rod",
                f"handlebars ({len(handlebars.BARS)} bends)"]
    if backends["cq_gears"]:
        families += ["helical", "herringbone", "ring", "rack", "bevel"]
    if backends["cq_warehouse"]:
        families += ["screws (12 heads)", "nuts (5 types)", "sprockets"]
    else:
        families += ["screws (2 heads)", "hex nuts"]
    return {"backends": backends, "families": families}
