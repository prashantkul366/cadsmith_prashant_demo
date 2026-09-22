"""Dimensions for standard hardware, taken from the published standards.

Numbers, not geometry.  This is the half of a parts catalogue that is plain
fact - an M8 socket head cap screw has a 13mm head and takes a 6mm key in
every catalogue on earth, because ISO 4762 says so - and it is the half that
fixes the failure this project actually keeps hitting: a model inventing a
plausible-looking dimension.  A NEMA 23 pilot bore is 38.1mm, not 22mm.

Geometry is built from these tables in ``parts.py``.  Nothing here depends
on CadQuery, so the Planner can be grounded in the numbers without anything
being built.

Sources: ISO 4762 (socket head cap screws), ISO 4014 (hex bolts), ISO 4032
(hex nuts), ISO 7089 (plain washers), ISO 273 (clearance holes), ISO 2338
(dowel pins), the ISO 15 bearing series, ISO 54 (gear modules), DIN 6885-1
(parallel keys), DIN 471 (retaining rings), DIN 1850 (plain bushings) and
ISO 4029 (set screws).

    These tables were transcribed by hand and carry nominal values only -
    no tolerances, no length-dependent thread runout.

    176 of the values are cross-checked against BOLTS, an independent open
    library of technical specifications, by ``app/tools/check_standards.py``.
    That covers ISO 4762, ISO 4014, ISO 4032, ISO 7089, the ISO 15 bearings
    and the coarse thread pitches; all of them agree.

    Not covered by that check, and still transcription only:

        clearance and tapping-drill columns of ``THREADS`` (ISO 273)
        ``NEMA_FRAMES``      - not a family BOLTS carries
        ``O_RING_CORDS``
        ``PARALLEL_KEYS``    - DIN 6885-1
        ``RETAINING_RINGS``  - DIN 471
        ``BUSHINGS``         - DIN 1850 / ISO 4379
        ``SET_SCREW_KEYS``   - ISO 4029
        ``GEAR_MODULES``     - ISO 54 series 1
        the belt profiles in ``parts.py``

    ``SHAFT_DIAMETERS`` is not a standard at all - it is the preferred-number
    list a shaft is normally drawn to, offered so that "a shaft" comes out at
    a size that can be bought.

    Nothing here carries tolerances, so read the standard before anything is
    manufactured from it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThreadSpec:
    """A metric coarse thread and the holes that go with it."""
    designation: str
    diameter: float          # nominal major diameter, mm
    pitch: float             # coarse pitch, mm
    clearance_close: float   # ISO 273 close fit
    clearance_normal: float  # ISO 273 normal (medium) fit
    tapping_drill: float     # for a coarse thread, ~ d - pitch


# ISO 261 coarse threads, with ISO 273 clearance holes.
THREADS: dict[str, ThreadSpec] = {
    spec.designation: spec for spec in (
        #         desig   d     pitch  close  normal  tap
        ThreadSpec("M2",   2.0,  0.40,  2.2,   2.4,   1.6),
        ThreadSpec("M2.5", 2.5,  0.45,  2.7,   2.9,   2.05),
        ThreadSpec("M3",   3.0,  0.50,  3.2,   3.4,   2.5),
        ThreadSpec("M4",   4.0,  0.70,  4.3,   4.5,   3.3),
        ThreadSpec("M5",   5.0,  0.80,  5.3,   5.5,   4.2),
        ThreadSpec("M6",   6.0,  1.00,  6.4,   6.6,   5.0),
        ThreadSpec("M8",   8.0,  1.25,  8.4,   9.0,   6.8),
        ThreadSpec("M10", 10.0,  1.50, 10.5,  11.0,   8.5),
        ThreadSpec("M12", 12.0,  1.75, 13.0,  13.5,  10.2),
        ThreadSpec("M16", 16.0,  2.00, 17.0,  17.5,  14.0),
        ThreadSpec("M20", 20.0,  2.50, 21.0,  22.0,  17.5),
        ThreadSpec("M24", 24.0,  3.00, 25.0,  26.0,  21.0),
    )
}


@dataclass(frozen=True)
class CapScrewSpec:
    """ISO 4762 socket head cap screw."""
    head_diameter: float     # dk
    head_height: float       # k, equal to the nominal diameter
    socket_across_flats: float   # s, the hex key size


ISO_4762: dict[str, CapScrewSpec] = {
    #                     dk     k     key
    "M2":   CapScrewSpec( 3.8,   2.0,  1.5),
    "M2.5": CapScrewSpec( 4.5,   2.5,  2.0),
    "M3":   CapScrewSpec( 5.5,   3.0,  2.5),
    "M4":   CapScrewSpec( 7.0,   4.0,  3.0),
    "M5":   CapScrewSpec( 8.5,   5.0,  4.0),
    "M6":   CapScrewSpec(10.0,   6.0,  5.0),
    "M8":   CapScrewSpec(13.0,   8.0,  6.0),
    "M10":  CapScrewSpec(16.0,  10.0,  8.0),
    "M12":  CapScrewSpec(18.0,  12.0, 10.0),
    "M16":  CapScrewSpec(24.0,  16.0, 14.0),
    "M20":  CapScrewSpec(30.0,  20.0, 17.0),
    "M24":  CapScrewSpec(36.0,  24.0, 19.0),
}


@dataclass(frozen=True)
class HexSpec:
    """A hexagonal head or nut: width across flats, and height."""
    across_flats: float      # s
    height: float            # k for a bolt head, m for a nut


ISO_4014: dict[str, HexSpec] = {      # hex head bolts
    "M4":  HexSpec( 7.0,  2.8),
    "M5":  HexSpec( 8.0,  3.5),
    "M6":  HexSpec(10.0,  4.0),
    "M8":  HexSpec(13.0,  5.3),
    "M10": HexSpec(16.0,  6.4),
    "M12": HexSpec(18.0,  7.5),
    "M16": HexSpec(24.0, 10.0),
    "M20": HexSpec(30.0, 12.5),
    "M24": HexSpec(36.0, 15.0),
}

ISO_4032: dict[str, HexSpec] = {      # hex nuts
    "M3":  HexSpec( 5.5,  2.4),
    "M4":  HexSpec( 7.0,  3.2),
    "M5":  HexSpec( 8.0,  4.7),
    "M6":  HexSpec(10.0,  5.2),
    "M8":  HexSpec(13.0,  6.8),
    "M10": HexSpec(16.0,  8.4),
    "M12": HexSpec(18.0, 10.8),
    "M16": HexSpec(24.0, 14.8),
    "M20": HexSpec(30.0, 18.0),
    "M24": HexSpec(36.0, 21.5),
}


@dataclass(frozen=True)
class WasherSpec:
    """ISO 7089 plain washer, 200 HV."""
    inner_diameter: float
    outer_diameter: float
    thickness: float


ISO_7089: dict[str, WasherSpec] = {
    "M3":  WasherSpec( 3.2,  7.0, 0.5),
    "M4":  WasherSpec( 4.3,  9.0, 0.8),
    "M5":  WasherSpec( 5.3, 10.0, 1.0),
    "M6":  WasherSpec( 6.4, 12.0, 1.6),
    "M8":  WasherSpec( 8.4, 16.0, 1.6),
    "M10": WasherSpec(10.5, 20.0, 2.0),
    "M12": WasherSpec(13.0, 24.0, 2.5),
    "M16": WasherSpec(17.0, 30.0, 3.0),
    "M20": WasherSpec(21.0, 37.0, 3.0),
    "M24": WasherSpec(25.0, 44.0, 4.0),
}


@dataclass(frozen=True)
class BearingSpec:
    """A deep groove ball bearing: bore, outside diameter, width."""
    bore: float              # d
    outer_diameter: float    # D
    width: float             # B


# ISO 15 dimension series. The 6000s are light, the 6200s medium and the
# 6300s heavy - same bore, progressively more load capacity and bulk.
BEARINGS: dict[str, BearingSpec] = {
    "608":  BearingSpec( 8.0, 22.0,  7.0),   # the skateboard bearing
    "6000": BearingSpec(10.0, 26.0,  8.0),
    "6001": BearingSpec(12.0, 28.0,  8.0),
    "6002": BearingSpec(15.0, 32.0,  9.0),
    "6003": BearingSpec(17.0, 35.0, 10.0),
    "6004": BearingSpec(20.0, 42.0, 12.0),
    "6005": BearingSpec(25.0, 47.0, 12.0),
    "6200": BearingSpec(10.0, 30.0,  9.0),
    "6201": BearingSpec(12.0, 32.0, 10.0),
    "6202": BearingSpec(15.0, 35.0, 11.0),
    "6203": BearingSpec(17.0, 40.0, 12.0),
    "6204": BearingSpec(20.0, 47.0, 14.0),
    "6205": BearingSpec(25.0, 52.0, 15.0),
    "6206": BearingSpec(30.0, 62.0, 16.0),
    "6300": BearingSpec(10.0, 35.0, 11.0),
    "6301": BearingSpec(12.0, 37.0, 12.0),
    "6302": BearingSpec(15.0, 42.0, 13.0),
    "6303": BearingSpec(17.0, 47.0, 14.0),
    "6304": BearingSpec(20.0, 52.0, 15.0),
    "6305": BearingSpec(25.0, 62.0, 17.0),
}


@dataclass(frozen=True)
class MotorFrameSpec:
    """A NEMA stepper motor frame, from the mounting face."""
    frame_size: float        # the square body, mm
    bolt_pattern: float      # square centres of the four mounting screws
    pilot_diameter: float    # the raised boss the plate must clear
    shaft_diameter: float
    mounting_screw: str      # the size that normally goes through the plate


# NEMA ICS 16 frame sizes. The pilot boss is the number most often got wrong:
# a NEMA 23 needs 38.1mm of clearance, and a plate bored 22mm - the NEMA 17
# figure - will not seat at all. That exact mistake is why this table exists.
NEMA_FRAMES: dict[str, MotorFrameSpec] = {
    #                        frame  pattern  pilot  shaft  screw
    "NEMA 8":  MotorFrameSpec( 20.3,  15.4,  15.0,  4.00, "M2.5"),
    "NEMA 11": MotorFrameSpec( 28.2,  23.0,  22.0,  5.00, "M2.5"),
    "NEMA 14": MotorFrameSpec( 35.2,  26.0,  22.0,  5.00, "M3"),
    "NEMA 17": MotorFrameSpec( 42.3,  31.0,  22.0,  5.00, "M3"),
    "NEMA 23": MotorFrameSpec( 56.4,  47.14, 38.1,  6.35, "M5"),
    "NEMA 34": MotorFrameSpec( 86.0,  69.6,  73.0, 14.00, "M6"),
    "NEMA 42": MotorFrameSpec(110.0,  88.9,  55.5, 19.00, "M8"),
}


# Standard O-ring cord diameters, metric. An O-ring is specified by its
# inside diameter and its cord, so the cord list is all that needs tabling.
O_RING_CORDS: tuple[float, ...] = (1.0, 1.5, 1.78, 2.0, 2.5, 2.62,
                                   3.0, 3.53, 4.0, 5.0, 5.33, 6.0, 7.0)


def clearance_hole(size: str, fit: str = "normal") -> float:
    """The hole a screw of this size passes through (ISO 273).

    The single most common dimension a model gets wrong: an M8 screw needs a
    9mm hole, not an 8mm one.
    """
    spec = THREADS[_normalise(size)]
    if fit == "close":
        return spec.clearance_close
    if fit == "normal":
        return spec.clearance_normal
    raise ValueError(f"Unknown fit '{fit}' - use 'close' or 'normal'.")


def tapping_drill(size: str) -> float:
    """The hole drilled before cutting a coarse internal thread."""
    return THREADS[_normalise(size)].tapping_drill


def counterbore(size: str) -> tuple[float, float]:
    """Diameter and depth of a counterbore that buries a cap screw head.

    The depth is the head height: flush.  Deepen it yourself if the head
    needs to sit below the surface.
    """
    key = _normalise(size)
    screw = ISO_4762[key]
    # 1mm of side clearance so the head is not a press fit in its own pocket.
    return screw.head_diameter + 1.0, screw.head_height


def _normalise(size: str) -> str:
    """Accept 'm8', 'M8', ' M8 ' and, for convenience, plain '8'."""
    key = str(size).strip().upper()
    if not key.startswith("M"):
        key = "M" + key
    if key not in THREADS:
        raise KeyError(f"No thread '{size}'. Known: {', '.join(THREADS)}")
    return key


def sizes() -> list[str]:
    return list(THREADS)


# ── the power-transmission half of the catalogue ────────────────────────
#
# Everything above this line fastens things together. Everything below it
# turns: the shaft, what keys it, what retains it, what it runs in, and the
# modules the gears on it are cut to. A gear on a shaft in a bearing is the
# assembly people actually ask this tool for, and until these tables existed
# only two of those four parts could be served.


# ISO 54 series 1 preferred modules. A gear is defined by any two of module,
# tooth count and diameter, so a request that gives only a diameter is not
# under-specified - it is one preferred module away from being exact, and
# this is the list to try. Series 2 (1.125, 1.375, 1.75, …) is deliberately
# left out: it exists, but nobody cuts a one-off gear to it.
GEAR_MODULES: tuple[float, ...] = (
    0.5, 0.6, 0.8, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0,
    5.0, 6.0, 8.0, 10.0, 12.0, 16.0, 20.0,
)


@dataclass(frozen=True)
class KeySpec:
    """A parallel key and the two slots it sits in, DIN 6885-1.

    ``shaft_depth`` and ``hub_depth`` are the numbers that get invented most
    often. They do not add up to the key height: the key stands proud of the
    shaft slot by less than the hub slot is deep, so the key bears on its
    flanks and never on its top face.
    """
    width: float             # b
    height: float            # h
    shaft_depth: float       # t1, measured from the shaft surface
    hub_depth: float         # t2, measured from the bore surface


# DIN 6885-1, keyed by the largest shaft diameter the key serves. A shaft is
# matched to the first row it does not exceed - see ``key_for_shaft``.
PARALLEL_KEYS: dict[float, KeySpec] = {
    #        b     h    t1   t2
     8.0: KeySpec( 2.0,  2.0, 1.2, 1.0),
    10.0: KeySpec( 3.0,  3.0, 1.8, 1.4),
    12.0: KeySpec( 4.0,  4.0, 2.5, 1.8),
    17.0: KeySpec( 5.0,  5.0, 3.0, 2.3),
    22.0: KeySpec( 6.0,  6.0, 3.5, 2.8),
    30.0: KeySpec( 8.0,  7.0, 4.0, 3.3),
    38.0: KeySpec(10.0,  8.0, 5.0, 3.3),
    44.0: KeySpec(12.0,  8.0, 5.0, 3.3),
    50.0: KeySpec(14.0,  9.0, 5.5, 3.8),
    58.0: KeySpec(16.0, 10.0, 6.0, 4.3),
    65.0: KeySpec(18.0, 11.0, 7.0, 4.4),
    75.0: KeySpec(20.0, 12.0, 7.5, 4.9),
    85.0: KeySpec(22.0, 14.0, 9.0, 5.4),
}


@dataclass(frozen=True)
class RetainingRingSpec:
    """An external circlip and its groove, DIN 471."""
    groove_diameter: float   # d3, the turned groove
    groove_width: float      # m, the groove wide enough for the ring
    thickness: float         # s, the ring's own thickness
    free_diameter: float     # d1, the ring relaxed and off the shaft


# DIN 471 external retaining rings, keyed by the shaft they fit. The groove
# is the part that has to be right: a ring dropped into a groove turned to
# the shaft diameter does not retain anything.
RETAINING_RINGS: dict[float, RetainingRingSpec] = {
    #                         d3     m     s     d1
     4.0: RetainingRingSpec( 3.70, 0.60, 0.40,  7.60),
     5.0: RetainingRingSpec( 4.70, 0.70, 0.60,  9.30),
     6.0: RetainingRingSpec( 5.60, 0.80, 0.70, 11.30),
     8.0: RetainingRingSpec( 7.60, 0.90, 0.80, 14.30),
    10.0: RetainingRingSpec( 9.60, 1.10, 1.00, 18.00),
    12.0: RetainingRingSpec(11.50, 1.10, 1.00, 20.20),
    14.0: RetainingRingSpec(13.40, 1.10, 1.00, 22.70),
    15.0: RetainingRingSpec(14.30, 1.10, 1.00, 24.00),
    16.0: RetainingRingSpec(15.20, 1.10, 1.00, 25.20),
    17.0: RetainingRingSpec(16.20, 1.10, 1.00, 26.20),
    20.0: RetainingRingSpec(19.00, 1.30, 1.20, 29.60),
    25.0: RetainingRingSpec(23.90, 1.30, 1.20, 36.30),
    30.0: RetainingRingSpec(28.60, 1.60, 1.50, 43.80),
    35.0: RetainingRingSpec(33.00, 1.60, 1.50, 50.00),
    40.0: RetainingRingSpec(37.50, 1.85, 1.75, 56.50),
    45.0: RetainingRingSpec(42.50, 1.85, 1.75, 62.40),
    50.0: RetainingRingSpec(47.00, 2.15, 2.00, 69.40),
}


@dataclass(frozen=True)
class BushingSpec:
    """A plain cylindrical sleeve bearing, DIN 1850 / ISO 4379."""
    bore: float              # d
    outer_diameter: float    # D
    length: float            # L, the preferred length for this bore


BUSHINGS: dict[float, BushingSpec] = {
     6.0: BushingSpec( 6.0,  8.0,  6.0),
     8.0: BushingSpec( 8.0, 10.0,  8.0),
    10.0: BushingSpec(10.0, 12.0, 10.0),
    12.0: BushingSpec(12.0, 14.0, 12.0),
    14.0: BushingSpec(14.0, 16.0, 15.0),
    16.0: BushingSpec(16.0, 18.0, 15.0),
    20.0: BushingSpec(20.0, 23.0, 20.0),
    25.0: BushingSpec(25.0, 28.0, 20.0),
    30.0: BushingSpec(30.0, 34.0, 30.0),
    35.0: BushingSpec(35.0, 39.0, 30.0),
    40.0: BushingSpec(40.0, 44.0, 40.0),
    50.0: BushingSpec(50.0, 55.0, 40.0),
}


# Preferred metric shaft diameters - R40 rounded to what is actually drawn
# and actually stocked. A shaft asked for at 13mm is not wrong, but a shaft
# asked for as "a shaft" should come out at one of these.
SHAFT_DIAMETERS: tuple[float, ...] = (
    3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 14.0, 15.0, 16.0, 17.0, 20.0,
    25.0, 30.0, 35.0, 40.0, 45.0, 50.0,
)


# ISO 4029 cup point socket set screws: the hex key across flats, by thread.
# The screw is otherwise a plain threaded cylinder, so the key size and the
# cup diameter are the whole table.
SET_SCREW_KEYS: dict[str, float] = {
    "M3": 1.5, "M4": 2.0, "M5": 2.5, "M6": 3.0,
    "M8": 4.0, "M10": 5.0, "M12": 6.0, "M16": 8.0,
}


def key_for_shaft(diameter: float) -> KeySpec:
    """The parallel key DIN 6885 puts on a shaft of this diameter.

    The table is keyed by the top of each range, so the first row the shaft
    does not exceed is its row.
    """
    for limit in sorted(PARALLEL_KEYS):
        if diameter <= limit:
            return PARALLEL_KEYS[limit]
    raise KeyError(f"No DIN 6885 key tabled for a {diameter:g}mm shaft "
                   f"(the table stops at {max(PARALLEL_KEYS):g}mm).")


def nearest_shaft(diameter: float) -> float:
    """The preferred shaft diameter closest to the one asked for."""
    return min(SHAFT_DIAMETERS, key=lambda d: (abs(d - diameter), d))


def gear_teeth_for_diameter(diameter: float, kind: str = "tip",
                            min_teeth: int = 10) -> tuple[int, float] | None:
    """A whole tooth count and preferred module giving this gear diameter.

    A gear asked for by diameter alone is not under-specified, it is
    unrounded: tip diameter is module x (teeth + 2) and pitch diameter is
    module x teeth, so every preferred module implies a tooth count, and
    most of them imply a fractional one. The best answer is the largest
    module that lands on a whole tooth count, because for a given diameter a
    coarser module is a stronger tooth - which is the choice a gear cutter
    makes too.

    Returns ``(teeth, module)``, or None if no preferred module gets within
    a tenth of a millimetre with at least ``min_teeth`` teeth.
    """
    offset = 2 if kind == "tip" else 0
    best = None
    for module in sorted(GEAR_MODULES, reverse=True):
        teeth = round(diameter / module) - offset
        if teeth < min_teeth:
            continue
        error = abs(module * (teeth + offset) - diameter)
        if error > 0.1:
            continue
        if best is None or error < best[2]:
            best = (teeth, module, error)
        if error < 1e-9:
            break      # exact, and modules are tried coarsest first
    return (best[0], best[1]) if best else None
