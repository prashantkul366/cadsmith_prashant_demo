"""What a part costs to make: the stock it starts from, and the work on it.

Two numbers and the reasoning between them. The stock is the billet or the
sheet the part is cut out of, priced by weight. The work is the operations
that turn one into the other, priced by the minute. Nothing here is a
quotation - it is an estimate for comparing one design against another,
and the output says so.

The operations are read off the geometry rather than asked for, because
the geometry is what is true: a hole is a hole whatever the plan called
it, and a pocket's volume is the volume the mill has to remove. What the
Planner contributes is the material and the process, which are the two
things geometry cannot tell you - a 100 x 60 plate is laser-cut sheet or a
milled billet depending on nothing in the model.

Every rate, feed and allowance comes from app/costing/rates.toml, which is
meant to be edited. A number that was guessed in this module instead would
be a number nobody could correct.
"""

from __future__ import annotations

import math
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

RATES_PATH = Path(__file__).resolve().parents[1] / "costing" / "rates.toml"

#: Processes that start from sheet rather than from a billet. A sheet part
#: is cut to shape, so there is no envelope of metal to machine away, and
#: costing one as a billet overstates it by an order of magnitude.
SHEET_PROCESSES = ("sheet", "fabricated")

#: Processes done on a lathe, where the stock is a bar and the envelope is
#: a cylinder rather than a box.
TURNED_PROCESSES = ("turned",)

#: Processes this model does not know how to cost. A moulding or a casting
#: is paid for mostly in tooling, amortised over a run of thousands, and a
#: printed part is paid for in machine hours against build volume - none of
#: which is time at a spindle. Costing one as a milled billet is not a
#: rough answer, it is the wrong question answered precisely, so the
#: estimate says which it did rather than letting the number stand alone.
UNPRICED_PROCESSES = ("cast", "moulded", "printed", "extruded")


@dataclass
class Said:
    """A sentence, kept as what it says rather than as the words.

    The card is read in Japanese as readily as in English, and a sentence
    built here would be built in one of them. So the key and its numbers
    travel and the browser writes it, with the English text riding along
    as the fallback for a key nobody has translated yet - the same shape
    the validation checks and the drawing notes already use.
    """
    code: str
    data: dict = field(default_factory=dict)
    text: str = ""

    def to_dict(self) -> dict:
        return {"code": self.code, "data": self.data, "text": self.text}


@dataclass
class Operation:
    """One thing a shop does to the part, and what it costs."""
    name: str
    machine: str
    minutes: float
    detail: Optional["Said"] = None

    def cost(self, rates: dict) -> float:
        hourly = _machine(rates, self.machine)["rate"]
        return self.minutes / 60.0 * hourly

    def to_dict(self, rates: dict) -> dict:
        return {"name": self.name, "machine": self.machine,
                "minutes": round(self.minutes, 2),
                "detail": self.detail.to_dict() if self.detail else None,
                "cost": round(self.cost(rates), 1)}


@dataclass
class Estimate:
    """The whole answer, with every step of it kept."""
    material: str = ""
    material_key: str = ""
    process: str = ""
    stock_kind: str = ""
    stock_mm3: float = 0.0
    part_mm3: float = 0.0
    stock_kg: float = 0.0
    material_cost: float = 0.0
    operations: list[Operation] = field(default_factory=list)
    machining_cost: float = 0.0
    setup_minutes: float = 0.0
    setup_cost: float = 0.0
    quantity: int = 1
    assumptions: list = field(default_factory=list)

    @property
    def total(self) -> float:
        return self.material_cost + self.machining_cost + self.setup_cost

    def to_dict(self, rates: dict) -> dict:
        return {
            "currency": rates.get("meta", {}).get("currency", "JPY"),
            "revised": rates.get("meta", {}).get("revised", ""),
            "material": self.material,
            "material_key": self.material_key,
            "process": self.process,
            "stock_kind": self.stock_kind,
            "stock_mm3": round(self.stock_mm3, 1),
            "part_mm3": round(self.part_mm3, 1),
            "removed_mm3": round(max(0.0, self.stock_mm3 - self.part_mm3), 1),
            "stock_kg": round(self.stock_kg, 4),
            "material_cost": round(self.material_cost, 1),
            "operations": [op.to_dict(rates) for op in self.operations],
            "machining_cost": round(self.machining_cost, 1),
            "setup_minutes": round(self.setup_minutes, 1),
            "setup_cost": round(self.setup_cost, 1),
            "quantity": self.quantity,
            "total": round(self.total, 1),
            "assumptions": [a.to_dict() if isinstance(a, Said)
                            else {"code": "", "data": {}, "text": str(a)}
                            for a in self.assumptions],
        }


