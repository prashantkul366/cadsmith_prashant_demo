"""The only file here that touches NX.

Five tools, and four of them are one NX call each. The fifth, `nx_python`,
is the point of the exercise: it hands Claude the NX Open API itself,
with the session already bound under the names NX's own journal recorder
uses - `theSession`, `workPart`, `theUI` - so that what Claude writes
looks like a recorded journal, because that is the NX code it has seen
most of.

Nothing here teaches Claude about CAD. There is no vocabulary of
operations, no validation, no retry, no guidance in the tool
descriptions beyond what the argument is. If Claude can change a part, it
is because it knows NX, not because this folder arranged things so that
it could. That is the question being asked.

Two safety properties, both worth knowing before running it on a part
that matters:

* An undo mark is set before every tool that changes anything, so a bad
  edit is one Ctrl+Z away and a bad run is a few.
* With BARE_DRY=1 nothing executes. Claude is told so, each write is
  reported back as refused with the code or value it wanted, and the
  transcript is a complete record of what it would have done. Worth one
  pass before the first real one.
"""

import io
import os
import sys
import traceback


def dry():
    return os.environ.get("BARE_DRY", "").strip() in ("1", "yes", "true")


def _nx():
    import NXOpen
    return NXOpen


def session():
    return _nx().Session.GetSession()


def say(text):
    """Into NX's Information window, and to stdout if there is one."""
    try:
        window = session().ListingWindow
        window.Open()
        for line in str(text).splitlines() or [""]:
            window.WriteLine(line)
    except Exception:
        pass
    try:
        sys.stdout.write(str(text) + "\n")
    except Exception:
        pass


def _mark(why):
    """An undo mark, so every change below can be backed out by hand."""
    try:
        NXOpen = _nx()
        return session().SetUndoMark(
            NXOpen.Session.MarkVisibility.Visible, why)
    except Exception:
        return None


def _update(why):
    """Make the part rebuild. A deferred change has not happened yet."""
    marker = _mark(why)
    try:
        session().UpdateManager.DoUpdate(marker)
    except Exception as error:
        return "%s: %s" % (type(error).__name__, error)
    return ""


def _get(thing, name, default=None):
    """One property, or the default if this object has not got it.

    Property names here were taken from the NX Open reference and some
    will be wrong on 2412. A name that is missing should cost that one
    fact and not the whole tree, and `hasattr` will not do it: a .NET
    property that does not apply to a feature type raises something other
    than AttributeError on access.
    """
    try:
        got = getattr(thing, name)
        return got() if callable(got) else got
    except Exception:
        return default


# --------------------------------------------------------------------
# the tools
# --------------------------------------------------------------------

def read_tree(arguments):
    """Features in order, and every expression, as plain data."""
    work = session().Parts.Work
    features = []
    for order, one in enumerate(_get(work, "Features", []) or []):
        features.append({
            "n": order + 1,
            "name": str(_get(one, "JournalIdentifier",
                             _get(one, "Name", "?"))),
            "type": str(_get(one, "FeatureType", "?")),
            "suppressed": bool(_get(one, "Suppressed", False)),
        })
    expressions = []
    for one in (_get(work, "Expressions", []) or []):
        name = _get(one, "Name", "")
        if not name:
            continue
        expressions.append({
            "name": str(name),
            "value": _get(one, "Value", None),
            "units": str(_get(one, "Units", "")),
            # NX writes what an expression drives in here, as
            # "p7 (Simple Hole(12) Diameter)". Without it the list is
            # p1..p40 and means nothing.
            "describes": str(_get(one, "Description", "")),
            "equation": str(_get(one, "Equation",
                                 _get(one, "RightHandSide", ""))),
        })
    return {
        "part": str(_get(work, "FullPath", _get(work, "Name", "?"))),
        "features": features,
        "expressions": expressions,
    }


def set_expression(arguments):
    """Set one expression to one number, and read it back."""
    name = str(arguments["name"])
    wanted = float(arguments["value"])
    if dry():
        return {"ok": False, "why": "BARE_DRY is set, nothing was changed",
                "would": "%s = %g" % (name, wanted)}

    work = session().Parts.Work
    found = None
    for one in (_get(work, "Expressions", []) or []):
        if str(_get(one, "Name", "")) == name:
            found = one
            break
    if found is None:
        return {"ok": False, "why": "no expression called " + repr(name)}

    _mark("bare: " + name)
    try:
        work.Expressions.Edit(found, "%s=%.10g" % (name, wanted))
    except Exception as error:
        return {"ok": False, "why": "%s: %s" % (type(error).__name__, error)}
    trouble = _update("bare: update after " + name)
    if trouble:
        return {"ok": False, "why": "the part would not rebuild: " + trouble}

    now = _get(found, "Value", None)
    try:
        if now is not None and abs(float(now) - wanted) > 1e-6:
            return {"ok": False,
                    "why": "NX took the edit but %s reads %g" % (name, now)}
    except (TypeError, ValueError):
        pass
    return {"ok": True, "now": "%s = %g" % (name, wanted)}


