"""Standard hardware, generated parametrically as CadQuery source.

The point of generating rather than importing: what comes out is *code*, with
the standard's dimensions as named assignments at the top.  So the app's code
panel shows real numbers, the parameter-patch editor can rewrite them, and
the Refiner can restructure the part - none of which is possible with a
downloaded STEP, which is a frozen shape with no history and no parameters.

    from app.catalog import parts
    screw = parts.socket_head_cap_screw("M8", 30)
    print(screw.code)        # standalone CadQuery, assigns `result`

Threads are not modelled.  A swept helix on a single M8x30 measured 283x the
build time and 224x the STEP size of a plain shank (2.5s and 1.3MB for one
screw), which is why every production CAD library shows fasteners with plain
shanks too.  Pass ``threaded=True`` if you want the real helix for a hero
render and can pay for it.

Origins are chosen so the part lands where it belongs when translated to a
feature: screws and bolts sit with the *bearing face under the head* at
z=0, everything else on its own base at z=0, axis along +Z.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.catalog import handlebars, standards


@dataclass(frozen=True)
class CatalogPart:
    id: str
    title: str
    standard: str
    code: str
    parameters: dict[str, float] = field(default_factory=dict)
    #: Optional: measure the built solid for whatever this family knows to
    #: care about, and say so in the shape validation.json carries. Left
    #: unset by the families whose only claim is a valid solid.
    inspect: Optional[Callable[[Any], list[dict]]] = None


def _n(value: float) -> str:
    """Format a dimension, always with a decimal point.

    Every number here is a length, and the app's parameter editor treats an
    assignment with no decimal point as a count and rounds edits to whole
    numbers - which would quietly turn an 8.4mm clearance hole into 8mm.
    """
    text = f"{float(value):g}"
    return text if "." in text or "e" in text else text + ".0"


def _across_corners(across_flats: float) -> float:
    """CadQuery's polygon() takes the circumscribed circle diameter."""
    return across_flats * 2.0 / 3.0 ** 0.5


_THREAD_SNIPPET = """
# A real helical thread. Expensive - see the note in app/catalog/parts.py.
helix = cq.Wire.makeHelix(pitch=pitch, height=length, radius=thread_diameter / 2.0)
crest = (
    cq.Workplane('XZ').center(thread_diameter / 2.0, 0)
    .polyline([(0, -pitch / 2.0), (0, pitch / 2.0), (-thread_depth, 0)])
    .close()
)
result = result.union(crest.sweep(cq.Workplane(helix), isFrenet=True))
"""


def socket_head_cap_screw(size: str = "M8", length: float = 30.0,
                          threaded: bool = False) -> CatalogPart:
    """ISO 4762 socket head cap screw - the workhorse of machine design."""
    key = standards._normalise(size)
    spec = standards.ISO_4762[key]
    thread = standards.THREADS[key]
    # ISO 4762 tables a minimum key engagement; a little over half the head
    # height is the usual simplification and always clears the minimum.
    socket_depth = round(spec.head_height * 0.55, 2)

    core = f"""import cadquery as cq

# Socket head cap screw to ISO 4762
# The bearing face under the head sits at z = 0, so translating this to a
# hole position drops the screw straight into place.
thread_diameter = {_n(thread.diameter)}
length = {_n(length)}                 # under the head, as the standard measures it
pitch = {_n(thread.pitch)}
head_diameter = {_n(spec.head_diameter)}
head_height = {_n(spec.head_height)}
socket_across_flats = {_n(spec.socket_across_flats)}
socket_depth = {_n(socket_depth)}
thread_depth = {_n(round(thread.pitch * 0.54, 3))}

# Shank, hanging below the bearing face
result = cq.Workplane('XY').circle(thread_diameter / 2.0).extrude(-length)

# Head, with the small chamfer the standard puts on its top edge
head = (
    cq.Workplane('XY').circle(head_diameter / 2.0).extrude(head_height)
    .edges('>Z').chamfer(head_diameter * 0.03)
)
result = result.union(head)

# Hex socket for the key
socket = (
    cq.Workplane('XY').workplane(offset=head_height)
    .polygon(6, {_n(round(_across_corners(spec.socket_across_flats), 4))})
    .extrude(-socket_depth)
)
result = result.cut(socket)
"""
    return CatalogPart(
        id=f"iso4762_{key.lower()}x{_n(length)}",
        title=f"Socket head cap screw {key} x {_n(length)}",
        standard="ISO 4762",
        code=core + (_THREAD_SNIPPET if threaded else ""),
        parameters={"thread_diameter": thread.diameter, "length": length,
                    "head_diameter": spec.head_diameter,
                    "head_height": spec.head_height},
    )


def hex_bolt(size: str = "M8", length: float = 30.0) -> CatalogPart:
    """ISO 4014 hex head bolt."""
    key = standards._normalise(size)
    spec = standards.ISO_4014[key]
    thread = standards.THREADS[key]

    code = f"""import cadquery as cq

# Hex head bolt to ISO 4014
# Bearing face under the head at z = 0.
thread_diameter = {_n(thread.diameter)}
length = {_n(length)}
head_across_flats = {_n(spec.across_flats)}
head_height = {_n(spec.height)}

result = cq.Workplane('XY').circle(thread_diameter / 2.0).extrude(-length)

head = (
    cq.Workplane('XY')
    .polygon(6, {_n(round(_across_corners(spec.across_flats), 4))})
    .extrude(head_height)
)
result = result.union(head)

# Chamfer the corners off the top of the head, as forging leaves them
result = result.faces('>Z').chamfer(head_across_flats * 0.06)
"""
    return CatalogPart(
        id=f"iso4014_{key.lower()}x{_n(length)}",
        title=f"Hex head bolt {key} x {_n(length)}",
        standard="ISO 4014", code=code,
        parameters={"thread_diameter": thread.diameter, "length": length,
                    "head_across_flats": spec.across_flats,
                    "head_height": spec.height},
    )


def hex_nut(size: str = "M8") -> CatalogPart:
    """ISO 4032 hex nut.

    The bore is the nominal diameter rather than the thread's minor
    diameter, so a nut and its screw sit tangent in an assembly instead of
    interfering. That is the usual simplification for unthreaded hardware.
    """
    key = standards._normalise(size)
    spec = standards.ISO_4032[key]
    thread = standards.THREADS[key]

    code = f"""import cadquery as cq

# Hex nut to ISO 4032
across_flats = {_n(spec.across_flats)}
thickness = {_n(spec.height)}
bore_diameter = {_n(thread.diameter)}

result = (
    cq.Workplane('XY')
    .polygon(6, {_n(round(_across_corners(spec.across_flats), 4))})
    .extrude(thickness)
)

# Both faces are chamfered on a real nut
result = result.faces('>Z').chamfer(across_flats * 0.05)
result = result.faces('<Z').chamfer(across_flats * 0.05)

result = (
    result.faces('>Z').workplane(centerOption='CenterOfBoundBox')
    .circle(bore_diameter / 2.0).cutThruAll()
)
"""
    return CatalogPart(
        id=f"iso4032_{key.lower()}", title=f"Hex nut {key}",
        standard="ISO 4032", code=code,
        parameters={"across_flats": spec.across_flats,
                    "thickness": spec.height,
                    "bore_diameter": thread.diameter},
    )


