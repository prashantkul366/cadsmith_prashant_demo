"""The NX operations, and what they refuse.

There is no NX here, so what is checked is the half that does not need
one: that an operation the model asks for is turned into something
well-formed, and that a wrong one is refused with a sentence the model
can act on rather than being passed to somebody's part.

The refusals matter more than the acceptances. An operation that reaches
NX and fails has already cost the engineer their attention; one that is
refused here costs a turn.

Run:  .venv/bin/python -m app.tests.test_nxtools
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.server import nxtools  # noqa: E402

#: A part as the plugin would report one: an extrude and two holes, with
#: NX's own expression names and descriptions.
PART = {
    "part": "bracket",
    "units": "mm",
    "features": [
        {"name": "Extrude(1)", "kind": "Extrude", "timestamp": 1,
         "expressions": [
             {"name": "p1", "value": 25.0,
              "description": "p1 (Extrude(1) Limit End)"}]},
        {"name": "Simple Hole(12)", "kind": "Hole", "timestamp": 2,
         "expressions": [
             {"name": "p7", "value": 13.0,
              "description": "p7 (Simple Hole(12) Diameter)"}]},
        {"name": "Edge Blend(14)", "kind": "Blend", "timestamp": 3,
         "suppressed": True,
         "expressions": [
             {"name": "p9", "value": 5.0,
              "description": "p9 (Edge Blend(14) Radius)",
              "formula": "wall/2"}]},
    ],
    "expressions": [
        {"name": "p1", "value": 25.0, "description": "p1 (Extrude(1) Limit End)"},
        {"name": "p7", "value": 13.0,
         "description": "p7 (Simple Hole(12) Diameter)"},
        {"name": "p9", "value": 5.0, "description": "p9 (Edge Blend(14) Radius)",
         "formula": "wall/2"},
        {"name": "wall", "value": 10.0, "description": "wall"},
    ],
}


def main() -> int:
    failures = 0

    def check(what: str, ok: bool, saw: str = "") -> None:
        nonlocal failures
        if not ok:
            failures += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {what}"
              + (f" - {saw}" if saw else ""))

    def refused(name: str, arguments: dict, tree=None) -> str:
        try:
            nxtools.checked(name, arguments, tree)
        except nxtools.NXToolError as error:
            return str(error)
        return ""

    tree = nxtools.tree_from(PART)

    print("The part, as the model is told about it")
    check("every feature is listed in the order NX built them",
          [f.name for f in sorted(tree.features, key=lambda f: f.timestamp)]
          == ["Extrude(1)", "Simple Hole(12)", "Edge Blend(14)"],
          ", ".join(f.name for f in tree.features))
    summary = tree.summary()
    check("the summary carries the numbers that drive each feature",
          "p7=13" in summary and "p1=25" in summary, summary.splitlines()[1:3])
    check("and says which feature is suppressed",
          "SUPPRESSED" in summary,
          [l for l in summary.splitlines() if "SUPPRESS" in l])
    # NX names expressions p1, p7, p9. Without the description a model
    # has no way to know which one is a hole diameter.
    check("an expression says which feature and parameter it drives",
          tree.expression("p7").means() == "Simple Hole(12) Diameter",
          tree.expression("p7").means())

    print("\nChanging a part somebody else designed")
    one = nxtools.checked("edit_expression",
                          {"name": "p7", "value": 11.0}, tree)
    check("a hole is opened by setting the expression that drives it",
          one.arguments == {"name": "p7", "value": 11.0}, str(one.arguments))
    # The one that matters: a value written over a formula silently
    # breaks the relation the designer put there.
    why = refused("edit_expression", {"name": "p9", "value": 3.0}, tree)
    check("an expression driven by a formula is not overwritten",
          "formula" in why, why[:80])
    check("and the refusal says what the formula was",
          "wall/2" in why, why[:80])
    missing = refused("edit_expression", {"name": "p42", "value": 1.0}, tree)
    check("a name the part does not have is refused with the names it has",
          "p7" in missing and "Simple Hole(12) Diameter" in missing,
          missing[:90])

    print("\nWhat must not reach NX")
    check("an operation that does not exist",
          "no operation called" in refused("melt", {}, tree), "")
    check("a hole with no diameter",
          "diameter is required" in refused("hole", {"depth": 10}, tree), "")
    check("a hole of no size",
          "greater than zero" in refused(
              "hole", {"diameter": 0, "depth": 10}, tree), "")
    # A counterbore narrower than its hole is a drawing nobody can make.
    narrow = refused("hole", {"kind": "counterbored", "diameter": 11,
                              "counterbore_diameter": 9,
                              "counterbore_depth": 5, "depth": 20}, tree)
    check("a counterbore no wider than its own hole",
          "wider" in narrow, narrow[:80])
    check("a threaded hole with no thread named",
          "needs thread" in refused(
              "hole", {"kind": "threaded", "diameter": 6.8, "depth": 20},
              tree), "")
    check("a countersink at an angle no drill has",
          "included angle" in refused(
              "hole", {"kind": "countersunk", "diameter": 6, "depth": 10,
                       "countersink_diameter": 12,
                       "countersink_angle": 15}, tree), "")
    check("an outline that is not an outline",
          "three" in refused("sketch_extrude",
                             {"points": [[0, 0], [10, 0]], "distance": 5},
                             tree), "")
    check("an outline that repeats a corner",
          "crosses itself" in refused(
              "sketch_extrude",
              {"points": [[0, 0], [10, 0], [0, 0], [10, 10]], "distance": 5},
              tree), "")
    check("a plane NX does not have",
          "one of" in refused(
              "sketch_extrude",
              {"points": [[0, 0], [10, 0], [10, 10]], "distance": 5,
               "plane": "AB"}, tree), "")
    check("a feature the part does not have",
          "no feature called" in refused(
              "suppress_feature", {"name": "Draft(9)"}, tree), "")

    print("\nWhat is allowed through")
    pad = nxtools.checked("sketch_extrude",
                          {"points": [[0, 0], [60, 0], [60, 40], [0, 40]],
                           "distance": 12, "plane": "XY",
                           "intent": "the base plate"}, tree)
    check("an outline and a depth become an extrude",
          pad.arguments["distance"] == 12.0
          and len(pad.arguments["points"]) == 4, str(pad.arguments)[:70])
    check("and the reason it was asked for is carried with it",
          pad.intent == "the base plate", pad.intent)
    # Through-all needs no depth, and asking for one would be a number
    # that means nothing.
    through = nxtools.checked("hole", {"diameter": 13, "through_all": True,
                                       "x": 10, "y": 20, "z": 0}, tree)
    check("a through hole carries no depth",
          "depth" not in through.arguments, str(through.arguments))
    counterbored = nxtools.checked(
        "hole", {"kind": "counterbored", "diameter": 6.6, "depth": 20,
                 "counterbore_diameter": 11, "counterbore_depth": 6.5,
                 "x": 0, "y": 0, "z": 0}, tree)
    check("a counterbore keeps both diameters and both depths",
          counterbored.arguments["counterbore_diameter"] == 11.0
          and counterbored.arguments["depth"] == 20.0,
          str(counterbored.arguments)[:80])
    check("every operation offered has a description a model can act on",
          all(len(d["description"]) > 40 for d in nxtools.definitions()),
          str([d["name"] for d in nxtools.definitions()]))

    print("\nEverything wrong with one operation, in one answer")
    # A model that forgot the position and the thread should be told
    # both. Told one at a time, each costs a model call and the engineer
    # waiting through it.
    several = refused("hole", {"kind": "threaded", "diameter": 0}, tree)
    check("a hole missing its size, its place and its thread says so once",
          all(word in several for word in
              ("diameter", "x is required", "thread")),
          several[:110])
    check("and the counterbore check still runs after a missing position",
          "wider" in refused("hole", {"kind": "counterbored", "diameter": 11,
                                      "counterbore_diameter": 9,
                                      "counterbore_depth": 5, "depth": 20},
                             tree), "")

    print("\nWhat the plugin may send that is not quite right")
    # This arrives over HTTP from code running inside somebody's NX. A
    # field that is missing should cost that field, not the turn.
    rough = nxtools.tree_from({"features": [
        {"name": "Extrude(1)"},
        {"kind": "Hole"},
        {"name": "Hole(3)", "kind": "Hole",
         "expressions": [{"name": "p2", "value": "not a number"},
                         {"name": "p3", "value": 8}]}]})
    check("a feature with no name is dropped, the rest are kept",
          [f.name for f in rough.features] == ["Extrude(1)", "Hole(3)"],
          str([f.name for f in rough.features]))
    check("and a value that is not a number costs that expression only",
          [e.name for e in rough.features[1].expressions] == ["p3"],
          str([e.name for e in rough.features[1].expressions]))

    print("\n" + "=" * 58)
    print("ALL CHECKS PASSED" if not failures else f"{failures} CHECK(S) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