def _feature(work, name):
    for one in (_get(work, "Features", []) or []):
        if str(_get(one, "JournalIdentifier", _get(one, "Name", ""))) == name:
            return one
    return None


def suppress_feature(arguments):
    name = str(arguments["name"])
    off = bool(arguments.get("suppressed", True))
    if dry():
        return {"ok": False, "why": "BARE_DRY is set, nothing was changed",
                "would": ("suppress " if off else "unsuppress ") + name}
    work = session().Parts.Work
    one = _feature(work, name)
    if one is None:
        return {"ok": False, "why": "no feature called " + repr(name)}
    _mark("bare: suppress " + name)
    try:
        if off:
            work.Features.SuppressFeatures([one])
        else:
            work.Features.UnsuppressFeatures([one])
    except Exception as error:
        return {"ok": False, "why": "%s: %s" % (type(error).__name__, error)}
    trouble = _update("bare: update after suppress")
    if trouble:
        return {"ok": False, "why": trouble}
    return {"ok": True, "now": ("suppressed " if off else "restored ") + name}


def delete_feature(arguments):
    name = str(arguments["name"])
    if dry():
        return {"ok": False, "why": "BARE_DRY is set, nothing was changed",
                "would": "delete " + name}
    work = session().Parts.Work
    one = _feature(work, name)
    if one is None:
        return {"ok": False, "why": "no feature called " + repr(name)}
    _mark("bare: delete " + name)
    try:
        work.Features.DeleteFeatures([one])
    except Exception as error:
        return {"ok": False, "why": "%s: %s" % (type(error).__name__, error)}
    trouble = _update("bare: update after delete")
    if trouble:
        return {"ok": False, "why": trouble}
    return {"ok": True, "now": "deleted " + name}


def nx_python(arguments):
    """Run Claude's own NX Open code in this session.

    The bound names are NX's journal-recorder names on purpose. What
    comes back is whatever the snippet printed, plus `result` if it set
    one, plus the traceback if it raised - the traceback being the most
    useful of the three, because it is how Claude finds out that the
    class it reached for is spelt differently on this release.
    """
    code = str(arguments.get("code", ""))
    if not code.strip():
        return {"ok": False, "why": "no code"}
    if dry():
        return {"ok": False, "why": "BARE_DRY is set, nothing was run",
                "would": code}

    NXOpen = _nx()
    the_session = NXOpen.Session.GetSession()
    scope = {
        "NXOpen": NXOpen,
        "theSession": the_session,
        "workPart": the_session.Parts.Work,
        "displayPart": _get(the_session.Parts, "Display", None),
        "result": None,
    }
    try:
        # Not through _get: NXOpen.UI is a class, and _get calls what it
        # finds if it is callable, which would construct one.
        scope["theUI"] = NXOpen.UI.GetUI()
    except Exception:
        scope["theUI"] = None
    _mark("bare: nx_python")

    held, sys.stdout = sys.stdout, io.StringIO()
    try:
        try:
            exec(compile(code, "<claude>", "exec"), scope, scope)
            failed = ""
        except Exception:
            failed = traceback.format_exc(limit=6)
    finally:
        printed, sys.stdout = sys.stdout.getvalue(), held

    answer = {"ok": not failed, "printed": printed[-4000:]}
    if scope.get("result") is not None:
        answer["result"] = repr(scope["result"])[:4000]
    if failed:
        answer["why"] = failed[-4000:]
        return answer
    trouble = _update("bare: update after nx_python")
    if trouble:
        answer["ok"] = False
        answer["why"] = "the code ran but the part would not rebuild: " \
                        + trouble
    return answer


#: What Claude is told it can do. Deliberately thin: an argument name and
#: what it is, and no advice about when to use which.
TOOLS = [
    {
        "name": "read_tree",
        "description": "List the work part's features in tree order and "
                       "all of its expressions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "set_expression",
        "description": "Set one NX expression to a number and rebuild.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string",
                         "description": "the expression's name, e.g. p7"},
                "value": {"type": "number"},
            },
            "required": ["name", "value"],
        },
    },
    {
        "name": "suppress_feature",
        "description": "Suppress or unsuppress one feature.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string",
                         "description": "the feature's journal identifier"},
                "suppressed": {"type": "boolean"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "delete_feature",
        "description": "Delete one feature from the tree.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "nx_python",
        "description":
            "Run Python in this NX session. NXOpen is imported and "
            "theSession, workPart, displayPart and theUI are bound. "
            "Assign to `result` or print to return something. The part is "
            "updated afterwards.",
        "input_schema": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    },
]

PERFORM = {
    "read_tree": read_tree,
    "set_expression": set_expression,
    "suppress_feature": suppress_feature,
    "delete_feature": delete_feature,
    "nx_python": nx_python,
}


def perform(name, arguments):
    """Do one tool call and always answer, never raise."""
    doer = PERFORM.get(name)
    if doer is None:
        return {"ok": False, "why": "no such tool: " + repr(name)}
    try:
        return doer(arguments or {})
    except Exception:
        return {"ok": False, "why": traceback.format_exc(limit=6)[-4000:]}