def flat_washer(size: str = "M8") -> CatalogPart:
    """ISO 7089 plain washer."""
    key = standards._normalise(size)
    spec = standards.ISO_7089[key]

    code = f"""import cadquery as cq

# Plain washer to ISO 7089
inner_diameter = {_n(spec.inner_diameter)}
outer_diameter = {_n(spec.outer_diameter)}
thickness = {_n(spec.thickness)}

result = (
    cq.Workplane('XY')
    .circle(outer_diameter / 2.0)
    .circle(inner_diameter / 2.0)
    .extrude(thickness)
)
"""
    return CatalogPart(
        id=f"iso7089_{key.lower()}", title=f"Plain washer {key}",
        standard="ISO 7089", code=code,
        parameters={"inner_diameter": spec.inner_diameter,
                    "outer_diameter": spec.outer_diameter,
                    "thickness": spec.thickness},
    )


def ball_bearing(designation: str = "6203") -> CatalogPart:
    """A deep groove ball bearing, simplified to a single solid.

    A real bearing is several bodies that move relative to each other, which
    is neither watertight nor useful to a kernel check. Catalogues ship a
    'simplified' envelope for exactly this reason: the bore, outside
    diameter and width are exact, so fit and clearance still check out, and
    a shallow recess on each face reads as the ring split.
    """
    key = str(designation).strip()
    if key not in standards.BEARINGS:
        raise KeyError(f"No bearing '{designation}'. "
                       f"Known: {', '.join(standards.BEARINGS)}")
    spec = standards.BEARINGS[key]
    band = (spec.outer_diameter - spec.bore) * 0.25

    code = f"""import cadquery as cq

# Deep groove ball bearing, simplified envelope to ISO 15
bore = {_n(spec.bore)}
outer_diameter = {_n(spec.outer_diameter)}
width = {_n(spec.width)}
ring_band = {_n(round(band, 3))}      # radial thickness of each ring
recess_depth = {_n(round(spec.width * 0.12, 3))}

result = (
    cq.Workplane('XY')
    .circle(outer_diameter / 2.0)
    .circle(bore / 2.0)
    .extrude(width)
)

# A shallow annular recess on each face, between the two rings, so the part
# reads as a bearing rather than a plain spacer.
#
# Both tools are extruded upward and overshoot the face they cut. An annular
# profile extruded downward from an offset plane comes out an invalid solid
# in this OCCT build, and cutting with it silently leaves the bearing
# unwatertight.
overshoot = 1.0
for base in (-overshoot, width - recess_depth):
    recess = (
        cq.Workplane('XY').workplane(offset=base)
        .circle(outer_diameter / 2.0 - ring_band)
        .circle(bore / 2.0 + ring_band)
        .extrude(recess_depth + overshoot)
    )
    result = result.cut(recess)
"""
    return CatalogPart(
        id=f"bearing_{key}", title=f"Deep groove ball bearing {key}",
        standard="ISO 15", code=code,
        parameters={"bore": spec.bore,
                    "outer_diameter": spec.outer_diameter,
                    "width": spec.width},
    )


def o_ring(inner_diameter: float = 20.0, cord: float = 2.5) -> CatalogPart:
    """An O-ring, specified the way they are sold: inside diameter x cord."""
    mean = inner_diameter + cord

    code = f"""import cadquery as cq

# O-ring, round cord section
inner_diameter = {_n(inner_diameter)}
cord_diameter = {_n(cord)}
mean_diameter = {_n(mean)}    # ID + cord: the circle the cord centre follows

# revolve() cannot close a full circular profile in this OCCT build - it
# raises StdFail_NotDone - so the torus is constructed directly. The volume
# matches Pappus exactly either way.
result = cq.Workplane(obj=cq.Solid.makeTorus(
    mean_diameter / 2.0, cord_diameter / 2.0))
"""
    return CatalogPart(
        id=f"oring_{_n(inner_diameter)}x{_n(cord)}",
        title=f"O-ring {_n(inner_diameter)} ID x {_n(cord)} cord",
        standard="ISO 3601", code=code,
        parameters={"inner_diameter": inner_diameter, "cord_diameter": cord},
    )


def dowel_pin(diameter: float = 6.0, length: float = 20.0) -> CatalogPart:
    """ISO 2338 parallel dowel pin, with the chamfered ends it is ground with."""
    chamfer = round(min(diameter * 0.12, 0.8), 2)

    code = f"""import cadquery as cq

# Parallel dowel pin to ISO 2338, m6 tolerance class
diameter = {_n(diameter)}
length = {_n(length)}
end_chamfer = {_n(chamfer)}

result = cq.Workplane('XY').circle(diameter / 2.0).extrude(length)
result = result.faces('>Z').chamfer(end_chamfer)
result = result.faces('<Z').chamfer(end_chamfer)
"""
    return CatalogPart(
        id=f"dowel_{_n(diameter)}x{_n(length)}",
        title=f"Dowel pin {_n(diameter)} x {_n(length)}",
        standard="ISO 2338", code=code,
        parameters={"diameter": diameter, "length": length},
    )


# ---------------------------------------------------------------------------
# Picking a part out of something someone typed.

# A \b after the digits fails on "M8x30", where a word character follows
# a word character and there is no boundary at all. A negative lookahead
# for more digits is what is actually meant.
# Nouns that mean "this is a part to be designed", not a catalogue lookup.
_CUSTOM_CONTEXT = (
    "housing", "bracket", "mount", "holder", "carrier", "enclosure",
    "manifold", "adapter", "adaptor", "fixture", "jig", "puller",
    "block for", "plate for", "body for", "seat for", "cover for",
    # A feature that receives the standard part is not the standard part.
    # "A groove for a 20x2.5 o-ring" wants the groove; handing back the
    # o-ring is the silent substitution this whole guard exists to stop.
    "groove for", "gland for", "slot for", "recess for", "pocket for",
    "channel for", "bore for", "hole for", "counterbore for",
    "clearance for", "cutout for", "cut-out for", "land for",
)

#: The word that makes a request a handlebar, and the words that take it
#: back. A riser, a clamp, a grip and a bar-end weight are all things that
#: attach to a bar and none of them is one, so they fall through to the
#: pipeline the way "a bearing housing for a 6203" does.
_BAR_NOUNS = ("handlebar", "handle bar", "drag bar", "ape hanger",
              "ape hangers", "tracker bar", "bars for")
