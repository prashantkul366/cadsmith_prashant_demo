"""Does NX on this machine support what we are building? No network.

Run as an NX journal, with a part open:

    File -> Execute -> NX Open...   and pick this file.

**It makes no network connection of any kind.** No internet, no server,
no AWS, no credentials, nothing sent anywhere. It reads information out
of NX's own API and writes a plain-text report beside this file. By
default it changes nothing in the part.

It answers one question: *if we build a tool that reads and edits an NX
feature tree, will it work on this machine and this release?* That has
three parts, and the report takes them in order.

1. **Is it allowed to run at all?** Journals can be disabled by policy,
   and NX Open can refuse on a licence. If this report exists, the
   answer to the first half is already yes.
2. **Does the API give us what the design needs?** The tool identifies
   features and edits the expressions that drive them. Those property
   names were taken from the NX Open reference without a session to
   confirm them, and some will be wrong on this release. The report says
   which names exist here, which answer, and what they answer with.
3. **Would a change go through?** The methods that edit an expression,
   suppress a feature and rebuild the part are checked for existence,
   and nothing is called. A real no-op write can be switched on below.

The single most important number in the report is how many expressions
carry a **description** - NX's own note saying what each one drives,
like `p7 (Simple Hole(12) Diameter)`. The whole approach rests on it: it
is what lets a tool change a part somebody else modelled years ago
without knowing how it was built. If that number is zero on real parts
here, the design needs rethinking, and it is better to learn that from
this report than from a pilot.
"""

# ---------------------------------------------------------------------
# Set this to True ONLY on a scratch part you do not care about.
#
# It proves the write path end to end by taking one plain numeric
# expression and writing back THE VALUE IT ALREADY HAS, then updating.
# The geometry cannot change - the number is the same - but NX will mark
# the part as modified, so close without saving afterwards. An undo mark
# is set first, so Ctrl+Z also reverses it.
# ---------------------------------------------------------------------
DO_WRITE_TEST = False

import os
import sys
import traceback

LINES = []


def say(text=""):
    LINES.append(str(text))


def head(text):
    say()
    say(text)
    say("-" * len(text))


def mark(ok, label, detail=""):
    say("  [%s] %-44s %s" % ("ok  " if ok else "FAIL", label, detail))


def ask(thing, name):
    """One property or method, without letting a bad one stop the rest.

    Not guarded with hasattr: a .NET property that does not apply to a
    given feature type raises something other than AttributeError when
    it is touched, and that would take the whole report down with it.
    """
    try:
        got = getattr(thing, name)
    except Exception as error:
        return False, "%s: %s" % (type(error).__name__, error)
    if callable(got):
        try:
            got = got()
        except Exception as error:
            return True, "callable, raised %s" % type(error).__name__
    return True, got


def short(value, width=46):
    try:
        text = str(value)
    except Exception:
        return "(unprintable)"
    text = " ".join(text.split())
    return text if len(text) <= width else text[:width - 1] + "…"


FEATURE_WANTS = [
    ("JournalIdentifier", "the stable handle we refer to a feature by"),
    ("Name", "what to call it in the tree"),
    ("FeatureType", "what kind of feature it is"),
    ("Timestamp", "where it sits in the build order"),
    ("Suppressed", "whether it is currently taken out"),
    ("IsSuppressed", "the other spelling of the same thing"),
    ("GetExpressions", "the numbers that drive it"),
]

EXPRESSION_WANTS = [
    ("Name", "p1, p7, and so on"),
    ("Value", "the number"),
    ("Units", "what the number is in"),
    ("Description", "WHICH FEATURE AND PARAMETER IT DRIVES"),
    ("Equation", "the formula, where there is one"),
    ("RightHandSide", "the other spelling of the formula"),
    ("Type", "number, string, point"),
    ("EditLocked", "whether it may be written at all"),
]

#: Checked for existence only. Nothing here is called.
WRITE_PATH = [
    ("work.Expressions", "Edit", "change an expression's value"),
    ("work.Features", "SuppressFeatures", "take a feature out"),
    ("work.Features", "UnsuppressFeatures", "put it back"),
    ("work.Features", "DeleteFeatures", "remove it"),
    ("session", "SetUndoMark", "make the change reversible"),
    ("session.UpdateManager", "DoUpdate", "rebuild the part"),
]