def load_rates(path: Optional[Path] = None) -> dict:
    """The rate table, or the compiled-in minimum if it cannot be read.

    Never raises. A rate file somebody is halfway through editing must not
    take the app down - it costs the estimate, not the run.
    """
    try:
        with open(path or RATES_PATH, "rb") as handle:
            return tomllib.load(handle)
    except Exception:
        return {}


def _machine(rates: dict, name: str) -> dict:
    machines = rates.get("machines") or {}
    found = machines.get(name) or machines.get("mill") or {}
    return {"rate": float(found.get("rate", 7500.0)),
            "setup": float(found.get("setup", 30.0))}


def _times(rates: dict) -> dict:
    return rates.get("times") or {}


def _time(rates: dict, key: str, fallback: float) -> float:
    try:
        return float(_times(rates).get(key, fallback))
    except (TypeError, ValueError):
        return fallback


def material_key(name: str, rates: dict) -> str:
    """Which row of the table this material is, by name or by alias.

    Longest alias first, so `stainless steel 301` is stainless rather than
    steel. A grade nobody listed answers `unknown`, and the estimate says
    as much rather than pretending to a figure.
    """
    text = (name or "").strip().lower()
    table = rates.get("materials") or {}
    if not text:
        return "unknown"
    candidates: list[tuple[int, str]] = []
    for key, row in table.items():
        if key == "unknown":
            continue
        for alias in [key] + list(row.get("aliases") or []):
            if alias and alias.lower() in text:
                candidates.append((len(alias), key))
    if not candidates:
        return "unknown"
    return max(candidates)[1]


def _material(rates: dict, key: str) -> dict:
    row = (rates.get("materials") or {}).get(key) or {}
    return {"density": float(row.get("density", 7850.0)),
            "price": float(row.get("price", 500.0)),
            "removal": float(row.get("removal", 25.0))}


def _holes(circles) -> list[dict]:
    """Distinct holes in a view, as diameter and count.

    The projector hands a hole over as one or two arcs, so they are grouped
    by centre first and then by size.
    """
    seen: dict[tuple, float] = {}
    for circle in circles or []:
        key = (round(circle.get("u", 0.0), 2), round(circle.get("v", 0.0), 2))
        radius = float(circle.get("r", 0.0))
        # A counterbore is two circles at one centre; the drill goes
        # through at the smaller.
        if key not in seen or radius < seen[key]:
            seen[key] = radius
    sizes: dict[float, int] = {}
    for radius in seen.values():
        if radius <= 0:
            continue
        diameter = round(radius * 2.0, 2)
        sizes[diameter] = sizes.get(diameter, 0) + 1
    return [{"diameter": d, "count": n} for d, n in sorted(sizes.items())]


def _perimeter(lines) -> float:
    """How far a laser travels around this view, in millimetres."""
    total = 0.0
    for line in lines or []:
        for (ax, ay), (bx, by) in zip(line, line[1:]):
            total += math.hypot(bx - ax, by - ay)
    return total