_BAR_CONTEXT = ("riser", "clamp", "grip", "bar end", "bar-end", "barend",
                "mirror", "lever", "perch", "throttle", "switch", "weight",
                "mount", "holder", "stem")

#: Named bends, longest name first so "mini ape" is not read as "ape".
_BAR_STYLES = (
    ("mini ape", "mini_ape"), ("mini-ape", "mini_ape"),
    ("ape hanger", "ape"), ("ape bar", "ape"), ("apes", "ape"),
    ("drag bar", "drag"), ("drag handlebar", "drag"),
    ("tracker", "tracker"), ("commuter", "commuter"),
    ("classic", "classic"), ("roadster", "classic"),
    ("ultra low", "road_ultra_low"), ("ultra-low", "road_ultra_low"),
    ("low bend", "road_low"), ("low road", "road_low"),
    ("medium bend", "road_medium"), ("road bar", "road_medium"),
    ("road handlebar", "road_medium"),
    ("high bend", "road_high"), ("high road", "road_high"),
)

#: A width is three or four digits of millimetres, or a couple of dozen
#: inches. Neither can be confused with a tube size, which is the other
#: number in the sentence.
_BAR_WIDTH_MM = re.compile(r"(\d{3,4}(?:\.\d+)?)\s*mm", re.I)
_BAR_WIDTH_IN = re.compile(r"(2[0-9]|3[0-9]|4[0-5])(?:\.\d+)?\s*(?:in\b|inch|\")", re.I)
_BAR_RISE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(mm|in\b|inch|\")?\s*(?:of\s+)?rise", re.I)
_BAR_TUBE = {
    "7/8": 22.2, "22mm": 22.2, "22 mm": 22.2, "22.2": 22.2,
    "1 inch": 25.4, '1"': 25.4, "1 in ": 25.4, "25.4": 25.4, "25mm": 25.4,
    "1-1/4": 31.8, "1 1/4": 31.8, "31.8": 31.8,
}

_SIZE = re.compile(r"\bM\s?(\d+(?:\.\d+)?)(?![\d.])", re.I)
_LENGTH = re.compile(r"\bM\s?\d+(?:\.\d+)?\s*[x×*]\s*(\d+(?:\.\d+)?)", re.I)
_BEARING = re.compile(r"\b(6\d{3}|608)\b")
_ORING = re.compile(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:id|inside)?\s*[x×]\s*"
                    r"(\d+(?:\.\d+)?)", re.I)
_PIN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*[x×]\s*(\d+(?:\.\d+)?)", re.I)

#: The same two parts written out longhand. An engineer is as likely to type
#: "20mm inside diameter, 2.5mm cord" as "20x2.5", and the compact forms above
#: match neither. Each half is looked up on its own so the order of the two
#: phrases in the sentence does not matter.
_ORING_ID = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:inside|internal|inner|i\.?d\.?)"
    r"(?:\s*(?:diameter|dia\.?))?", re.I)
_ORING_CORD = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:cord|section|thickness)"
    r"(?:\s*(?:diameter|dia\.?))?", re.I)
_PIN_DIA = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:mm)?\s*(?:diameter|dia\.?|thick|across)", re.I)
#: "a 3mm dowel pin" - the diameter sits in front of the noun with no word
#: naming it, which is how the size is most often written.
_PIN_BARE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:mm)?\s+dowel", re.I)
_LENGTH_WORDS = re.compile(r"(\d+(?:\.\d+)?)\s*mm\s+long", re.I)


# ---------------------------------------------------------------------------
# Families neither cq_gears nor cq_warehouse covers
# ---------------------------------------------------------------------------

def compression_spring(wire_diameter: float = 2.0, outer_diameter: float = 20.0,
                       free_length: float = 50.0, coils: float = 8.0
                       ) -> CatalogPart:
    """A helical compression spring, swept along a real helix.

    ``free_length`` is the overall height an engineer measures, so the helix
    centreline runs one wire diameter shorter than that and the sweep is
    lifted half a wire off the base - otherwise a spring asked for at 50mm
    comes back 52mm tall.

    Ends are left open (neither closed nor ground): squaring them is a
    grinding operation on the real part and adds a boolean here for no
    benefit to a fit check.
    """
    code = f"""import cadquery as cq

wire_diameter = {_n(wire_diameter)}
outer_diameter = {_n(outer_diameter)}
free_length = {_n(free_length)}
active_coils = {_n(coils)}

mean_radius = (outer_diameter - wire_diameter) / 2.0
# Free length is the overall height, so the centreline is a wire shorter.
helix_height = free_length - wire_diameter
coil_pitch = helix_height / active_coils

helix = cq.Wire.makeHelix(
    pitch=coil_pitch, height=helix_height, radius=mean_radius)
result = (
    cq.Workplane('XZ')
    .center(mean_radius, 0)
    .circle(wire_diameter / 2.0)
    .sweep(cq.Workplane(helix), isFrenet=True)
    .translate((0, 0, wire_diameter / 2.0))
)
"""
    return CatalogPart(
        id=f"spring_d{wire_diameter:g}_od{outer_diameter:g}_l{free_length:g}",
        title=f"Compression spring, {wire_diameter:g} mm wire, "
              f"{outer_diameter:g} mm OD, {free_length:g} mm free length",
        standard="helical compression spring", code=code,
        parameters={"wire_diameter": wire_diameter,
                    "outer_diameter": outer_diameter,
                    "free_length": free_length, "coils": coils})


@dataclass(frozen=True)
class BeltProfile:
    """A timing belt tooth profile.

    ``groove_radius`` marks a curvilinear profile (GT2, HTD); ``tooth_depth``
    with ``half_top`` marks a trapezoidal one (the T series).
    """
    pitch: float
    tooth_depth: float
    pitch_line_offset: float
    groove_radius: float = 0.0   # curvilinear
    half_top: float = 0.0        # trapezoidal
    flank_angle: float = 20.0


#: The trapezoidal T-series profiles are exact - ISO 5296 defines them as
#: trapezoids. GT2 and HTD are approximated by a circular groove, which is
#: what every open-source pulley generator does and what prints correctly;
#: the true profiles are proprietary curves. Say so rather than implying
#: standard fidelity we do not have.
BELT_PROFILES: dict[str, BeltProfile] = {
    "GT2":   BeltProfile(pitch=2.0, tooth_depth=0.76, pitch_line_offset=0.254,
                         groove_radius=0.555),
    "HTD5M": BeltProfile(pitch=5.0, tooth_depth=2.06, pitch_line_offset=0.5715,
                         groove_radius=1.49),
    "T5":    BeltProfile(pitch=5.0, tooth_depth=1.2, pitch_line_offset=0.5,
                         half_top=1.325),
    "T10":   BeltProfile(pitch=10.0, tooth_depth=2.5, pitch_line_offset=1.0,
                         half_top=2.625),
}