def main():
    say("NX capability check")
    say("===================")
    say("No network connection is made. Nothing is sent anywhere.")
    say("By default nothing in the part is changed.")

    # ---------------------------------------------------------- 1. NX
    head("1. Is it allowed to run here")
    say("  Journal execution: the fact that you are reading this means")
    say("  NX ran a Python journal, so it is permitted on this machine.")
    try:
        import NXOpen
    except Exception as error:
        mark(False, "import NXOpen", "%s: %s" % (type(error).__name__, error))
        say("  Without NX Open there is nothing further to check.")
        return
    mark(True, "import NXOpen")
    try:
        session = NXOpen.Session.GetSession()
    except Exception as error:
        mark(False, "get an NX session",
             "%s: %s" % (type(error).__name__, error))
        say("  This is usually a licence refusal. That is the answer to")
        say("  'can it be integrated here', and it needs Siemens, not us.")
        return
    mark(True, "get an NX session", "no licence refusal")

    for label, name in (("NX version", "UGII_FULL_VERSION"),
                        ("NX release", "UGII_VERSION")):
        try:
            value = session.GetEnvironmentVariableValue(name)
        except Exception:
            value = ""
        if value:
            say("       %-20s %s" % (label, value))
    say("       %-20s %s" % ("Python", sys.version.split()[0]))
    say("       %-20s %s" % ("platform", sys.platform))

    try:
        work = session.Parts.Work
    except Exception as error:
        work = None
        mark(False, "reach the work part",
             "%s: %s" % (type(error).__name__, error))
    if work is None:
        mark(False, "a part is open", "open a part and run this again")
        say()
        say("  Everything below needs a part. Open one - ideally a real")
        say("  one with features and holes, not an empty file - and run")
        say("  this again.")
        return
    mark(True, "a part is open", short(ask(work, "FullPath")[1]))

    # -------------------------------------------------- 2. reading it
    head("2. Can we read the feature tree")
    features = []
    try:
        features = list(work.Features)
        mark(True, "read the feature list", "%d features" % len(features))
    except Exception as error:
        mark(False, "read the feature list",
             "%s: %s" % (type(error).__name__, error))

    if features:
        say()
        say("  Which properties a feature actually has on this release:")
        sample = features[0]
        for name, why in FEATURE_WANTS:
            exists, value = ask(sample, name)
            if exists:
                mark(True, name, "%s  (%s)" % (short(value, 28), why))
            else:
                mark(False, name, "not available  (%s)" % why)
        say()
        say("  The first few features as the tool would see them:")
        for one in features[:8]:
            ident = ask(one, "JournalIdentifier")[1] or ask(one, "Name")[1]
            kind = ask(one, "FeatureType")[1]
            say("       %-28s %s" % (short(ident, 28), short(kind, 24)))
        if len(features) > 8:
            say("       ... and %d more" % (len(features) - 8))

    head("3. Can we read the expressions that drive it")
    expressions = []
    try:
        expressions = list(work.Expressions)
        mark(True, "read the expression list",
             "%d expressions" % len(expressions))
    except Exception as error:
        mark(False, "read the expression list",
             "%s: %s" % (type(error).__name__, error))

    described = 0
    numeric = []
    if expressions:
        say()
        say("  Which properties an expression actually has here:")
        for name, why in EXPRESSION_WANTS:
            exists, value = ask(expressions[0], name)
            if exists:
                mark(True, name, "%s  (%s)" % (short(value, 24), why))
            else:
                mark(False, name, "not available  (%s)" % why)

        for one in expressions:
            text = ask(one, "Description")[1]
            if text and str(text).strip():
                described += 1
            formula = str(ask(one, "Equation")[1] or "")
            value = ask(one, "Value")[1]
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            name = str(ask(one, "Name")[1] or "")
            if name and formula.strip() in ("", str(value), "%g" % number):
                numeric.append((one, name, number))

        say()
        say("  THE NUMBER THAT MATTERS")
        pct = (100.0 * described / len(expressions)) if expressions else 0
        mark(described > 0,
             "expressions that say what they drive",
             "%d of %d  (%.0f%%)" % (described, len(expressions), pct))
        if described:
            say()
            say("  Examples - this is what lets the tool work on a part it")
            say("  did not build:")
            shown = 0
            for one in expressions:
                text = ask(one, "Description")[1]
                if text and str(text).strip():
                    say("       %-10s = %-12s %s"
                        % (short(ask(one, "Name")[1], 10),
                           short(ask(one, "Value")[1], 12), short(text, 44)))
                    shown += 1
                    if shown >= 6:
                        break
        else:
            say()
            say("  None of the expressions on this part say what they")
            say("  drive. Either this part was built in a way that does")
            say("  not record it, or this release names the property")
            say("  differently. Try a part with holes and patterns before")
            say("  concluding anything - and send this report either way.")

        say()
        mark(len(numeric) > 0, "plain numbers we could safely edit",
             "%d of %d (the rest are formula-driven or not numeric)"
             % (len(numeric), len(expressions)))
        say("       A formula-driven expression is deliberately refused by")
        say("       the tool rather than overwritten, so this count is the")
        say("       part of the tree it would actually offer to change.")

    # ----------------------------------------------- 4. the write path
    head("4. Would a change go through")
    say("  Checked for existence only. Nothing here is called.")
    scope = {"session": session, "session.UpdateManager": None,
             "work.Expressions": None, "work.Features": None}
    try:
        scope["session.UpdateManager"] = session.UpdateManager
    except Exception:
        pass
    try:
        scope["work.Expressions"] = work.Expressions
    except Exception:
        pass
    try:
        scope["work.Features"] = work.Features
    except Exception:
        pass
    for owner, method, why in WRITE_PATH:
        holder = scope.get(owner)
        if holder is None:
            mark(False, "%s.%s" % (owner, method), "%s is unavailable" % owner)
            continue
        try:
            found = callable(getattr(holder, method))
        except Exception:
            found = False
        mark(found, "%s.%s" % (owner, method), why)

    # ------------------------------------------- 5. optional live test
    head("5. A real no-op write")
    if not DO_WRITE_TEST:
        say("  Skipped. Nothing in the part was changed.")
        say()
        say("  To run it, open a SCRATCH part, set DO_WRITE_TEST = True at")
        say("  the top of this file and run it again. It writes one")
        say("  expression back to the value it already has, so the")
        say("  geometry cannot change, and it sets an undo mark first.")
        say("  Close without saving afterwards.")
    elif not numeric:
        say("  Skipped: this part has no plain numeric expression to use.")
    else:
        one, name, value = numeric[0]
        say("  Using %s, currently %g. Writing the same value back." %
            (name, value))
        try:
            session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                                "nxcheck no-op")
            mark(True, "set an undo mark")
        except Exception as error:
            mark(False, "set an undo mark",
                 "%s: %s" % (type(error).__name__, error))
        try:
            work.Expressions.Edit(one, "%s=%.10g" % (name, value))
            mark(True, "edit the expression")
        except Exception as error:
            mark(False, "edit the expression",
                 "%s: %s" % (type(error).__name__, error))
        try:
            session.UpdateManager.DoUpdate(
                session.SetUndoMark(NXOpen.Session.MarkVisibility.Visible,
                                    "nxcheck update"))
            mark(True, "rebuild the part")
        except Exception as error:
            mark(False, "rebuild the part",
                 "%s: %s" % (type(error).__name__, error))
        after = ask(one, "Value")[1]
        try:
            back = abs(float(after) - value) < 1e-9
        except (TypeError, ValueError):
            back = False
        mark(back, "read the value back unchanged", short(after, 20))
        say()
        say("  The part is now marked modified even though nothing moved.")
        say("  Close it without saving.")

    # ---------------------------------------------------- 6. verdict
    head("Verdict")
    failures = [l for l in LINES if l.startswith("  [FAIL]")]
    blocking = [l for l in failures
                if "not available" not in l and "other spelling" not in l]
    if not failures:
        say("  Everything checked out. The approach works on this machine.")
    elif not blocking:
        say("  Nothing blocking. Some property names are spelled")
        say("  differently on this release - that is exactly what this")
        say("  report is for, and it is a small correction, not a")
        say("  redesign.")
    else:
        say("  %d thing(s) need attention:" % len(blocking))
        for line in blocking:
            say("   " + line.strip())
    say()
    say("  Send this whole report back. The property names and the")
    say("  description count are what the tool gets corrected against.")


try:
    main()
except Exception:
    LINES.append("")
    LINES.append("The check itself failed. That is useful too:")
    LINES.extend(traceback.format_exc().splitlines())

report = "\n".join(LINES)
try:
    import NXOpen
    window = NXOpen.Session.GetSession().ListingWindow
    window.Open()
    for line in LINES:
        window.WriteLine(line)
except Exception:
    pass
try:
    sys.stdout.write(report + "\n")
except Exception:
    pass
try:
    where = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "nxcheck-report.txt")
    with open(where, "w") as handle:
        handle.write(report + "\n")
    try:
        NXOpen.Session.GetSession().ListingWindow.WriteLine(
            "\nreport written to: " + where)
    except Exception:
        print("\nreport written to: " + where)
except Exception:
    pass