def operations(geometry: dict, views: dict, spec: Any, rates: dict,
               material: str, process: str) -> tuple[list[Operation], dict]:
    """What has to be done to the stock, and what the stock is.

    Read off the solid and its projection. The process decides the shape of
    the answer: sheet is cut to outline and has no envelope to clear, a
    turned part starts from bar, and everything else starts from a billet
    that has to be faced and then carved.
    """
    key = material_key(material, rates)
    metal = _material(rates, key)
    box = geometry.get("bounding_box") or {}
    xlen = float(box.get("xlen", 0.0))
    ylen = float(box.get("ylen", 0.0))
    zlen = float(box.get("zlen", 0.0))
    part_mm3 = float(geometry.get("volume") or 0.0)
    stock_cfg = rates.get("stock") or {}
    allowance = float(stock_cfg.get("allowance_mm", 3.0))

    ops: list[Operation] = []
    notes: list[str] = []
    top = (views or {}).get("TOP") or {}
    front = (views or {}).get("FRONT") or {}
    holes = _holes(top.get("circles")) or _holes(front.get("circles"))

    if process in SHEET_PROCESSES:
        # A sheet part is cut from stock the size of its own outline plus
        # what nesting wastes. There is no envelope of metal to remove, so
        # costing it as a billet is the single biggest way to be wrong.
        waste = float(stock_cfg.get("sheet_waste", 0.25))
        thickness = min(xlen, ylen, zlen) or zlen
        footprint = (xlen * ylen * zlen) / thickness if thickness else 0.0
        stock_mm3 = footprint * thickness * (1.0 + waste)
        stock_kind = "sheet"
        notes.append(Said(
            "cost.a.sheet", {"mm": f"{thickness:g}",
                             "pct": f"{waste * 100:.0f}"},
            f"sheet {thickness:g} mm thick, nested with "
            f"{waste * 100:.0f}% waste"))
        # The laser cuts the holes on the same pass it cuts the outline.
        # Sending a laser-cut part to a mill to be drilled is both a
        # machine it never visits and a setup it never pays for, and it
        # made a sheet part cost more than the billet it is cheaper than.
        metres = _perimeter(top.get("visible")) / 1000.0
        bored = sum(h["count"] * math.pi * h["diameter"] for h in holes) / 1000.0
        if metres + bored > 0:
            ops.append(Operation(
                "profile cut", "laser",
                (metres + bored) * _time(rates, "laser_per_m", 1.5),
                Said("cost.d.cutholes" if bored else "cost.d.cut",
                     {"mm": f"{metres * 1000:.0f}",
                      "holes": sum(h["count"] for h in holes),
                      "around": f"{bored * 1000:.0f}"},
                     f"{metres * 1000:.0f} mm of outline"
                     + (f" and {bored * 1000:.0f} mm around "
                        f"{sum(h['count'] for h in holes)} hole(s)"
                        if bored else ""))))
        holes = []          # cut, not drilled
        edge_m = metres + bored
    else:
        if process in TURNED_PROCESSES:
            # Bar stock: a cylinder that encloses the part.
            diameter = max(xlen, ylen) + allowance
            length = zlen + allowance
            stock_mm3 = math.pi * (diameter / 2.0) ** 2 * length
            stock_kind = "bar"
            notes.append(Said(
                "cost.a.bar", {"dia": f"{diameter:g}", "len": f"{length:g}",
                               "mm": f"{allowance:g}"},
                f"bar ø{diameter:g} x {length:g} mm, "
                f"{allowance:g} mm allowance"))
            machine = "lathe"
        else:
            stock_mm3 = ((xlen + allowance) * (ylen + allowance)
                         * (zlen + allowance))
            stock_kind = "billet"
            notes.append(Said(
                "cost.a.billet",
                {"size": f"{xlen + allowance:g} x {ylen + allowance:g} x "
                         f"{zlen + allowance:g}", "mm": f"{allowance:g}"},
                f"billet {xlen + allowance:g} x {ylen + allowance:g} x "
                f"{zlen + allowance:g} mm, {allowance:g} mm allowance on "
                f"each face"))
            machine = "mill"
            face_area = (xlen + allowance) * (ylen + allowance)
            ops.append(Operation(
                "face the stock", machine,
                2 * face_area / 10000.0 * _time(rates, "facing_per_area", 1.2),
                Said("cost.d.faces", {"cm2": f"{face_area / 100:.0f}"},
                     f"two faces, {face_area / 100:.0f} cm2 each")))

        removed = max(0.0, stock_mm3 - part_mm3) / 1000.0      # cm3
        if removed > 0:
            ops.append(Operation(
                "rough out", machine, removed / max(metal["removal"], 0.1),
                Said("cost.d.rough",
                     {"cm3": f"{removed:.1f}",
                      "rate": f"{metal['removal']:g}"},
                     f"{removed:.1f} cm3 at {metal['removal']:g} cm3/min")))
            # The walls that leaves have to be finished, and a finishing
            # pass is slower than roughing by the area it covers rather
            # than the metal it takes.
            walls = 2 * (xlen * zlen + ylen * zlen) / 10000.0
            ops.append(Operation(
                "finish", machine,
                walls * _time(rates, "finish_per_area", 2.5),
                Said("cost.d.wall", {"cm2": f"{walls * 100:.0f}"},
                     f"{walls * 100:.0f} cm2 of wall")))
        edge_m = 2 * (xlen + ylen) / 1000.0

    # Holes are drilled whatever the part is made of or cut from.
    steel_removal = _material(rates, "steel")["removal"]
    speed = _time(rates, "drill_feed", 120.0) * (
        metal["removal"] / steel_removal if steel_removal else 1.0)
    depth = zlen or 1.0
    for hole in holes:
        minutes = hole["count"] * (
            depth / max(speed, 1.0) + _time(rates, "drill_overhead", 0.25))
        ops.append(Operation(
            "drill", "mill", minutes,
            Said("cost.d.drill",
                 {"n": hole["count"], "dia": f"{hole['diameter']:g}",
                  "depth": f"{depth:g}"},
                 f"{hole['count']}x ø{hole['diameter']:g} through "
                 f"{depth:g} mm")))

    # A fit is a reamed hole, and a thread is a tapped one. Both are read
    # from the specification rather than guessed at from a diameter.
    fits = list(getattr(spec, "fits", None) or [])
    if fits:
        ops.append(Operation(
            "ream to fit", "mill",
            len(fits) * _time(rates, "ream_extra", 0.8),
            Said("cost.d.ream",
                 {"fits": ", ".join(f.fit for f in fits[:4])},
                 ", ".join(f.fit for f in fits[:4]))))
        notes.append(Said(
            "cost.a.fits", {"n": len(fits)},
            f"{len(fits)} fit(s) reamed rather than drilled"))

    if edge_m > 0:
        ops.append(Operation(
            "deburr", "bench", edge_m * _time(rates, "deburr_per_m", 2.0),
            Said("cost.d.edge", {"mm": f"{edge_m * 1000:.0f}"},
                 f"{edge_m * 1000:.0f} mm of edge")))

    return ops, {"stock_mm3": stock_mm3, "stock_kind": stock_kind,
                 "material_key": key, "notes": notes, "part_mm3": part_mm3}