def timing_pulley(teeth: int = 20, belt: str = "GT2",
                  face_width: float = 7.0, bore: float = 5.0) -> CatalogPart:
    """A timing belt pulley: GT2, HTD 5M, T5 or T10."""
    key = belt.upper().replace("-", "").replace(" ", "")
    if key not in BELT_PROFILES:
        raise KeyError(f"Unknown belt '{belt}'. "
                       f"Known: {', '.join(BELT_PROFILES)}")
    profile = BELT_PROFILES[key]
    pitch_d = teeth * profile.pitch / 3.141592653589793

    head = f"""import cadquery as cq
from math import pi, tan, radians

# Timing pulley, {key} tooth profile
teeth = {teeth}
belt_pitch = {_n(profile.pitch)}
face_width = {_n(face_width)}
pitch_line_offset = {_n(profile.pitch_line_offset)}

pitch_diameter = teeth * belt_pitch / pi
outer_radius = pitch_diameter / 2.0 - pitch_line_offset

result = cq.Workplane('XY').circle(outer_radius).extrude(face_width)
"""

    if profile.groove_radius:
        body = f"""
# Curvilinear profile, approximated by a circular groove on the pitch circle.
groove_radius = {_n(profile.groove_radius)}
grooves = (
    cq.Workplane('XY')
    .polarArray(pitch_diameter / 2.0, 0, 360, teeth)
    .circle(groove_radius)
    .extrude(face_width)
)
result = result.cut(grooves)
"""
    else:
        body = f"""
# Trapezoidal profile, exact per ISO 5296. One groove is built as a prism
# through the full face width - a timing pulley is a constant cross-section -
# then rotated into place around the rim.
tooth_depth = {_n(profile.tooth_depth)}
half_top = {_n(profile.half_top)}
flank_angle = {_n(profile.flank_angle)}

root_radius = outer_radius - tooth_depth
half_root = half_top - tooth_depth * tan(radians(flank_angle))
groove = (
    cq.Workplane('XY')
    .polyline([(-half_top, outer_radius + 1.0), (half_top, outer_radius + 1.0),
               (half_root, root_radius), (-half_root, root_radius)])
    .close()
    .extrude(face_width)
)
cutter = groove
for index in range(1, teeth):
    cutter = cutter.union(
        groove.rotate((0, 0, 0), (0, 0, 1), 360.0 * index / teeth))
result = result.cut(cutter)
"""

    tail = ""
    if bore:
        tail = f"""
bore_diameter = {_n(bore)}
result = (
    result.faces('>Z').workplane(centerOption='CenterOfBoundBox')
    .circle(bore_diameter / 2.0)
    .cutThruAll()
)
"""
    return CatalogPart(
        id=f"pulley_{key.lower()}_{teeth}t",
        title=f"{key} timing pulley, {teeth} teeth",
        standard=("ISO 5296 trapezoidal" if profile.half_top
                  else f"{key} curvilinear (approximated)"),
        code=head + body + tail,
        parameters={"teeth": teeth, "belt": key, "face_width": face_width,
                    "bore": bore, "pitch_diameter": pitch_d})



def spur_gear(teeth: int = 20, module: float = 2.0, face_width: float = 8.0,
              bore: float = 6.0, pressure_angle: float = 20.0) -> CatalogPart:
    """An involute spur gear, built here rather than fetched from a library.

    Gears are the standard part people ask for most, and until now they were
    the one family that needed an optional git dependency: without cq_gears
    the router refused every gear request outright. A spur gear is also the
    easiest of them to get exactly right, because the involute is closed-form
    - so this family stops depending on anything.

    Proportions follow the ISO 53 basic rack: addendum one module, dedendum
    1.25 modules, so tip diameter is module x (teeth + 2) and the circular
    tooth thickness at the pitch circle is pi x module / 2. The flank is a
    true involute, not the star polygon a language model reaches for.

    cq_gears is still the better answer for helical, herringbone, bevel, rack
    and ring gears, and the router prefers it for spur gears too when it is
    installed - it carries a trochoidal root fillet this does not.
    """
    if teeth < 5:
        raise ValueError(f"A spur gear needs at least 5 teeth, not {teeth}.")

    head = f"""import cadquery as cq
from math import acos, cos, sin, tan, pi, radians

# Involute spur gear, ISO 53 basic rack
module = {_n(module)}
teeth_number = {teeth}
pressure_angle = {_n(pressure_angle)}
face_width = {_n(face_width)}

# ISO 53 basic rack proportions: addendum one module, dedendum 1.25.
pitch_radius = module * teeth_number / 2.0
base_radius = pitch_radius * cos(radians(pressure_angle))
tip_radius = pitch_radius + module
root_radius = pitch_radius - 1.25 * module

# An involute exists only outside the base circle. Below about 41 teeth the
# base circle sits above the root, so the flank starts there and the profile
# drops radially to the root from its lowest involute point.
flank_start = max(base_radius, root_radius)
inv_pitch = tan(radians(pressure_angle)) - radians(pressure_angle)


def half_width(radius):
    \"\"\"Half the tooth's angular width at this radius, about its centreline.

    At the pitch radius this is pi / (2 * teeth_number), which makes the circular
    tooth thickness there exactly pi * module / 2 - the definition the whole
    involute system is built on.
    \"\"\"
    alpha = acos(min(1.0, base_radius / radius))
    return pi / (2.0 * teeth_number) + inv_pitch - (tan(alpha) - alpha)


def at(radius, angle):
    return (radius * cos(angle), radius * sin(angle))


pitch_angle = 2.0 * pi / teeth_number
root_half = half_width(flank_start)
# Eight points per flank. The involute is gentle enough over one tooth that
# a spline through them holds the profile to well under a micron.
radii = [flank_start + (tip_radius - flank_start) * i / 8.0
         for i in range(9)]

# Each flank is one spline through the involute; tip and root are straight.
# Splines rather than a dense polyline: chording every flank costs five times
# the faces for a worse surface, and each one lands in the STEP export.
profile = cq.Workplane('XY').moveTo(*at(root_radius, -root_half))
for tooth in range(teeth_number):
    centre = tooth * pitch_angle
    if flank_start > root_radius:
        profile = profile.lineTo(*at(flank_start, centre - root_half))
    profile = profile.spline([at(r, centre - half_width(r)) for r in radii[1:]],
                             includeCurrent=True)
    # The tip is two straight segments through a vertex on the centreline, so
    # the measured tip diameter is exactly module x (teeth_number + 2).
    profile = profile.lineTo(*at(tip_radius, centre))
    profile = profile.lineTo(*at(tip_radius, centre + half_width(tip_radius)))
    profile = profile.spline([at(r, centre + half_width(r))
                              for r in reversed(radii[:-1])],
                             includeCurrent=True)
    if flank_start > root_radius:
        profile = profile.lineTo(*at(root_radius, centre + root_half))
    # The next tooth opens with its own root point, closing this gap.
    profile = profile.lineTo(*at(root_radius, centre + pitch_angle - root_half))

result = profile.close().extrude(face_width)
"""

    tail = ""
    if bore:
        tail = f"""
bore_diameter = {_n(bore)}
result = (
    result.faces('>Z').workplane(centerOption='CenterOfBoundBox')
    .circle(bore_diameter / 2.0)
    .cutThruAll()
)
"""
    return CatalogPart(
        id=f"spur_gear_{teeth}t_m{_n(module).replace('.', 'p')}",
        title=f"Spur gear, {teeth} teeth, module {module:g}",
        standard="ISO 53 basic rack, 20\u00b0 involute",
        code=head + tail,
        parameters={"teeth": teeth, "module": module,
                    "face_width": face_width, "bore": bore,
                    "pressure_angle": pressure_angle,
                    "pitch_diameter": module * teeth,
                    "tip_diameter": module * (teeth + 2)},
    )


