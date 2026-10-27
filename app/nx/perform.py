"""Performing one operation with NX Open.

Separated from the journal that drives it so that the mapping from an
operation's name to NX's own API is one readable table rather than a
long function with the conversation wrapped round it.

Every call here is taken from the NX Open reference and none has been
run: there is no NX where this was written. They are written to fail
loudly and individually - one operation that NX refuses is reported as
that operation refused, with NX's own words, and the rest of the turn
carries on. The engineer sees which one failed and why, and so does the
model on the next turn.

`edit_expression` is the one to get right first. It is how an existing
part is changed, it is the operation the whole approach rests on, and it
is the simplest to verify: set a number, update, read it back.
"""


def _session():
    import NXOpen
    return NXOpen.Session.GetSession()


def _update(session, why):
    """Make the part rebuild, and say so if it will not.

    NX defers the recompute, so a change that has not been updated has
    not really happened - and a failure here is the part telling you the
    change was not valid, which is the most useful thing it can say.
    """
    try:
        marker = session.SetUndoMark(
            __import__("NXOpen").Session.MarkVisibility.Visible, why)
    except Exception:
        marker = None
    try:
        session.UpdateManager.DoUpdate(marker)
    except Exception as error:
        return "%s: %s" % (type(error).__name__, error)
    return ""


def edit_expression(arguments):
    """Set the number that drives a feature.

    The value is read back after the update rather than assumed. NX can
    accept a value and then not apply it - a constraint elsewhere, a
    rounding to the expression's units - and a tool that reports success
    it did not verify is worse than one that fails.
    """
    session = _session()
    work = session.Parts.Work
    name = arguments["name"]
    wanted = float(arguments["value"])

    found = None
    for one in work.Expressions:
        if getattr(one, "Name", "") == name:
            found = one
            break
    if found is None:
        return {"ok": False, "why": "this part has no expression called "
                                    + repr(name)}

    try:
        work.Expressions.Edit(found, "%s=%.10g" % (name, wanted))
    except Exception as error:
        return {"ok": False,
                "why": "NX would not take that value: %s: %s"
                       % (type(error).__name__, error)}

    trouble = _update(session, "CADSmith: " + name)
    if trouble:
        return {"ok": False, "why": "the part would not rebuild: " + trouble}

    try:
        now = float(found.Value)
    except Exception:
        now = None
    if now is not None and abs(now - wanted) > 1e-6:
        return {"ok": False,
                "why": "NX took the edit but %s is %g, not %g"
                       % (name, now, wanted)}
    return {"ok": True, "detail": "%s = %g" % (name, wanted)}


def suppress_feature(arguments):
    session = _session()
    work = session.Parts.Work
    name = arguments["name"]
    wanted = bool(arguments.get("suppressed", True))
    for one in work.Features:
        if getattr(one, "JournalIdentifier", getattr(one, "Name", "")) == name:
            try:
                if wanted:
                    work.Features.SuppressFeatures([one])
                else:
                    work.Features.UnsuppressFeatures([one])
            except Exception as error:
                return {"ok": False, "why": "%s: %s"
                                            % (type(error).__name__, error)}
            trouble = _update(session, "CADSmith: suppress " + name)
            if trouble:
                return {"ok": False, "why": trouble}
            return {"ok": True,
                    "detail": ("suppressed " if wanted else "restored ") + name}
    return {"ok": False, "why": "this part has no feature called " + repr(name)}


def delete_feature(arguments):
    session = _session()
    work = session.Parts.Work
    name = arguments["name"]
    for one in work.Features:
        if getattr(one, "JournalIdentifier", getattr(one, "Name", "")) == name:
            try:
                # Measured on NX v2412.0.0.5001: Features has no
                # DeleteFeatures. The documented route is to add the
                # object to the delete list and let the update do it.
                # The direct call is tried first for releases that have
                # it, so this works either way.
                deleter = getattr(work.Features, "DeleteFeatures", None)
                if callable(deleter):
                    deleter([one])
                else:
                    session.UpdateManager.AddToDeleteList([one])
            except Exception as error:
                return {"ok": False, "why": "%s: %s"
                                            % (type(error).__name__, error)}
            trouble = _update(session, "CADSmith: delete " + name)
            if trouble:
                return {"ok": False, "why": trouble}
            return {"ok": True, "detail": "deleted " + name}
    return {"ok": False, "why": "this part has no feature called " + repr(name)}


def read_part(arguments):
    import collect
    session = _session()
    return {"ok": True, "detail": "read the tree again",
            "tree": collect.part(session.Parts.Work)}


def _not_yet(what):
    def refuse(arguments):
        return {"ok": False,
                "why": what + " is not implemented on the NX side yet. The "
                              "expression-driven operations are, and they "
                              "are what changes an existing part."}
    return refuse


#: What performs each operation. The ones that change an existing part
#: are written; the ones that create geometry are not, and say so rather
#: than half-working. Which to build next is a question for the first
#: engineer who hits the limit, not for a guess made without NX.
PERFORM = {
    "edit_expression": edit_expression,
    "suppress_feature": suppress_feature,
    "delete_feature": delete_feature,
    "read_part": read_part,
    "sketch_extrude": _not_yet("sketch_extrude"),
    "hole": _not_yet("hole"),
    "edge_blend": _not_yet("edge_blend"),
    "chamfer": _not_yet("chamfer"),
}


def one(operation):
    """Perform one operation and say what happened, never raising."""
    name = operation.get("name", "")
    doer = PERFORM.get(name)
    if doer is None:
        return {"name": name, "ok": False,
                "why": "the plugin does not know how to " + repr(name)}
    try:
        answer = doer(operation.get("arguments") or {})
    except Exception as error:
        answer = {"ok": False,
                  "why": "%s: %s" % (type(error).__name__, error)}
    answer["name"] = name
    return answer