def estimate(geometry: dict, views: dict, spec: Any = None,
             rates: Optional[dict] = None,
             material: str = "", process: str = "") -> Estimate:
    """The cost of one part, with everything it was worked out from."""
    rates = rates if rates is not None else load_rates()
    material = material or getattr(spec, "material", "") or ""
    process = (process or getattr(spec, "process", "") or "").strip().lower()

    ops, stock = operations(geometry, views, spec, rates, material, process)
    metal = _material(rates, stock["material_key"])
    stock_cfg = rates.get("stock") or {}
    recovery = float(stock_cfg.get("scrap_recovery", 0.0))

    out = Estimate(material=material or "not stated",
                   material_key=stock["material_key"],
                   process=process or "not stated",
                   stock_kind=stock["stock_kind"],
                   stock_mm3=stock["stock_mm3"],
                   part_mm3=stock["part_mm3"],
                   operations=ops,
                   assumptions=list(stock["notes"]))

    out.stock_kg = stock["stock_mm3"] / 1e9 * metal["density"]
    out.material_cost = out.stock_kg * metal["price"]
    if recovery:
        scrap_kg = max(0.0, stock["stock_mm3"] - stock["part_mm3"]) / 1e9 \
            * metal["density"]
        out.material_cost -= scrap_kg * metal["price"] * recovery
        out.assumptions.append(Said(
            "cost.a.scrap", {"pct": f"{recovery * 100:.0f}"},
            f"{recovery * 100:.0f}% of the swarf recovered against the "
            f"stock"))

    out.machining_cost = sum(op.cost(rates) for op in ops)

    # Setting up is charged once for each machine the part visits, and
    # divided by how many are being made - which is most of why the second
    # part costs so much less than the first.
    quantity = max(1, int((rates.get("batch") or {}).get("quantity", 1)))
    out.quantity = quantity
    for name in sorted({op.machine for op in ops}):
        out.setup_minutes += _machine(rates, name)["setup"]
    out.setup_cost = sum(
        _machine(rates, name)["setup"] / 60.0 * _machine(rates, name)["rate"]
        for name in {op.machine for op in ops}) / quantity
    out.setup_minutes /= quantity

    if stock["material_key"] == "unknown":
        out.assumptions.append(Said(
            "cost.a.unknown", {"what": material or "the material"},
            f"{material or 'the material'} is not in the rate table, so a "
            f"generic steel price was used - add it to rates.toml"))
    if not process:
        out.assumptions.append(Said(
            "cost.a.noprocess", {},
            "no process was proposed, so the part was costed as a milled "
            "billet"))
    elif process in UNPRICED_PROCESSES:
        out.assumptions.append(Said(
            "cost.a.tooling", {"process": process},
            f"a {process} part is paid for mostly in tooling, which this "
            f"model does not carry - what follows is what it would cost "
            f"machined from solid, which is an upper bound and not a "
            f"{process} price"))
    elif process not in SHEET_PROCESSES + TURNED_PROCESSES \
            and process not in ("milled", "machined"):
        out.assumptions.append(Said(
            "cost.a.unpriced", {"process": process},
            f"'{process}' is not a process this model prices, so the part "
            f"was costed as a milled billet"))
    out.assumptions.append(Said(
        "cost.a.batch", {"n": quantity},
        f"setup divided across a batch of {quantity}"))
    return out
