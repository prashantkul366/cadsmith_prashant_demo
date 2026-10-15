"""Turning NX objects into the plain data the server reads.

Deliberately free of `import NXOpen`. Everything here takes an object
and asks it for properties by name, so it runs against a real NX feature
and against a stand-in with the same property names - which is the only
way any of this could be tested before there was an NX to test it on.

The defensiveness is not politeness. The property names were taken from
the NX Open reference without a session to confirm them, and some will
be wrong. Each one is asked for separately and a name that is not there
costs that one fact: a tree with no timestamps is still a usable tree,
where an exception half way through is nothing at all. `selfcheck.py`
reports which names this NX actually has, and this is written so that
the report can correct it without the shape changing.
"""

#: Where a feature's name might be, best first.
FEATURE_NAME = ("JournalIdentifier", "Name")
#: Where its kind might be.
FEATURE_KIND = ("FeatureType", "Type")
#: Both spellings of "is this feature switched off".
FEATURE_OFF = ("Suppressed", "IsSuppressed")
#: Both spellings of an expression's formula.
EXPRESSION_FORMULA = ("Equation", "RightHandSide")


def _first(thing, names, default=None):
    """The first of these properties that exists and answers.

    Not guarded with `hasattr`: that only swallows AttributeError, and a
    property raising anything else - which is how a .NET property that
    does not apply to this feature type surfaces in Python - would come
    straight back out and take the whole tree with it.
    """
    for name in names:
        try:
            got = getattr(thing, name)
            if callable(got):
                got = got()
        except Exception:
            continue
        if got is not None and got != "":
            return got
    return default


def _text(value, default=""):
    if value is None:
        return default
    try:
        return str(value)
    except Exception:
        return default


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def expression(raw):
    """One NX expression, as the server's tree model wants it."""
    name = _text(_first(raw, ("Name",)))
    if not name:
        return None
    formula = _text(_first(raw, EXPRESSION_FORMULA))
    value = _number(_first(raw, ("Value",), 0.0))
    # A formula that is just the number is not a formula. NX stores the
    # right-hand side of `p7 = 13` as "13", and treating that as driven
    # would make every plain number unwritable.
    if formula.strip() in ("", _text(value), "%g" % value):
        formula = ""
    return {
        "name": name,
        "value": value,
        "units": _text(_first(raw, ("Units",)), "mm"),
        # What the expression drives, in NX's own words:
        # "p7 (Simple Hole(12) Diameter)". Without it a part is p1..p40
        # and nothing can tell which one is a hole.
        "description": _text(_first(raw, ("Description",))),
        "formula": formula,
    }


def feature(raw, order=0):
    """One NX feature, with the expressions that drive it."""
    name = _text(_first(raw, FEATURE_NAME))
    if not name:
        return None
    drives = []
    getter = getattr(raw, "GetExpressions", None)
    if callable(getter):
        try:
            for one in (getter() or []):
                described = expression(one)
                if described is not None:
                    drives.append(described)
        except Exception:
            pass
    return {
        "name": name,
        "kind": _text(_first(raw, FEATURE_KIND), "unknown"),
        "timestamp": int(_number(_first(raw, ("Timestamp",), order), order)),
        "suppressed": bool(_first(raw, FEATURE_OFF, False)),
        "expressions": drives,
    }


def part(work):
    """The whole part, as the body of a turn.

    Takes the work part itself so the one place that touches NX's object
    model is here, and everything above it is plain data.
    """
    features = []
    try:
        for order, one in enumerate(work.Features):
            described = feature(one, order)
            if described is not None:
                features.append(described)
    except Exception:
        pass

    expressions = []
    try:
        for one in work.Expressions:
            described = expression(one)
            if described is not None:
                expressions.append(described)
    except Exception:
        pass

    return {
        "part": _text(_first(work, ("Name",)), "(unnamed)"),
        "units": "mm",
        "features": features,
        "expressions": expressions,
    }
