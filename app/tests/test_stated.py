"""What a request states outright, read before any model sees it.

This is the only check in the app that holds a part to a number the person
wrote rather than to a number an agent produced, so what it can and cannot
read decides whether the gate is measuring anything at all.

It could not read the library it was built for. A mechanical request writes
its millimetres the way a drawing does - "300 x 300 x 25 plate", "Dia 25 H7
locating bore", "508 tall" - and every pattern here demanded the unit be
spelled out. Across the 61-prompt Yamaha library that came to one request
read and sixty not: no extents, no bores, no hole diameters, nothing for the
gate to hold anything to but the Planner's own claims, which is the
self-grading this layer exists to catch.

Reading a number with no unit is not free, though, and the cases that cost a
correct part are all here: the gate blocks on a shortfall, so a number read
wrongly fails a part that was right.

Run:  .venv/bin/python -m app.tests.test_stated
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.server import builder, stated  # noqa: E402


def hard(prompt: str) -> set:
    """The numbers this request states that may block a run."""
    return {(s.role, s.value) for s in stated.read(prompt) if s.is_hard}


def soft(prompt: str) -> set:
    return {(s.role, s.value) for s in stated.read(prompt) if not s.is_hard}


# What must be read, written the way the library writes it.
READS = [
    ("300 x 300 x 25 plate, eight Dia 11 counterbored on a 100 radius",
     {("extent", 300.0), ("extent", 25.0)}),
    ("600 x 300 x 25 base, 508 tall vertical plate, two 20 thick gussets",
     {("extent", 600.0), ("extent", 300.0), ("extent", 25.0)}),
    ("123.3 x 100.8 x 10 plate, 5 x 4 grid of Dia 21.3 pockets",
     {("extent", 123.3), ("extent", 100.8), ("extent", 10.0)}),
    ("Dia 267 disc 5 thick, Dia 58 bore", {("bore", 58.0)}),
    ("OD 62 disk 8 thick, Dia 26 bore, rear conical seat", {("bore", 26.0)}),
    ("Barrel OD 12.5 25 long with a Dia 8.6 bore", {("bore", 8.6)}),
    # Units, where they are written, still read as they always did.
    ("a 100mm by 60mm by 8mm plate",
     {("extent", 100.0), ("extent", 60.0), ("extent", 8.0)}),
    ("a 2cm by 3cm by 4cm block",
     {("extent", 20.0), ("extent", 30.0), ("extent", 40.0)}),
]

# What must not be read, because reading it fails a part that is right.
REFUSES = [
    # A thread is not a size. "M8x1.25 x 30" is three numbers and none of
    # them is 8 mm across.
    ("hex flange bolt, M8x1.25 x 30, hex 13 across flats", "extent", 8.0),
    ("M20x1.5 internal thread, 40 long", "extent", 20.0),
    # A fit class is not a dimension: the 7 in "H7".
    ("flanges Dia 44, Dia 25 hub, Dia 10 H7 bore", "bore", 7.0),
    ("Dia 32 H7 bearing bore, two Dia 6.6 counterbored", "bore", 7.0),
    # A ratio is not a dimension: the 1 in "1:10".
    ("Dia 70 cylinder 45 tall, tapered bore 1:10, keyway", "bore", 1.0),
    # "42 ID" in "OD 42 ID 31.8" is the outside, labelled before the number.
    ("Ring OD 42 ID 31.8, pad block with two M3x0.5 holes", "bore", 42.0),
    # A pitch is not the part's size, with or without a unit.
    ("a plate with four holes in a 70 x 50 x 20 pattern", "extent", 70.0),
    # Nor is a chamfer callout.
    ("25 mm cube, 0.5 x 45 deg chamfer on all 12 edges", "extent", 45.0),
    # Two terms are not a size: they are as likely a thread or a gear.
    ("a 20 tooth x 2 module spur gear", "extent", 20.0),
]

# Counted holes carry their diameter when the request names it in front of
# the number. Reading only the count left the gate with a tally and nothing
# to check the holes against, which is how a part comes back with the right
# number of wrong holes.
HOLES = [
    ("280 x 200 x 10 plate, R12 corners, four Dia 13 holes", 4, [13.0] * 4),
    ("eight Dia 12 H7 holes and a Dia 8 H7 locating hole", 8, [12.0] * 8),
    ("six Dia 10.5 holes on a 62.5 radius", 6, [10.5] * 6),
    # With a unit, exactly as before.
    ("four 6mm holes", 4, [6.0] * 4),
]


def main() -> int:
    failures = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        if not ok:
            failures += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}"
              + (f" - {detail}" if detail else ""))

    print("Dimensions written without units")
    for prompt, want in READS:
        got = hard(prompt)
        check(prompt[:52], want <= got,
              ", ".join(f"{r} {v:g}" for r, v in sorted(got)) or "nothing")

    print("\nNumbers that are not dimensions")
    for prompt, role, value in REFUSES:
        got = hard(prompt) | soft(prompt)
        check(f"{prompt[:46]} -/-> {role} {value:g}", (role, value) not in got,
              ", ".join(f"{r} {v:g}" for r, v in sorted(got)) or "nothing")

    print("\nHoles keep their diameter")
    for prompt, count, diameters in HOLES:
        n, d = stated.holes(prompt)
        ok = n == count and sorted(d) == sorted(diameters)
        check(prompt[:52], ok, f"{n} hole(s), {sorted(set(d))}")

    print("\nA request that says its own size needs no Planner")
    for prompt, _ in READS:
        check(prompt[:52], builder.readable(prompt))
    check("but a request that says nothing still does",
          not builder.readable("a bracket that holds a motor"))

    print("\n" + "=" * 58)
    print("ALL CHECKS PASSED" if not failures else f"{failures} CHECK(S) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
