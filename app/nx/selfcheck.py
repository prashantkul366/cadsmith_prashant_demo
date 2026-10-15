"""What NX Open on this machine actually offers, written to a file.

Run as a journal with a part open:  File -> Execute -> NX Open

This does nothing to the part. It opens nothing, changes nothing and
saves nothing. It asks the API about itself and writes the answers to
`cadsmith-nx-report.json` beside this file.

The reason it is the first thing to run: the rest of this plugin was
written against the NX Open reference by somebody who has never had an
NX to run it on. Every property name in it is a guess of the educated
kind. This turns that guessing into one measurement - the report says
which names exist on this NX, which answer, and what they answer with -
so the rest can be corrected from evidence rather than from another
reading of the documentation.

It is also the integration check in its own right. If this cannot reach
NX Open, or cannot see a part, or the licence refuses, that is the answer
to "can the tool be integrated with NX here" and it arrives in one
minute rather than after a week of plumbing.
"""

import datetime
import json
import os
import platform
import sys
import traceback

#: Everything the plugin needs from a feature, and what it would be for.
#: Reported one by one so a missing name costs that one fact.
FEATURE_WANTS = [
    ("Name", "what to call it in the tree"),
    ("FeatureType", "what kind of feature it is"),
    ("JournalIdentifier", "a stable handle to refer to it by"),
    ("Timestamp", "where it sits in the build order"),
    ("Suppressed", "whether it is currently taken out"),
    ("IsSuppressed", "the other spelling of the same thing"),
    ("GetFeatureName", "the display name, where it differs"),
    ("GetExpressions", "the numbers that drive it - the important one"),
]

#: Everything the plugin needs from an expression.
EXPRESSION_WANTS = [
    ("Name", "p1, p7, and so on"),
    ("Value", "the number"),
    ("Units", "what the number is in"),
    ("Description", "which feature and parameter it drives"),
    ("Equation", "the formula, where there is one"),
    ("RightHandSide", "the other spelling of the formula"),
    ("Type", "number, string, point"),
    ("EditLocked", "whether it may be written at all"),
]

#: The session-level things the plugin needs to exist.
SESSION_WANTS = [
    ("Parts", "the open parts"),
    ("UpdateManager", "making the part rebuild after a change"),
    ("ListingWindow", "somewhere to print"),
    ("Preferences", "settings"),
]


def _ask(thing, name):
    """Whether this name exists here, and what it gives back.

    Never raises. A property that throws when read is a fact worth
    reporting, not a reason to lose the rest of the report.
    """
    if not hasattr(thing, name):
        return {"there": False}
    try:
        got = getattr(thing, name)
    except Exception as error:
        return {"there": True, "reading it raised":
                "%s: %s" % (type(error).__name__, error)}
    if callable(got):
        try:
            called = got()
        except Exception as error:
            return {"there": True, "callable": True, "calling it raised":
                    "%s: %s" % (type(error).__name__, error)}
        return {"there": True, "callable": True,
                "gives": _describe(called)}
    return {"there": True, "callable": False, "is": _describe(got)}