# ── the turning half: shafts and what goes on them ──────────────────────
#
# A gear, a bearing and a screw were servable; the shaft they all sit on was
# not, so "a 20mm shaft with a keyway" went to five agents to have a cylinder
# invented for it. These close that gap. The fastener tables above are
# published standards; where a family has no published geometry - collars and
# couplings are made to each maker's own proportions - the docstring says so
# and the proportions are parameters, not secrets.


def shaft(diameter: float = 20.0, length: float = 100.0,
          keyway: bool = False, keyway_length: float | None = None,
          ring_groove: bool = False) -> CatalogPart:
    """A plain round shaft, optionally keyed and grooved for a circlip.

    The shaft itself is only a cylinder. What is worth having from a
    catalogue is everything cut into it: a keyway to DIN 6885 depth t1, and
    a retaining-ring groove to DIN 471 - the two dimensions that get guessed
    at, and the two that stop the assembly going together when the guess is
    wrong. A keyway cut to the key's full height instead of t1 leaves the key
    bearing on its top face, which is exactly the failure the depth column
    exists to prevent.
    """
    chamfer = round(min(diameter * 0.05, 1.5), 2)
    lines = [
        "import cadquery as cq",
        "",
        "# Plain round shaft, axis along +Z, ends chamfered for entry",
        f"diameter = {_n(diameter)}",
        f"length = {_n(length)}",
        f"end_chamfer = {_n(chamfer)}",
        "",
        "result = cq.Workplane('XY').circle(diameter / 2.0).extrude(length)",
        "result = result.faces('>Z').chamfer(end_chamfer)",
        "result = result.faces('<Z').chamfer(end_chamfer)",
    ]
    parameters = {"diameter": diameter, "length": length}
    title = f"Shaft {_n(diameter)} dia x {_n(length)}"
    standard = "preferred diameter; ends chamfered"
    part_id = f"shaft_{_n(diameter)}x{_n(length)}"

    if keyway:
        spec = standards.key_for_shaft(diameter)
        run = keyway_length if keyway_length else round(length * 0.4, 1)
        run = min(run, length - 2 * chamfer - 2.0)
        lines += [
            "",
            "# Keyway to DIN 6885-1 for this shaft diameter. The depth is t1,",
            "# measured from the shaft surface - NOT the key's full height,",
            "# which would let the key bear on its top face instead of its",
            "# flanks. Cut with an end mill of the key's width, so the ends",
            "# are round: a sled-runner keyway, the common machined form.",
            f"key_width = {_n(spec.width)}",
            f"keyway_depth = {_n(spec.shaft_depth)}   # t1",
            f"keyway_length = {_n(run)}",
            "",
            "keyway_centre = length / 2.0",
            "cutter = (",
            "    cq.Workplane('YZ')",
            "    .workplane(offset=diameter / 2.0 - keyway_depth)",
            "    .center(0, keyway_centre)",
            "    .slot2D(keyway_length, key_width, angle=90)",
            "    .extrude(diameter)",
            ")",
            "result = result.cut(cutter)",
        ]
        parameters.update({"key_width": spec.width,
                           "keyway_depth": spec.shaft_depth,
                           "keyway_length": run})
        title += f", {_n(spec.width)}mm keyway"
        standard = "DIN 6885-1 keyway"
        part_id += "_keyed"

    if ring_groove:
        try:
            ring = standards.RETAINING_RINGS[standards.nearest_shaft(diameter)]
        except KeyError:
            ring = None
        if ring is not None:
            lines += [
                "",
                "# Retaining-ring groove to DIN 471. The groove diameter is d3,",
                "# well under the shaft: a groove turned to the shaft diameter",
                "# holds nothing.",
                f"groove_diameter = {_n(ring.groove_diameter)}   # d3",
                f"groove_width = {_n(ring.groove_width)}   # m",
                "groove_from_end = 6.0",
                "",
                "result = (",
                "    result.faces('>Z').workplane(centerOption='CenterOfBoundBox')",
                "    .workplane(offset=-groove_from_end)",
                "    .circle(diameter / 2.0 + 1.0)",
                "    .circle(groove_diameter / 2.0)",
                "    .cutBlind(-groove_width)",
                ")",
            ]
            parameters.update({"groove_diameter": ring.groove_diameter,
                               "groove_width": ring.groove_width})
            standard += " + DIN 471 groove"
            part_id += "_grooved"

    return CatalogPart(id=part_id, title=title, standard=standard,
                       code="\n".join(lines) + "\n", parameters=parameters)


def parallel_key(shaft_diameter: float = 20.0,
                 length: float | None = None) -> CatalogPart:
    """A DIN 6885-1 form A parallel key: the bar that goes in the keyway.

    Form A is round-ended, cut from bar with an end mill of the key's own
    width, so it drops into a sled-runner keyway without filing.
    """
    spec = standards.key_for_shaft(shaft_diameter)
    run = length if length else round(max(shaft_diameter * 1.5,
                                          spec.width * 4.0), 0)

    code = f"""import cadquery as cq

# Parallel key, DIN 6885-1 form A (round ends)
key_width = {_n(spec.width)}    # b
key_height = {_n(spec.height)}   # h
key_length = {_n(run)}   # l

# The overall length includes the two round ends, so the slot's length is
# the length, not the length plus a diameter.
result = (
    cq.Workplane('XY')
    .slot2D(key_length, key_width, angle=0)
    .extrude(key_height)
)
"""
    return CatalogPart(
        id=f"key_{_n(spec.width)}x{_n(spec.height)}x{_n(run)}",
        title=f"Parallel key {_n(spec.width)} x {_n(spec.height)} x {_n(run)}",
        standard=f"DIN 6885-1 form A, for a {_n(shaft_diameter)}mm shaft",
        code=code,
        parameters={"key_width": spec.width, "key_height": spec.height,
                    "key_length": run, "shaft_diameter": shaft_diameter,
                    "hub_depth": spec.hub_depth},
    )


