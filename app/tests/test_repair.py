# -*- coding: utf-8 -*-
"""The script arrived damaged; does it still mean the same part?

Every case here is taken from a real run over the prompt library, where
more than half of everything that went wrong never reached the kernel: the
script would not import or would not parse. The repair must mend the
transcription and leave the geometry alone - a script that cuts one hole
must still cut one hole afterwards, so the gate can still fail it.

Run:  .venv/bin/python -m app.tests.test_repair
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.server import repair  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


# The real one: 351 lines, no import, no `result`, from app/runs.
BARE = '''cq.Workplane("XY").box(100, 100, 30, centered=(True, True, True)).faces("<Z").workplane().pushPoints([
    (-45, -45),
    (45, 45),
]).hole(6.4)'''

GOOD = '''import cadquery as cq

side = 25.0
result = cq.Workplane("XY").box(side, side, side)
'''


def main() -> int:
    print("A script that will not import")
    out, notes = repair.normalise(BARE)
    check("the missing import is added",
          out.startswith("import cadquery as cq"), out.splitlines()[0])
    check("and the trailing expression becomes the part",
          "result = cq.Workplane" in out,
          next((l for l in out.splitlines() if "result" in l), "")[:48])
    check("both repairs are reported, not silent", len(notes) == 2, str(notes))
    check("and what comes out parses", repair.complaint(out) == "",
          repair.complaint(out)[:70])

    print("\nA script that is already right is not touched")
    out, notes = repair.normalise(GOOD)
    check("nothing is changed", out == GOOD.strip(), out[:40])
    check("and nothing is claimed", notes == [], str(notes))

    print("\nThe geometry is never altered")
    one_hole = ('import cadquery as cq\n'
                'result = cq.Workplane("XY").box(50, 50, 6).faces(">Z")'
                '.workplane().hole(5.5)\n')
    out, _ = repair.normalise(one_hole)
    check("a script that cuts one hole still cuts one hole",
          out.count("hole(") == 1 and "5.5" in out, out[-60:])

    print("\nA script that mixes both names needs both imports")
    # Measured: the repair added `import cadquery as cq`, said so, and the
    # script still died on `name 'cadquery' is not defined`. `as cq` binds
    # cq and nothing else.
    mixed = ('result = cq.Workplane("XY").box(10, 10, 10)\n'
             'sphere = cadquery.Workplane("XY").sphere(5)\n'
             'result = result.cut(sphere)\n')
    out, notes = repair.normalise(mixed)
    check("both imports are added", "import cadquery as cq" in out
          and "import cadquery\n" in out, str(out.splitlines()[:2]))
    check("and both are reported", len(notes) == 2, str(notes))
    ns: dict = {}
    try:
        compile(out, "<repaired>", "exec")
        compiled = True
    except SyntaxError as bad:
        compiled = False
    check("what comes out compiles", compiled)

    print("\nA fence the model wrapped the code in")
    fenced = "Here is the part:\n```python\n" + GOOD + "```\nHope that helps!"
    out, notes = repair.normalise(fenced)
    check("the code comes out of the fence",
          out.startswith("import cadquery as cq") and "Hope that helps" not in out,
          out.splitlines()[0])
    check("and it parses", repair.complaint(out) == "")

    print("\nA reply cut off at the token ceiling")
    cut = ('import cadquery as cq\n'
           'result = cq.Workplane("XY").pushPoints([\n    (-45, -45),\n    (-')
    check("the truncation is recognised", repair.looks_truncated(cut) is True)
    said = repair.complaint(cut)
    check("the complaint names the line", "line" in said, said[:60])
    check("and says it was cut off rather than wrong",
          "cut off at the token limit" in said, said[-80:])
    check("a genuine typo is not blamed on truncation",
          repair.looks_truncated('import cadquery as cq\nresult = cq.box(1,,2)\n') is False)

    print("\nWhat must not be mistaken for the part")
    already = ('import cadquery as cq\n'
               'result = cq.Workplane("XY").box(1, 1, 1)\n'
               'print(result)\n')
    out, notes = repair.normalise(already)
    check("a trailing print is not bound to result",
          out == already.strip() and notes == [], str(notes))
    assembly = ('import cadquery as cq\n'
                'part = cq.Workplane("XY").box(1, 1, 1)\n'
                'result = cq.Assembly().add(part)\n')
    out, notes = repair.normalise(assembly)
    check("an assembly that already assigns result is left alone",
          notes == [], str(notes))

    print("\nAdvice for the mistakes a model makes over and over")
    cases = {
        "AttributeError: 'Workplane' object has no attribute 'wrapped'": ".val()",
        "TypeError: Workplane.moveTo() takes from 1 to 3 positional arguments but 4 were given": "moveTo(x, y)",
        "AttributeError: 'Workplane' object has no attribute 'roundedRect'": "edges('|Z').fillet",
        "ValueError: Workplane object must have at least one solid on the stack to union!": "union(other)",
        "ValueError: If multiple objects selected, they all must be planar faces.": ">Z",
    }
    for error, wanted in cases.items():
        said = repair.advice(error)
        check(f"{error.split(':')[1].strip()[:44]}", wanted in said,
              said.splitlines()[-1][:70] if said else "nothing said")
    check("an error it does not know gets no invented advice",
          repair.advice("ZeroDivisionError: division by zero") == "")
    check("and an empty error says nothing", repair.advice("") == "")

    print("\n" + "=" * 58)
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED: {', '.join(failures[:5])}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
