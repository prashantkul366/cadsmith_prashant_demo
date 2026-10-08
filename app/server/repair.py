# -*- coding: utf-8 -*-
"""Repair a generated script's *transcription*, never its geometry.

Measured over 45 runs of the library, more than half of everything that went
wrong never reached the kernel at all - the script would not import or would
not parse:

    22  SyntaxError: '(' was never closed
    20  NameError: name 'cq' is not defined
    10  NameError: name 'cadquery' is not defined

None of those is a CAD mistake. One script ran to 351 lines, opened with
``cq.Workplane("XY").box(100, 100, 30)`` - no import, no ``result`` - and
ended mid-expression at ``pushPoints([\\n    (-``, cut off at the token
ceiling. The model had understood the part; the reply was damaged in
transit.

So this module fixes only what is unambiguous about the text:

  * the fence a model wraps code in, wherever it put it;
  * the ``import cadquery as cq`` a script uses and does not declare;
  * a trailing expression that is plainly the part, bound to ``result``.

It never adds, removes or changes an operation. If a script says to cut
four holes it still cuts four; if it says one it still says one, and the
gate still fails it. Anything that does not parse after this is handed back
with the line and the column, because an Error Refiner told "line 348:
'(' was never closed, and the reply looks truncated" fixes a different
thing from one shown a traceback.
"""

from __future__ import annotations

import ast
import re
from typing import Optional

#: A fenced block, however the model labelled it.
_FENCE = re.compile(r"```[ \t]*(?:python|py)?[ \t]*\r?\n(.*?)(?:```|\Z)",
                    re.DOTALL | re.IGNORECASE)

#: Does the script reach for the module under either name?
_USES_CQ = re.compile(r"(?<![\w.])cq\s*\.", re.MULTILINE)
_USES_CADQUERY = re.compile(r"(?<![\w.])cadquery\s*\.", re.MULTILINE)

#: Is it already imported, under any of the spellings that would work?
_IMPORTS_AS_CQ = re.compile(r"^\s*(?:import\s+cadquery\s+as\s+cq"
                            r"|from\s+cadquery\s+import\s+.*\bcq\b)",
                            re.MULTILINE)
_IMPORTS_CADQUERY = re.compile(r"^\s*import\s+cadquery(?!\s+as)", re.MULTILINE)


def _parses(code: str) -> Optional[SyntaxError]:
    try:
        ast.parse(code)
    except SyntaxError as bad:
        return bad
    return None


def _unfenced(code: str) -> str:
    """The code inside the fence, when the fence is what broke it.

    Only used if the text as given does not parse and the fenced part does,
    so a script that happens to contain the characters in a string is left
    alone.
    """
    blocks = [found.group(1) for found in _FENCE.finditer(code)]
    if not blocks:
        return code
    best = max(blocks, key=len)
    return best if _parses(best) is None else code


def _with_import(code: str) -> tuple[str, list[str]]:
    """Declare every name the script reaches for, not just the first one.

    ``import cadquery as cq`` binds ``cq`` and nothing else, and
    ``import cadquery`` binds ``cadquery`` and nothing else. A model that
    writes both names - measured, it does - needs both lines, and the first
    version of this returned after the first match: the log said the import
    had been added and the script still died on ``name 'cadquery' is not
    defined``.
    """
    lines: list[str] = []
    notes: list[str] = []
    if _USES_CQ.search(code) and not _IMPORTS_AS_CQ.search(code):
        lines.append("import cadquery as cq")
        notes.append("added the missing `import cadquery as cq`")
    if _USES_CADQUERY.search(code) and not _IMPORTS_CADQUERY.search(code):
        lines.append("import cadquery")
        notes.append("added the missing `import cadquery`")
    if not lines:
        return code, []
    return "\n".join(lines) + "\n" + code, notes