def plain_bushing(bore: float = 12.0,
                  length: float | None = None) -> CatalogPart:
    """A DIN 1850 plain sleeve bearing - a bushing, not a ball bearing."""
    size = standards.nearest_shaft(bore)
    spec = standards.BUSHINGS.get(size)
    if spec is None:
        raise KeyError(f"No DIN 1850 bushing tabled for a {bore:g}mm bore.")
    run = length if length else spec.length

    code = f"""import cadquery as cq

# Plain sleeve bearing to DIN 1850 / ISO 4379
bore = {_n(spec.bore)}    # d
outer_diameter = {_n(spec.outer_diameter)}    # D
length = {_n(run)}    # L

result = (
    cq.Workplane('XY')
    .circle(outer_diameter / 2.0)
    .circle(bore / 2.0)
    .extrude(length)
)
# Lead-in chamfers, inside and out: a bushing is pressed into its housing
# and a shaft is pushed through it, and neither starts without one.
result = result.faces('>Z').chamfer(0.3)
result = result.faces('<Z').chamfer(0.3)
"""
    return CatalogPart(
        id=f"bushing_{_n(spec.bore)}x{_n(spec.outer_diameter)}x{_n(run)}",
        title=(f"Plain bushing {_n(spec.bore)} x "
               f"{_n(spec.outer_diameter)} x {_n(run)}"),
        standard="DIN 1850 / ISO 4379", code=code,
        parameters={"bore": spec.bore, "outer_diameter": spec.outer_diameter,
                    "length": run},
    )


def set_screw(size: str = "M6", length: float = 10.0) -> CatalogPart:
    """An ISO 4029 hexagon socket set screw with a cup point."""
    size = standards._normalise(size)
    thread = standards.THREADS[size]
    key = standards.SET_SCREW_KEYS.get(size)
    if key is None:
        raise KeyError(f"No ISO 4029 set screw tabled for {size}.")
    cup = round(thread.diameter * 0.55, 2)
    socket_depth = round(thread.diameter * 0.5, 2)

    code = f"""import cadquery as cq

# Hexagon socket set screw, cup point, ISO 4029
thread_diameter = {_n(thread.diameter)}
length = {_n(length)}
key_across_flats = {_n(key)}
cup_diameter = {_n(cup)}
socket_depth = {_n(socket_depth)}

result = cq.Workplane('XY').circle(thread_diameter / 2.0).extrude(length)

# The cup: the end is chamfered back to the cup diameter and then faced off,
# leaving the thin annular rim that bites into the shaft.
result = result.faces('<Z').chamfer((thread_diameter - cup_diameter) / 2.0)
result = (
    result.faces('<Z').workplane(centerOption='CenterOfBoundBox')
    .circle(cup_diameter / 2.0)
    .cutBlind(-{_n(round(thread.diameter * 0.08, 2))})
)

# The key socket, across flats, from the other end.
result = (
    result.faces('>Z').workplane(centerOption='CenterOfBoundBox')
    .polygon(6, key_across_flats * 2.0 / 3.0 ** 0.5)
    .cutBlind(-socket_depth)
)
"""
    return CatalogPart(
        id=f"set_screw_{size.lower()}x{_n(length)}",
        title=f"Set screw {size} x {_n(length)}, cup point",
        standard="ISO 4029", code=code,
        parameters={"thread_diameter": thread.diameter, "length": length,
                    "key_across_flats": key, "cup_diameter": cup},
    )


def threaded_rod(size: str = "M8", length: float = 100.0) -> CatalogPart:
    """A length of metric studding, turned to the thread's pitch diameter.

    The plain cylinder is the honest model: it is the pitch diameter, not
    the major diameter, so anything designed around it clears a real rod.
    Cutting the helix costs a minute of kernel time and gains nothing that
    is not already in the designation.
    """
    size = standards._normalise(size)
    thread = standards.THREADS[size]
    pitch_diameter = round(thread.diameter - 0.6495 * thread.pitch, 3)

    code = f"""import cadquery as cq

# Metric studding, {size} x {_n(thread.pitch)} coarse
major_diameter = {_n(thread.diameter)}
pitch_diameter = {_n(pitch_diameter)}   # major - 0.6495 * pitch
length = {_n(length)}

# Modelled at the pitch diameter, not the major: a nut or a clearance hole
# sized against this will fit the real rod. See the docstring.
result = cq.Workplane('XY').circle(pitch_diameter / 2.0).extrude(length)
result = result.faces('>Z').chamfer({_n(round(thread.pitch, 2))})
result = result.faces('<Z').chamfer({_n(round(thread.pitch, 2))})
"""
    return CatalogPart(
        id=f"threaded_rod_{size.lower()}x{_n(length)}",
        title=f"Threaded rod {size} x {_n(length)}",
        standard=f"ISO 261 coarse, pitch {_n(thread.pitch)}", code=code,
        parameters={"major_diameter": thread.diameter,
                    "pitch_diameter": pitch_diameter, "length": length,
                    "pitch": thread.pitch},
    )


def retaining_ring(shaft_diameter: float = 20.0) -> CatalogPart:
    """A DIN 471 external retaining ring, simplified to a constant width.

    The standard's three numbers that matter are here exactly: the groove
    diameter it seats on, its thickness, and its free outside diameter. The
    real ring's radial width tapers away from the lugs and the lugs carry
    pliers holes; this one is a plain C of constant width. Anything checking
    clearance, stack height or groove fit gets the right answer; anything
    checking the ring's own stress does not, and should use the standard.
    """
    size = standards.nearest_shaft(shaft_diameter)
    spec = standards.RETAINING_RINGS.get(size)
    if spec is None:
        raise KeyError(f"No DIN 471 ring tabled for a {shaft_diameter:g}mm shaft.")

    code = f"""import cadquery as cq

# External retaining ring, DIN 471 - simplified constant-width C
shaft_diameter = {_n(size)}
groove_diameter = {_n(spec.groove_diameter)}   # d3, the seat
free_diameter = {_n(spec.free_diameter)}    # d1, relaxed and off the shaft
thickness = {_n(spec.thickness)}    # s

# The opening has to clear the shaft to go on, so it is set from the shaft
# diameter rather than from the groove the ring ends up in.
opening = shaft_diameter * 0.55

result = (
    cq.Workplane('XY')
    .circle(free_diameter / 2.0)
    .circle(groove_diameter / 2.0)
    .extrude(thickness)
)
gap = (
    cq.Workplane('XY')
    .box(free_diameter, opening, thickness * 3.0,
         centered=(False, True, True))
    .translate((0, 0, thickness / 2.0))
)
result = result.cut(gap)
"""
    return CatalogPart(
        id=f"circlip_{_n(size)}",
        title=f"Retaining ring, {_n(size)}mm shaft",
        standard="DIN 471 (constant-width simplification)", code=code,
        parameters={"shaft_diameter": size,
                    "groove_diameter": spec.groove_diameter,
                    "groove_width": spec.groove_width,
                    "thickness": spec.thickness,
                    "free_diameter": spec.free_diameter},
    )


