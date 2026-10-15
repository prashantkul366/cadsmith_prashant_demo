"""Reading an NX part into the data the server reads.

There is no NX here, so the objects are stand-ins: plain Python with
the property names NX Open's reference gives. That proves the reading
logic and proves nothing about the names. The names are what
`app/nx/selfcheck.py` goes to measure on a machine that has NX.

What this does catch, and it is most of what goes wrong in code like
this: a property that is missing costing the whole tree, a formula that
is really just a number being treated as a relation, a method that
raises taking everything with it.

Run:  .venv/bin/python -m app.tests.test_nx_collect
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.nx import collect        # noqa: E402
from app.server import nxtools    # noqa: E402


class Expression:
    """What NX Open's reference says an expression looks like."""

    def __init__(self, name, value, units="mm", description="",
                 equation=None):
        self.Name = name
        self.Value = value
        self.Units = units
        self.Description = description
        if equation is not None:
            self.Equation = equation


class Feature:
    def __init__(self, identifier, kind, timestamp=0, suppressed=False,
                 drives=()):
        self.JournalIdentifier = identifier
        self.FeatureType = kind
        self.Timestamp = timestamp
        self.Suppressed = suppressed
        self._drives = list(drives)

    def GetExpressions(self):
        return self._drives


class Part:
    def __init__(self, name, features, expressions):
        self.Name = name
        self.Features = features
        self.Expressions = expressions


def main() -> int:
    failures = 0

    def check(what: str, ok: bool, saw: str = "") -> None:
        nonlocal failures
        if not ok:
            failures += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {what}"
              + (f" - {saw}" if saw else ""))

    diameter = Expression("p7", 13.0, "mm", "p7 (Simple Hole(12) Diameter)")
    radius = Expression("p9", 5.0, "mm", "p9 (Edge Blend(14) Radius)",
                        equation="wall/2")
    plain = Expression("p1", 25.0, "mm", "p1 (Extrude(1) Limit End)",
                       equation="25")
    work = Part("bracket",
                [Feature("Extrude(1)", "Extrude", 1, False, [plain]),
                 Feature("Simple Hole(12)", "Hole", 2, False, [diameter]),
                 Feature("Edge Blend(14)", "Blend", 3, True, [radius])],
                [plain, diameter, radius])

    print("A part read the way the plugin would read it")
    got = collect.part(work)
    check("every feature comes across",
          [f["name"] for f in got["features"]]
          == ["Extrude(1)", "Simple Hole(12)", "Edge Blend(14)"],
          str([f["name"] for f in got["features"]]))
    check("with the expressions that drive it",
          got["features"][1]["expressions"][0]["name"] == "p7",
          str(got["features"][1]["expressions"]))
    check("and the description that says what it drives",
          got["features"][1]["expressions"][0]["description"]
          == "p7 (Simple Hole(12) Diameter)", "")
    check("a suppressed feature says so",
          got["features"][2]["suppressed"] is True, "")

    print("\nA formula, and a number that only looks like one")
    # NX stores the right-hand side of `p1 = 25` as "25". Reading that
    # as a relation would make every plain number unwritable, which is
    # most of the numbers on most parts.
    check("a real formula is kept",
          got["expressions"][2]["formula"] == "wall/2",
          got["expressions"][2]["formula"])
    check("and a right-hand side that is just the value is not a formula",
          got["expressions"][0]["formula"] == "",
          repr(got["expressions"][0]["formula"]))

    print("\nWhat the server makes of it")
    # The two halves have to agree: this is the shape nxtools parses.
    tree = nxtools.tree_from(got)
    check("the server reads it back without loss",
          len(tree.features) == 3 and len(tree.expressions) == 3,
          f"{len(tree.features)} features, {len(tree.expressions)} expressions")
    check("and can be told to open the hole",
          nxtools.checked("edit_expression", {"name": "p7", "value": 11.0},
                          tree).arguments["value"] == 11.0, "")
    try:
        nxtools.checked("edit_expression", {"name": "p9", "value": 3.0}, tree)
        check("while the formula-driven one is still refused", False, "it was not")
    except nxtools.NXToolError as error:
        check("while the formula-driven one is still refused",
              "wall/2" in str(error), str(error)[:60])

    print("\nWhen this NX is not the NX the reference described")
    # Every property name here was taken from documentation without a
    # session to confirm it. Some will be wrong on the machine this
    # finally runs on, and a wrong one must cost one fact.
    class Older:
        Name = "Hole(3)"          # no JournalIdentifier
        Type = "Hole"             # no FeatureType
        IsSuppressed = True       # the other spelling

        def GetExpressions(self):
            return [Expression("p2", 8.0)]

    older = collect.feature(Older())
    check("a feature named the other way is still read",
          older["name"] == "Hole(3)" and older["kind"] == "Hole", str(older))
    check("and the other spelling of suppressed is understood",
          older["suppressed"] is True, str(older["suppressed"]))

    class Hostile:
        JournalIdentifier = "Extrude(9)"
        FeatureType = "Extrude"

        @property
        def Timestamp(self):
            raise RuntimeError("this NX does not like that question")

        def GetExpressions(self):
            raise RuntimeError("nor that one")

    rough = collect.feature(Hostile(), order=4)
    check("a property that raises costs that property only",
          rough is not None and rough["name"] == "Extrude(9)", str(rough))
    check("and falls back to the order it was found in",
          rough["timestamp"] == 4, str(rough["timestamp"]))
    check("a method that raises leaves the feature without numbers, not gone",
          rough["expressions"] == [], str(rough["expressions"]))

    class Nameless:
        FeatureType = "Extrude"

    check("a feature with no name at all is dropped rather than guessed at",
          collect.feature(Nameless()) is None, "")

    print("\n" + "=" * 58)
    print("ALL CHECKS PASSED" if not failures else f"{failures} CHECK(S) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