def _assigns_result(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "result" \
                and isinstance(node.ctx, ast.Store):
            return True
    return False


def _with_result(code: str) -> tuple[str, str]:
    """Bind a trailing bare expression to ``result``.

    The runner looks for ``result``; a model that ends on the expression
    itself has said which solid it means, and there is exactly one reading.
    Only the last top-level statement, only when nothing anywhere assigns
    ``result``, and never for a call whose value is clearly not the part
    (an export, a print).
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code, ""
    if not tree.body or _assigns_result(tree):
        return code, ""
    last = tree.body[-1]
    if not isinstance(last, ast.Expr):
        return code, ""
    text = ast.get_source_segment(code, last.value)
    if not text or text.strip().startswith(("print", "show", "cq.exporters")):
        return code, ""
    lines = code.splitlines()
    start = (last.lineno or 1) - 1
    end = (getattr(last, "end_lineno", last.lineno) or last.lineno) - 1
    rebuilt = lines[:start] + ("result = " + text).splitlines() + lines[end + 1:]
    patched = "\n".join(rebuilt) + ("\n" if code.endswith("\n") else "")
    if _parses(patched) is not None:
        return code, ""
    return patched, "bound the trailing expression to `result`"


def looks_truncated(code: str) -> bool:
    """Was the reply cut off rather than wrong?

    An unclosed bracket at the very end, with no closing one after it, is
    what a token ceiling leaves behind. Distinguished from a genuine typo
    because the script is long and the break is at the end of it.
    """
    if _parses(code) is None:
        return False
    opens = sum(code.count(ch) for ch in "([{")
    closes = sum(code.count(ch) for ch in ")]}")
    if opens <= closes:
        return False
    tail = code.rstrip()
    return bool(tail) and tail[-1] in "([{,=+-*/" or opens - closes > 1


def normalise(code: str) -> tuple[str, list[str]]:
    """The script as it should have arrived, and what had to be mended.

    Returns the code unchanged and an empty list when nothing was wrong,
    which is the common case once the token ceiling is high enough.
    """
    notes: list[str] = []
    out = code.strip()

    if _parses(out) is not None:
        inner = _unfenced(out)
        if inner is not out and inner.strip() != out:
            out = inner.strip()
            notes.append("took the code out of its markdown fence")

    out, added = _with_import(out)
    notes.extend(added)

    out, note = _with_result(out)
    if note:
        notes.append(note)

    return out, notes


def complaint(code: str) -> str:
    """What to tell the Error Refiner when the script will not parse.

    Names the line and the column, and says plainly when the reply looks
    truncated - a model told its code was cut off writes a shorter script,
    where one shown a traceback hunts for a bug that is not there.
    """
    bad = _parses(code)
    if bad is None:
        return ""
    where = f"line {bad.lineno}" + (f", column {bad.offset}" if bad.offset else "")
    said = f"The script does not parse: {bad.msg} ({where})."
    if looks_truncated(code):
        said += (" The reply was cut off at the token limit rather than "
                 "being wrong - it is incomplete, not mistaken. Write the "
                 "whole part again more compactly: build hole positions with "
                 "a loop or a list comprehension instead of writing every "
                 "coordinate out, and keep comments short.")
    return said


# ---------------------------------------------------------------------------
# Advice for the mistakes a model makes over and over
# ---------------------------------------------------------------------------

#: Matched against an execution error, and appended to what the Error
#: Refiner is told. KB2 already covers the kernel's own complaints -
#: fillets too large, no pending wires, unclosed wires. These are the
#: *API* mistakes measured over the library, where the traceback names a
#: Python attribute and says nothing about what to write instead.
#:
#: Each entry is (what appears in the error, what to do about it). Kept
#: here rather than in autofab/rag_kb2.py so the research pipeline stays
#: the published one.
_ADVICE: tuple[tuple[str, str], ...] = (
    ("object has no attribute 'wrapped'",
     "`.wrapped` is on a Shape, not on a Workplane. Use `.val().wrapped` "
     "if you need the OCCT object, or stay in the Workplane API."),
    ("moveTo() takes from 1 to 3 positional arguments",
     "`moveTo` takes two coordinates in the plane - moveTo(x, y). It is a "
     "2D move on the current workplane, so there is no third argument. To "
     "work at a height, select the face and call .workplane() there."),
    ("move() takes from 1 to 3 positional arguments",
     "`move` takes two coordinates in the plane - move(x, y), relative to "
     "where you are. There is no third argument."),
    ("'Solid' object has no attribute",
     "You are holding a Solid, not a Workplane - `.val()` and `.findSolid()` "
     "return one. Booleans and selectors live on the Workplane: keep the "
     "Workplane in your variable and call .cut(), .union(), .faces() on "
     "that."),
    ("'Vector' object has no attribute 'rotate'",
     "A Vector does not rotate itself. Rotate the shape instead - "
     ".rotate(axisStart, axisEnd, angleDegrees) on the Workplane - or "
     "compute the rotated coordinates arithmetically."),
    ("object has no attribute 'roundedRect'",
     "There is no roundedRect. Draw `.rect(w, h)` and then round the "
     "upright edges with `.edges('|Z').fillet(r)`, which is how a plate "
     "gets its corner radius."),
    ("object has no attribute 'slot'",
     "There is no slot. A slot is two circles and a rectangle: "
     "`.moveTo(-a, 0).circle(r).moveTo(a, 0).circle(r).rect(2*a, 2*r)` "
     "unioned, or a rectangle with its short ends filleted to half the "
     "width."),
    ("If multiple objects selected, they all must be planar faces",
     "`.workplane()` needs exactly one planar face. Your selector matched "
     "several faces or a curved one - narrow it, e.g. `.faces('>Z')` for "
     "the topmost rather than `.faces('|Z')` for every one facing that "
     "way."),
    ("must have at least one solid on the stack to union",
     "There is nothing to union with yet. Build the first solid into a "
     "variable, then union the second into it - `result = base.union(other)` "
     "- rather than chaining a union onto an empty Workplane."),
    ("Cannot find a solid on the stack or in the parent chain",
     "The chain lost its solid, usually because a selector matched nothing "
     "and the Workplane became empty. Assign intermediate results to "
     "variables so you can see which step emptied it."),
    ("ChFi3d_Builder", 
     "The kernel could not build that fillet or chamfer on the edges "
     "selected - usually because the radius is as large as the face it "
     "has to run across, or the selection includes edges that meet at a "
     "point. Select fewer edges, or use a smaller radius."),
    ("GC_MakeArcOfCircle",
     "That arc is degenerate - three points on a line, or a radius too "
     "small for the distance between its ends. Check the geometry of the "
     "points before the arc, or use a straight line there."),
)


def advice(error: str) -> str:
    """What to do about this error, where the traceback does not say.

    Returns an empty string for anything unrecognised, so the Error
    Refiner's own reading - and KB2's patterns - are left to it.
    """
    if not error:
        return ""
    found = [what for marker, what in _ADVICE if marker in error]
    if not found:
        return ""
    return ("\n\nWhat this error means in the CadQuery API:\n"
            + "\n".join("  - " + line for line in found))
