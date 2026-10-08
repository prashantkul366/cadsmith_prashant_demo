"""What a part costs, and whether the table you edit is the table it uses.

Two numbers and the reasoning between them: the stock the part is cut
from, priced by weight, and the operations that turn stock into part,
priced by the minute. Nothing here is a quotation. The value of it is that
every figure traces to a line in app/costing/rates.toml, so a number that
looks wrong can be argued with rather than guessed at - and that is the
thing worth testing: that the file really does decide the answer.

Nothing is mocked. Each case builds a solid, projects it the way the app
does, and costs it.

Run:  .venv/bin/python -m app.tests.test_costing
"""

from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cadquery as cq  # noqa: E402

from app.server import costing, drawing, specification  # noqa: E402


def built(solid, into: Path, name: str):
    step = into / f"{name}.step"
    cq.exporters.export(solid, str(step))
    shape = solid.val()
    box = shape.BoundingBox()
    geometry = {"bounding_box": {"xlen": box.xlen, "ylen": box.ylen,
                                 "zlen": box.zlen},
                "volume": shape.Volume(), "is_valid": True}
    return geometry, drawing._project(step)      # noqa: SLF001


def main() -> int:
    failures = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        if not ok:
            failures += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}"
              + (f" - {detail}" if detail else ""))

    rates = costing.load_rates()
    check("the rate table loads", bool(rates.get("materials")),
          f"{len(rates.get('materials') or {})} material(s), "
          f"{len(rates.get('machines') or {})} machine(s)")

    print("\nA material is found by what the Planner called it")
    for named, want in (("aluminium 6061-T6", "aluminium"),
                        ("6082-T6", "aluminium"),
                        ("mild steel S45C", "steel"),
                        # The trap: "stainless steel" contains "steel", and
                        # the two differ by a factor of five in price and a
                        # factor of two in how fast a mill cuts them.
                        ("stainless steel 301", "stainless"),
                        ("SUS304", "stainless"),
                        ("Ti-6Al-4V", "titanium"),
                        ("POM (acetal)", "plastic")):
        got = costing.material_key(named, rates)
        check(f"{named} -> {want}", got == want, got)
    check("and one nobody listed is not quietly assumed",
          costing.material_key("unobtainium", rates) == "unknown")

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        plate = (cq.Workplane("XY").box(280, 200, 10)
                 .faces(">Z").workplane()
                 .pushPoints([(-120, -80), (120, -80), (120, 80), (-120, 80)])
                 .hole(13.0))
        geometry, views = built(plate, work, "plate")

        def price(process: str, table=None, material="aluminium 6061-T6"):
            return costing.estimate(geometry, views, None, table or rates,
                                    material, process).to_dict(table or rates)

        print("\nThe process decides most of the cost")
        milled, sheet = price("milled"), price("sheet")
        check("a billet part is machined from stock bigger than itself",
              milled["stock_mm3"] > milled["part_mm3"]
              and milled["stock_kind"] == "billet",
              f"{milled['removed_mm3'] / 1000:.0f} cm3 removed")
        check("and cutting the same plate from sheet costs less",
              sheet["total"] < milled["total"],
              f"¥{sheet['total']:,.0f} vs ¥{milled['total']:,.0f}")
        # The bug this caught: a laser-cut part was being sent to a mill to
        # have its holes drilled, which is a machine it never visits and a
        # setup it never pays for - and it made sheet dearer than billet.
        machines = {op["machine"] for op in sheet["operations"]}
        check("a laser-cut part never visits a mill", "mill" not in machines,
              ", ".join(sorted(machines)))
        cut = next(op for op in sheet["operations"]
                   if op["machine"] == "laser")
        check("because the laser cuts the holes on the same pass",
              cut["detail"]["code"] == "cost.d.cutholes"
              and cut["detail"]["data"]["holes"] == 4,
              str(cut["detail"]))
        # The sentence is kept as a key and its numbers so the card can be
        # read in either language; the English text rides along as the
        # fallback for a key nobody has translated yet.
        check("and every sentence travels as a key, not as words",
              all(op["detail"] is None
                  or (op["detail"]["code"] and op["detail"]["text"])
                  for op in sheet["operations"] + milled["operations"])
              and all(a["code"] and a["text"]
                      for a in milled["assumptions"]),
              str([op["detail"]["code"] for op in milled["operations"]]))

        print("\nEvery figure comes from the table, so editing it moves them")
        dearer = copy.deepcopy(rates)
        dearer["materials"]["aluminium"]["price"] *= 2.0
        check("doubling the metal price doubles the material cost",
              abs(price("milled", dearer)["material_cost"]
                  - 2 * milled["material_cost"]) < 1.0,
              f"¥{price('milled', dearer)['material_cost']:,.0f}")
        slower = copy.deepcopy(rates)
        slower["materials"]["aluminium"]["removal"] /= 2.0
        check("halving how fast it cuts makes roughing twice as long",
              _minutes(price("milled", slower), "rough out")
              > 1.9 * _minutes(milled, "rough out"),
              f"{_minutes(price('milled', slower), 'rough out'):.2f} min")
        quicker = copy.deepcopy(rates)
        quicker["machines"]["mill"]["rate"] = 0.0
        check("a free machine makes its operations free",
              price("milled", quicker)["machining_cost"]
              < milled["machining_cost"],
              f"¥{price('milled', quicker)['machining_cost']:,.0f}")

        print("\nSetting up is charged once, and shared across the batch")
        ten = copy.deepcopy(rates)
        ten["batch"]["quantity"] = 10
        batched = price("milled", ten)
        check("ten of them each carry a tenth of the setup",
              abs(batched["setup_cost"] * 10 - milled["setup_cost"]) < 1.0,
              f"¥{batched['setup_cost']:,.0f} each vs "
              f"¥{milled['setup_cost']:,.0f}")
        check("which is most of why the tenth is cheaper than the first",
              batched["total"] < milled["total"],
              f"¥{batched['total']:,.0f} vs ¥{milled['total']:,.0f}")

        print("\nWhat it assumed, said out loud")
        def codes(estimate):
            return [a["code"] for a in estimate["assumptions"]]

        unknown = price("milled", material="unobtainium")
        check("a material it does not know is reported, not hidden",
              "cost.a.unknown" in codes(unknown), str(codes(unknown)))
        check("and so is the stock it decided to start from",
              "cost.a.billet" in codes(milled), str(codes(milled)))
        check("and the batch the setup was divided by",
              "cost.a.batch" in codes(milled), str(codes(milled)))

        print("\nA process it cannot price says so rather than guessing")
        for process, want in (("moulded", "cost.a.tooling"),
                              ("forged", "cost.a.unpriced")):
            said = [a["code"] for a in price(process)["assumptions"]]
            check(f"a {process} part is flagged, not quietly machined",
                  want in said, str(said))
        for process in ("milled", "sheet", "turned"):
            said = [a["code"] for a in price(process)["assumptions"]]
            check(f"while {process} is priced without a caveat",
                  not ({"cost.a.tooling", "cost.a.unpriced"} & set(said)),
                  str(said))

        print("\nA fit is reamed, not drilled")
        block = (cq.Workplane("XY").box(60, 40, 30)
                 .faces(">Z").workplane().hole(32.0))
        geometry, views = built(block, work, "block")
        spec = specification.Specification(
            material="stainless steel 304", process="milled",
            fits=[specification.Fit(feature="bearing bore", size_mm=32.0,
                                    fit="H7", grounded=True)])
        with_fit = costing.estimate(geometry, views, spec, rates).to_dict(rates)
        check("an H7 bore adds a reaming operation",
              any(op["name"] == "ream to fit"
                  for op in with_fit["operations"]),
              str([op["name"] for op in with_fit["operations"]]))
        check("and stainless takes longer to rough out than aluminium",
              _minutes(with_fit, "rough out") > 0,
              f"{_minutes(with_fit, 'rough out'):.2f} min")

    print("\n" + "=" * 58)
    print("ALL CHECKS PASSED" if not failures else f"{failures} CHECK(S) FAILED")
    return 1 if failures else 0


def _minutes(estimate: dict, name: str) -> float:
    for op in estimate["operations"]:
        if op["name"] == name:
            return float(op["minutes"])
    return 0.0


if __name__ == "__main__":
    sys.exit(main())
