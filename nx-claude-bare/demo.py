"""What a run looks like, with no NX and no AWS. Run: python demo.py

Everything here is the real code except two things: the NX session is a
stand-in, and the model's replies are scripted instead of coming from
Bedrock. The conversation loop, the preview, the approval gate and the
whole of `nxside` are exactly what runs on the engineer's machine.

The stand-in part is modelled on the one NX v2412.0.0.5001 actually
reported back - the same features, the same expression names, the same
descriptions, and the same awkward details: `Equation` carrying the
whole equation rather than the right-hand side, `Units` answering with
an object rather than text, and no `DeleteFeatures` on the feature
collection.

Use it to show somebody what the tool does before taking it near a real
part, or to try a change to the loop without booking time on an NX seat.
"""

import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)


# ------------------------------------------------------------------
# a stand-in NX, shaped like the machine that sent the report
# ------------------------------------------------------------------

class _Unit(object):
    Abbreviation = "mm"

    def __repr__(self):
        return "<NXOpen.Unit object at 0x000001F4>"


class _Expr(object):
    def __init__(self, name, value, describes="", rhs=None):
        self.Name = name
        self.Value = value
        self.Units = _Unit()
        self.Description = describes
        self._rhs = ("%g" % value) if rhs is None else rhs
        self.Type = "Number"

    @property
    def Equation(self):            # 2412 returns the WHOLE equation
        return "%s=%s" % (self.Name, self._rhs)

    @property
    def RightHandSide(self):
        return self._rhs

    @property
    def EditLocked(self):          # absent on 2412
        raise AttributeError("no such property on this release")


class _Feature(object):
    def __init__(self, ident, kind, when):
        self.JournalIdentifier = ident
        self.Name = ""
        self.FeatureType = kind
        self.Timestamp = when
        self.Suppressed = False

    @property
    def IsSuppressed(self):        # absent on 2412
        raise AttributeError("no such property on this release")

    def GetExpressions(self):
        return []


class _Expressions(list):
    def Edit(self, expression, text):
        _, _, value = text.partition("=")
        expression.Value = float(value)
        expression._rhs = "%g" % expression.Value


class _Features(list):
    def SuppressFeatures(self, which):
        for one in which:
            one.Suppressed = True

    def UnsuppressFeatures(self, which):
        for one in which:
            one.Suppressed = False
    # no DeleteFeatures, exactly as reported


class _Part(object):
    FullPath = r"E:\TestNX\Sample.prt"
    Name = "Sample"

    def __init__(self):
        self.Features = _Features([
            _Feature("DATUM_CSYS(0)", "DATUM_CSYS", 0),
            _Feature("SKETCH(1:1B)", "DATUM_CSYS", 1),
            _Feature("SKETCH(1)", "SKETCH", 2),
            _Feature("EXTRUDE(2)", "EXTRUDE", 3),
            _Feature("BLEND(3)", "BLEND", 4),
            _Feature("SIMPLE HOLE(4)", "HOLE PACKAGE", 5),
            _Feature("SIMPLE HOLE(4:1A)", "SIMPLE HOLE", 6),
        ])
        self.Expressions = _Expressions([
            _Expr("p0", 0.0, "(Extrude(2) Start Limit)"),
            _Expr("p1", 215.0, "(Extrude(2) End Limit)"),
            _Expr("p9", 10.0, "(Edge Blend(3) Radius 1)"),
            _Expr("p58", 50.0, "(\u00d850 Hole(4) Diameter)"),
            _Expr("p62", 295.0, "(\u00d850 Hole(4) Depth)"),
            _Expr("p67", 118.0, "(\u00d850 Hole(4) Tip Angle)"),
            _Expr("p2", 120.0),          # sketch dimensions carry no
            _Expr("p3", 80.0),           # description, as on the real
            _Expr("p4", 40.0),           # part
            _Expr("p5", 25.0),
        ])


class _Window(object):
    def Open(self):
        pass

    def WriteLine(self, text):
        pass


class _Update(object):
    def DoUpdate(self, marker):
        return 0

    def AddToDeleteList(self, objects):
        pass