def _describe(value):
    """A value as something JSON can carry and a person can read."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:200]
    if isinstance(value, (list, tuple)):
        return {"count": len(value),
                "first": _describe(value[0]) if value else None}
    return "%s: %s" % (type(value).__name__, str(value)[:120])


def main():
    report = {
        "written": datetime.datetime.now().isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "nx": {},
        "session": {},
        "part": {},
        "features": [],
        "expressions": [],
        "trouble": [],
    }

    try:
        import NXOpen
    except Exception as error:
        report["trouble"].append(
            "NXOpen would not import: %s: %s. Nothing else could run."
            % (type(error).__name__, error))
        return _write(report)

    try:
        session = NXOpen.Session.GetSession()
    except Exception as error:
        report["trouble"].append(
            "no NX session: %s: %s" % (type(error).__name__, error))
        return _write(report)

    # Which NX this is. The plugin is aimed at 2412.5000 and the first
    # thing anyone will ask of a surprising result is what it ran on.
    for name in ("GetEnvironmentVariableValue", "BuildNumber", "ReleaseNumber"):
        report["nx"][name] = _ask(session, name)
    for variable in ("UGII_FULL_VERSION", "UGII_VERSION", "UGII_BASE_DIR",
                     "UGII_LANG"):
        try:
            report["nx"][variable] = session.GetEnvironmentVariableValue(
                variable)
        except Exception:
            report["nx"][variable] = os.environ.get(variable, "(not set)")

    for name, why in SESSION_WANTS:
        report["session"][name] = {"for": why, **_ask(session, name)}

    try:
        part = session.Parts.Work
    except Exception as error:
        report["trouble"].append(
            "no work part: %s: %s" % (type(error).__name__, error))
        part = None
    if part is None:
        report["trouble"].append(
            "Open a part and run this again: with nothing open there is no "
            "feature tree to describe, which is most of what this is for.")
        return _write(report)

    report["part"] = {"name": _describe(getattr(part, "Name", None)),
                      "full path": _describe(
                          getattr(part, "FullPath", None)),
                      "units": _describe(getattr(part, "PartUnits", None))}

    # The features, as far as the plugin would need to read them. Only
    # the first few: this is a description of the API, not of the part,
    # and a part with four hundred features would make the report
    # unreadable without saying anything new.
    try:
        features = list(part.Features)
    except Exception as error:
        report["trouble"].append(
            "could not iterate part.Features: %s: %s"
            % (type(error).__name__, error))
        features = []
    report["feature count"] = len(features)
    for feature in features[:8]:
        entry = {}
        for name, why in FEATURE_WANTS:
            entry[name] = {"for": why, **_ask(feature, name)}
        report["features"].append(entry)

    try:
        expressions = list(part.Expressions)
    except Exception as error:
        report["trouble"].append(
            "could not iterate part.Expressions: %s: %s"
            % (type(error).__name__, error))
        expressions = []
    report["expression count"] = len(expressions)
    for expression in expressions[:8]:
        entry = {}
        for name, why in EXPRESSION_WANTS:
            entry[name] = {"for": why, **_ask(expression, name)}
        report["expressions"].append(entry)

    # Editing is the operation everything else rests on, so whether the
    # call exists is worth knowing before anything is built on it. The
    # call is NOT made: this must not change anybody's part.
    try:
        collection = part.Expressions
        report["editing"] = {
            name: {"there": hasattr(collection, name)}
            for name in ("Edit", "EditWithUnits", "EditExpressionWithUnits",
                         "CreateExpression", "Delete")}
    except Exception as error:
        report["trouble"].append(
            "could not look at part.Expressions: %s: %s"
            % (type(error).__name__, error))

    # Whether this NX can reach a server on this machine at all. The
    # plugin works by calling out to one, so a corporate policy that
    # stops it is the thing to find out now rather than later.
    report["can reach localhost"] = _reachable()
    return _write(report)


def _reachable(port=8000):
    """Whether a local server could be called from inside NX.

    Tried against the port the app uses. "Refused" is a good answer: it
    means the network path works and nothing was listening. "Blocked" or
    a timeout is the one that matters, because that is policy.
    """
    import socket
    try:
        with socket.create_connection(("127.0.0.1", port), 2.0):
            return "connected - something is already listening"
    except ConnectionRefusedError:
        return "refused - the path works, nothing was listening (expected)"
    except Exception as error:
        return "%s: %s" % (type(error).__name__, error)


def _write(report):
    where = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "cadsmith-nx-report.json")
    try:
        with open(where, "w") as handle:
            json.dump(report, handle, indent=1, default=str)
    except Exception:
        where = os.path.join(os.path.expanduser("~"),
                             "cadsmith-nx-report.json")
        with open(where, "w") as handle:
            json.dump(report, handle, indent=1, default=str)

    # Printed as well, so it is visible in the Information window even if
    # the file cannot be found afterwards.
    try:
        import NXOpen
        session = NXOpen.Session.GetSession()
        window = session.ListingWindow
        window.Open()
        window.WriteLine("CADSmith NX self-check")
        window.WriteLine("written to: " + where)
        for line in json.dumps(report, indent=1, default=str).splitlines():
            window.WriteLine(line)
    except Exception:
        print("CADSmith NX self-check written to: " + where)
    return where


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
