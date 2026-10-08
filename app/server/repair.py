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


def _with_import(code: str) -> tuple[str, str]:
    if _USES_CQ.search(code) and not _IMPORTS_AS_CQ.search(code):
        return "import cadquery as cq\n" + code, "added the missing `import cadquery as cq`"
    if _USES_CADQUERY.search(code) and not (_IMPORTS_CADQUERY.search(code)
                                            or _IMPORTS_AS_CQ.search(code)):
        return "import cadquery\n" + code, "added the missing `import cadquery`"
    return code, ""


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

    out, note = _with_import(out)
    if note:
        notes.append(note)

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