def shaft_collar(bore: float = 12.0, clamp: bool = True) -> CatalogPart:
    """A one-piece clamping shaft collar.

    No published standard sets a collar's outside dimensions - every maker
    has its own - so the proportions here are the commercial ones (outside
    twice the bore, width half the bore, rounded to the half millimetre) and
    they are parameters, not constants. What is standard is the clamp screw:
    it is an ISO 4762 cap screw and the clearance hole is ISO 273.
    """
    outer = round(bore * 2.0 * 2) / 2.0
    width = max(round(bore * 0.5 * 2) / 2.0, 6.0)
    screw = "M3" if bore <= 8 else "M4" if bore <= 15 else "M5" if bore <= 25 else "M6"
    thread = standards.THREADS[screw]
    clearance = standards.clearance_hole(screw)
    head = standards.ISO_4762[screw].head_diameter
    head_height = standards.ISO_4762[screw].head_height

    lines = [
        "import cadquery as cq",
        "",
        "# Clamping shaft collar. Outside proportions are commercial, not",
        "# standard - see the docstring. The clamp screw is ISO 4762 and its",
        "# clearance hole ISO 273.",
        f"bore = {_n(bore)}",
        f"outer_diameter = {_n(outer)}",
        f"width = {_n(width)}",
        "",
        "result = (",
        "    cq.Workplane('XY')",
        "    .circle(outer_diameter / 2.0)",
        "    .circle(bore / 2.0)",
        "    .extrude(width)",
        ")",
    ]
    parameters = {"bore": bore, "outer_diameter": outer, "width": width}

    if clamp:
        slit = round(max(bore * 0.09, 1.0), 2)
        lines += [
            "",
            f"clamp_screw_clearance = {_n(clearance)}   # ISO 273 for {screw}",
            f"clamp_head_diameter = {_n(head)}   # ISO 4762 socket head",
            f"clamp_head_height = {_n(head_height)}",
            f"slit_width = {_n(slit)}",
            "",
            "# The slit runs out through the +X side. Everything inboard of the",
            "# bore is already air, so cutting from the centre costs nothing.",
            "slit = (",
            "    cq.Workplane('XY')",
            "    .box(outer_diameter, slit_width, width * 2.0,",
            "         centered=(False, True, True))",
            "    .translate((0, 0, width / 2.0))",
            ")",
            "result = result.cut(slit)",
            "",
            "# The clamp screw crosses the slit, so it has to sit in the solid",
            "# between the bore and the outside - midway is where it goes.",
            "clamp_radius = (bore + outer_diameter) / 4.0",
            "screw_hole = (",
            "    cq.Workplane('XZ')",
            "    .center(clamp_radius, width / 2.0)",
            "    .circle(clamp_screw_clearance / 2.0)",
            "    .extrude(outer_diameter, both=True)",
            ")",
            "result = result.cut(screw_hole)",
            "",
            "# A counterbore on the -Y ear so the head finishes below the",
            "# outside. It starts at that ear's outer surface and goes inward",
            "# by the head's own height: any deeper and it meets the slit,",
            "# which cuts the ear off the collar entirely.",
            "ear_reach = (outer_diameter ** 2 / 4.0 - clamp_radius ** 2) ** 0.5",
            "counterbore = (",
            "    cq.Workplane('XZ')",
            "    .workplane(offset=ear_reach)",
            "    .center(clamp_radius, width / 2.0)",
            "    .circle(clamp_head_diameter / 2.0 + 0.2)",
            "    .extrude(-clamp_head_height)",
            ")",
            "result = result.cut(counterbore)",
        ]
        parameters.update({"clamp_screw_clearance": clearance,
                           "slit_width": slit})

    return CatalogPart(
        id=f"collar_{_n(bore)}",
        title=f"Shaft collar, {_n(bore)}mm bore"
              + (f", {screw} clamp" if clamp else ""),
        standard=f"commercial proportions; {screw} ISO 4762 clamp screw",
        code="\n".join(lines) + "\n", parameters=parameters)


def rigid_coupling(bore: float = 12.0,
                   second_bore: float | None = None) -> CatalogPart:
    """A one-piece clamping shaft coupling, for joining two shafts end to end.

    Like the collar, the body proportions are commercial rather than
    standard. The two clamps are put at right angles to each other, which is
    how they are made: two slits in the same plane would leave the middle of
    the coupling as a hinge.
    """
    other = second_bore if second_bore else bore
    biggest = max(bore, other)
    outer = round(biggest * 2.0 * 2) / 2.0
    length = round(biggest * 3.0 * 2) / 2.0
    screw = "M3" if biggest <= 8 else "M4" if biggest <= 15 else "M5" if biggest <= 25 else "M6"
    clearance = standards.clearance_hole(screw)
    head = standards.ISO_4762[screw].head_diameter
    head_height = standards.ISO_4762[screw].head_height
    slit = round(max(biggest * 0.09, 1.0), 2)

    code = f"""import cadquery as cq

# Clamping shaft coupling. Body proportions are commercial, not standard;
# the clamp screws are ISO 4762 with ISO 273 clearance holes.
bore_a = {_n(bore)}
bore_b = {_n(other)}
outer_diameter = {_n(outer)}
length = {_n(length)}
slit_width = {_n(slit)}
clamp_screw_clearance = {_n(clearance)}   # ISO 273 for {screw}
clamp_head_diameter = {_n(head)}
clamp_head_height = {_n(head_height)}

# A thin web is left at the middle so the two shafts butt against it rather
# than against each other.
web = 1.5

result = cq.Workplane('XY').circle(outer_diameter / 2.0).extrude(length)
result = (
    result.faces('<Z').workplane(centerOption='CenterOfBoundBox')
    .circle(bore_a / 2.0)
    .cutBlind(-(length - web) / 2.0)
)
result = (
    result.faces('>Z').workplane(centerOption='CenterOfBoundBox')
    .circle(bore_b / 2.0)
    .cutBlind(-(length - web) / 2.0)
)

clamp_radius = (max(bore_a, bore_b) + outer_diameter) / 4.0


def clamp(z, angle):
    \"\"\"One slit and its screw, as a single solid to cut away.\"\"\"
    slit = (
        cq.Workplane('XY')
        .box(outer_diameter, slit_width, length / 3.0,
             centered=(False, True, True))
        .translate((0, 0, z))
    )
    screw = (
        cq.Workplane('XZ')
        .center(clamp_radius, z)
        .circle(clamp_screw_clearance / 2.0)
        .extrude(outer_diameter, both=True)
    )
    ear_reach = (outer_diameter ** 2 / 4.0 - clamp_radius ** 2) ** 0.5
    head_recess = (
        cq.Workplane('XZ')
        .workplane(offset=ear_reach)
        .center(clamp_radius, z)
        .circle(clamp_head_diameter / 2.0 + 0.2)
        .extrude(-clamp_head_height)
    )
    return slit.union(screw).union(head_recess).rotate((0, 0, 0), (0, 0, 1), angle)


# At right angles, so neither end hinges on the other's slit.
result = result.cut(clamp(length * 0.22, 0))
result = result.cut(clamp(length * 0.78, 90))
"""
    return CatalogPart(
        id=f"coupling_{_n(bore)}_{_n(other)}",
        title=(f"Shaft coupling, {_n(bore)}mm to {_n(other)}mm bore"
               if bore != other else f"Shaft coupling, {_n(bore)}mm bore"),
        standard=f"commercial proportions; {screw} ISO 4762 clamp screws",
        code=code,
        parameters={"bore_a": bore, "bore_b": other,
                    "outer_diameter": outer, "length": length,
                    "clamp_screw_clearance": clearance},
    )


