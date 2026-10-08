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

    print("\n" + "=" * 58)
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED: {', '.join(failures[:5])}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
