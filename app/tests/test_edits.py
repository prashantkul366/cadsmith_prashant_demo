"""Check that natural-language edits map to the right parameter, or refuse.

The point of these cases is the refusals as much as the successes: a
mis-mapped edit silently changes the wrong dimension, so anything ambiguous
must fall through to the Refiner agent instead of guessing.

Run:  .venv/bin/python -m app.tests.test_edits
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.server.edits import (Change, apply_changes, describe,
                             describe_parameters, parameters, plan_edit)

CODE = """import cadquery as cq

base_length = 100.0
base_width = 60.0
base_thickness = 10.0
support_height = 45.0
support_thickness = 8.0
hole_diameter = 8.0
hole_count = 4

result = cq.Workplane('XY').box(base_length, base_width, base_thickness)
for i in range(hole_count):
    spacing = 12.0
    result = result.faces('>Z').workplane().hole(hole_diameter)
"""


def main() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
        if not ok:
            failures.append(label)

    print("\nParameter extraction")
    found = parameters(CODE)
    check("top-level parameters found", len(found) == 7, str(sorted(found)))
    check("indented locals are ignored", "spacing" not in found)
    check("integers recognised as integers", found["hole_count"].is_integer)
    check("floats recognised as floats", not found["base_length"].is_integer)

    print("\nEdits that should map")
    cases = [
        ("make the base 15mm thick", "base_thickness", 15.0),
        ("set support height to 60", "support_height", 60.0),
        ("change the hole diameter to 6.5mm", "hole_diameter", 6.5),
        ("base length should be 120mm", "base_length", 120.0),
        ("increase support height by 10", "support_height", 55.0),
        ("add two more holes", "hole_count", 6.0),
    ]
    for instruction, expected_name, expected_value in cases:
        plan = plan_edit(CODE, instruction)
        ok = (plan.possible and plan.changes[0].name == expected_name
              and abs(plan.changes[0].new - expected_value) < 1e-9)
        check(f'"{instruction}"', ok,
              describe(plan.changes) if plan.possible else f"refused: {plan.reason}")

    print("\nEdits that must fall through to the agent")
    refusals = [
        ("add a reinforcing gusset between the walls", "shape"),
        ("make it stronger", "value"),
        ("round the outer edges", "shape"),
        ("set the flange diameter to 90mm", "no flange"),
        ("make the base thickness 0", "would set"),
        ("set base thickness to 10", "already"),
    ]
    for instruction, expected_reason in refusals:
        plan = plan_edit(CODE, instruction)
        check(f'"{instruction}"', not plan.possible and expected_reason in plan.reason,
              plan.reason or f"WRONGLY APPLIED: {describe(plan.changes)}")

    print("\nAmbiguity is refused, not guessed")
    ambiguous = plan_edit(CODE, "make the thickness 12mm")
    check('"make the thickness 12mm" is ambiguous',
          not ambiguous.possible and "ambiguous" in ambiguous.reason,
          ambiguous.reason or describe(ambiguous.changes))

    print("\nApplying a change")
    plan = plan_edit(CODE, "make the base 15mm thick")
    updated = apply_changes(CODE, plan.changes)
    check("assignment rewritten", "base_thickness = 15.0" in updated)
    check("other parameters untouched", "base_length = 100.0" in updated
          and "hole_count = 4" in updated)
    check("line count unchanged",
          len(updated.splitlines()) == len(CODE.splitlines()))
    check("still valid Python", _compiles(updated))

    integer_plan = plan_edit(CODE, "add two more holes")
    integer_code = apply_changes(CODE, integer_plan.changes)
    check("integer parameters stay integers", "hole_count = 6" in integer_code,
          next(l for l in integer_code.splitlines() if "hole_count =" in l))

    comment_code = "thickness = 4.0  # mm, per the drawing\n"
    commented = apply_changes(comment_code, plan_edit(comment_code,
                              "make the thickness 9mm").changes)
    check("trailing comment preserved",
          commented.strip() == "thickness = 9.0  # mm, per the drawing",
          commented.strip())

    print("\nDescribed well enough to put a control on")
    described = {d["name"]: d for d in describe_parameters(CODE)}
    check("every patchable parameter is described",
          set(described) == set(parameters(CODE)),
          ", ".join(sorted(described)))
    check("a count is a count, and a whole number",
          described["hole_count"]["kind"] == "count"
          and described["hole_count"]["integer"]
          and described["hole_count"]["step"] == 1,
          str(described["hole_count"]))
    check("a length is measured in mm",
          described["base_thickness"]["kind"] == "length"
          and described["base_thickness"]["unit"] == "mm",
          str(described["base_thickness"]))
    check("the slider brackets the value it opens on",
          all(d["min"] <= d["value"] <= d["max"] for d in described.values()),
          ", ".join(f"{d['name']}={d['value']:g} in [{d['min']:g},{d['max']:g}]"
                    for d in described.values()
                    if not d["min"] <= d["value"] <= d["max"]) or "all inside")
    check("the slider never offers a value the patcher would refuse",
          all(d["min"] > 0 for d in described.values()),
          ", ".join(f"{d['name']} min={d['min']:g}" for d in described.values()
                    if d["min"] <= 0) or "all positive")
    check("the label is the script's own name, made readable",
          described["hole_diameter"]["label"] == "Hole diameter",
          described["hole_diameter"]["label"])

    angled = {d["name"]: d for d in describe_parameters(
        "taper_angle = 12.0\npressure_angle = 20.0\n")}
    check("an angle is measured in degrees, near where it sits",
          all(d["kind"] == "angle" and d["unit"] == "\u00b0"
              and d["max"] <= 180 for d in angled.values()),
          ", ".join(f"{d['name']} {d['min']:g}-{d['max']:g}{d['unit']}"
                    for d in angled.values()))

    # The whole point of one parser: a control that appears must be one the
    # patcher can actually move.
    moved = apply_changes(CODE, [
        Change(name=d["name"], old=d["value"], new=d["max"])
        for d in described.values()])
    check("every described control is one apply_changes can move",
          all(f"{d['name']} =" in moved for d in described.values())
          and parameters(moved) and all(
              abs(parameters(moved)[n].value - d["max"]) < 1e-9
              for n, d in described.items()),
          ", ".join(f"{n}={parameters(moved)[n].value:g}"
                    for n in sorted(described))[:80])
    check("and the moved script is still valid Python", _compiles(moved))

    print(f"\n{'=' * 58}")
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED: {', '.join(failures)}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


def _compiles(code: str) -> bool:
    try:
        compile(code, "<edited>", "exec")
        return True
    except SyntaxError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