def select(text: str) -> CatalogPart | None:
    """The standard part someone asked for, or None if this is a custom part.

    Deliberately strict, unlike the mock provider's forgiving part matcher:
    a wrong guess here silently hands back the wrong hardware, and a custom
    bracket that merely *mentions* an M8 screw must still be generated, not
    substituted. Only an unambiguous designation matches.
    """
    lowered = text.lower()

    # A request naming a standard part inside a bigger noun is asking for the
    # bigger noun: "a bearing housing for a 6203" wants the housing, and the
    # bearing is what goes in it. Handing back the bearing would be silently
    # wrong, so custom context wins over any designation in the text.
    if any(word in lowered for word in _CUSTOM_CONTEXT):
        return None

    if any(word in lowered for word in _BAR_NOUNS):
        if any(word in lowered for word in _BAR_CONTEXT):
            return None
        style = next((name for word, name in _BAR_STYLES if word in lowered),
                     None)
        if style is None:
            # "A handlebar" on its own says nothing about which one, and a
            # bar is five dimensions rather than a size. The pipeline can
            # design one; the catalogue will not guess.
            return None
        overrides: dict[str, float] = {}
        width = _BAR_WIDTH_MM.search(text)
        inches = _BAR_WIDTH_IN.search(text)
        if width:
            overrides["overall_width"] = float(width.group(1))
        elif inches:
            overrides["overall_width"] = round(float(inches.group(1)) * 25.4, 1)
        rise = _BAR_RISE.search(text)
        if rise:
            unit = (rise.group(2) or "mm").lower()
            value = float(rise.group(1))
            overrides["rise"] = round(value * 25.4, 1) if unit != "mm" else value
        for spelling, diameter in _BAR_TUBE.items():
            if spelling in lowered:
                overrides["tube_diameter"] = diameter
                break
        try:
            return handlebar(style, **overrides)
        except KeyError:
            return None

    if "bearing" in lowered:
        found = _BEARING.search(text)
        if found and found.group(1) in standards.BEARINGS:
            return ball_bearing(found.group(1))
        return None

    if "o-ring" in lowered or "o ring" in lowered or "oring" in lowered:
        found = _ORING.search(text)
        if found:
            return o_ring(float(found.group(1)), float(found.group(2)))
        inner, cord = _ORING_ID.search(text), _ORING_CORD.search(text)
        if inner and cord:
            return o_ring(float(inner.group(1)), float(cord.group(1)))
        return None

    if "dowel" in lowered:
        found = _PIN.search(text)
        if found:
            return dowel_pin(float(found.group(1)), float(found.group(2)))
        diameter = _PIN_DIA.search(text) or _PIN_BARE.search(text)
        length = _LENGTH_WORDS.search(text)
        if diameter and length:
            return dowel_pin(float(diameter.group(1)),
                             float(length.group(1)))
        return None

    size_match = _SIZE.search(text)
    if not size_match:
        return None
    try:
        size = standards._normalise(size_match.group(1))
    except KeyError:
        return None

    length_match = _LENGTH.search(text) or _LENGTH_WORDS.search(text)
    length = float(length_match.group(1)) if length_match else None

    if "washer" in lowered:
        return flat_washer(size) if size in standards.ISO_7089 else None
    if "nut" in lowered:
        return hex_nut(size) if size in standards.ISO_4032 else None
    if any(word in lowered for word in
           ("cap screw", "socket head", "shcs", "allen", "hex socket")):
        if size in standards.ISO_4762:
            return socket_head_cap_screw(size, length or size_lengths(size))
        return None
    if "hex" in lowered and ("bolt" in lowered or "screw" in lowered):
        if size in standards.ISO_4014:
            return hex_bolt(size, length or size_lengths(size))
        return None
    if "bolt" in lowered or "screw" in lowered:
        # Unqualified: a cap screw is the common case in machine design.
        if size in standards.ISO_4762:
            return socket_head_cap_screw(size, length or size_lengths(size))
    return None


def size_lengths(size: str) -> float:
    """A sensible default length when someone names a size but no length."""
    diameter = standards.THREADS[standards._normalise(size)].diameter
    return round(diameter * 3.0, 1)


def handlebar(style: str = "road_medium", **overrides) -> CatalogPart:
    """A motorcycle handlebar, bent to a published set of dimensions.

    The table in ``handlebars.py`` holds bars that exist - four production
    road bends, the drawing this study was given, and the shapes the custom
    trade names - and every one of them is the same tube bent to different
    numbers, which is what makes a handlebar worth building parametrically
    rather than one model per style.
    """
    bar = handlebars.BARS[style]
    dimensions = bar.dimensions()
    dimensions.update({name: value for name, value in overrides.items()
                       if value is not None})
    width = dimensions["overall_width"]
    tube = dimensions["tube_diameter"]
    return CatalogPart(
        id=f"handlebar_{style}_w{width:g}_d{tube:g}",
        title=f"{bar.title}, {width:g} mm wide on {tube:g} mm tube",
        standard=f"handlebar - {bar.source}",
        code=handlebars.code_for(**dimensions),
        parameters=dimensions,
        inspect=lambda solid: handlebars.inspect(solid, dimensions))


#: Every family this module builds, by name. ``select`` reads a request and
#: picks one; this is for reaching a builder directly, when the family is
#: already known and only the sizes are in question.
BUILDERS = {
    "socket_head_cap_screw": socket_head_cap_screw,
    "hex_bolt": hex_bolt,
    "hex_nut": hex_nut,
    "flat_washer": flat_washer,
    "ball_bearing": ball_bearing,
    "o_ring": o_ring,
    "dowel_pin": dowel_pin,
    "set_screw": set_screw,
    "threaded_rod": threaded_rod,
    "compression_spring": compression_spring,
    "timing_pulley": timing_pulley,
    "spur_gear": spur_gear,
    "shaft": shaft,
    "parallel_key": parallel_key,
    "plain_bushing": plain_bushing,
    "retaining_ring": retaining_ring,
    "shaft_collar": shaft_collar,
    "rigid_coupling": rigid_coupling,
    "handlebar": handlebar,
}