def _install_stand_in():
    """Put a fake NXOpen where `import NXOpen` will find it."""
    NXOpen = types.ModuleType("NXOpen")

    class Session(object):
        _one = None

        class MarkVisibility(object):
            Visible = 1

        def __init__(self):
            self.Parts = types.SimpleNamespace(Work=_Part(), Display=None)
            self.ListingWindow = _Window()
            self.UpdateManager = _Update()

        @staticmethod
        def GetSession():
            if Session._one is None:
                Session._one = Session()
            return Session._one

        def SetUndoMark(self, visibility, why):
            return object()

        def GetEnvironmentVariableValue(self, name):
            return {"UGII_FULL_VERSION": "v2412.0.0.5001"}.get(name, "")

    NXOpen.Session = Session
    sys.modules["NXOpen"] = NXOpen


# ------------------------------------------------------------------
# a scripted stand-in for the model
# ------------------------------------------------------------------

def _use(*calls):
    """One assistant turn asking for one or more operations.

    Several in one turn is the realistic case, and it is the one worth
    showing: the whole set is previewed and approved together, not one
    dialog per operation.
    """
    return {"content": [{"type": "tool_use", "id": identifier,
                         "name": name, "input": arguments}
                        for identifier, name, arguments in calls],
            "stop_reason": "tool_use"}


def _say(text):
    return {"content": [{"type": "text", "text": text}],
            "stop_reason": "end_turn"}


SCRIPTS = {
    "read": ("Read the feature tree and tell me what this part is.", [
        _use(("1", "read_tree", {})),
        _say("This is a single modelled solid, built in four steps: a "
             "sketch, extruded 215 mm (p1), an edge blend of 10 mm (p9), "
             "and a \u00d850 hole 295 mm deep (p58, p62) with a 118\u00b0 "
             "tip angle (p67).\n\nFour more expressions - p2 to p5 - carry "
             "no description, so they are almost certainly the sketch "
             "dimensions that set the outline. I can change them by name "
             "but cannot tell you which is which from here."),
    ]),
    "hole": ("The hole needs to clear an M12 bolt with a little room. "
             "Change it and tell me what you did.", [
        _use(("1", "read_tree", {})),
        _use(("2", "set_expression", {"name": "p58", "value": 13.0})),
        _say("Done. p58 \u2014 the \u00d850 hole's diameter \u2014 is now "
             "13 mm. An M12 bolt needs 13 mm for a normal-fit clearance "
             "hole (ISO 273 medium), so that is 1 mm of room on the "
             "diameter.\n\nI left the depth (p62, 295 mm) and the tip "
             "angle (p67, 118\u00b0) alone, since neither follows from the "
             "bolt size. Note the feature is still named 'Ø50 Hole(4)' in "
             "the tree \u2014 NX keeps the name it was created with."),
    ]),
    "refused": ("Delete the blend and make the part 400 long.", [
        _use(("1", "read_tree", {})),
        _use(("2", "set_expression", {"name": "p1", "value": 400.0}),
             ("3", "delete_feature", {"name": "BLEND(3)"})),
        _say("Understood \u2014 I have left the part as it was."),
    ]),
}


def main():
    want = (sys.argv[1] if len(sys.argv) > 1 else "hole").lower()
    if want not in SCRIPTS:
        print("usage: python demo.py [%s]" % " | ".join(SCRIPTS))
        return 2
    prompt, replies = SCRIPTS[want]

    _install_stand_in()
    import bare
    import nxside

    if want == "refused":
        nxside.approve = lambda plan: False          # the engineer says no
    else:
        nxside.approve = lambda plan: True           # the engineer says yes

    print("=" * 68)
    print("  A simulated run. The NX session and the model's replies are")
    print("  stand-ins; the loop, the preview and nxside are the real")
    print("  code. This is what appears in NX's Information window.")
    print("=" * 68)

    said = list(replies)

    def ask(messages, tools=None, system=None, max_tokens=4096):
        return said.pop(0) if said else _say("(nothing further)")

    lines = []

    def note(line):
        # The stand-in window is the only printer here, so the
        # transcript is not doubled on screen.
        lines.append(str(line))
        print("   NX \u2502 " + str(line).replace("\n", "\n   NX \u2502 "))

    note("model anthropic.claude-sonnet-5 in us-east-1")
    bare.conversation(nxside, ask, prompt, note=note)
    print("=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
