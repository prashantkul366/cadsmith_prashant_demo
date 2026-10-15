"""A turn of the NX conversation, with no NX and no model.

A turn is a pure function of what it is handed - the request, the tree,
and what happened last time - which is the whole reason the plugin
drives and the server answers. So it can be tested completely here, and
the only thing left unproven is NX itself.

Run:  .venv/bin/python -m app.tests.test_nxturn
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.server import nxturn, nxtools  # noqa: E402

PART = {
    "part": "bracket",
    "features": [
        {"name": "Extrude(1)", "kind": "Extrude", "timestamp": 1,
         "expressions": [{"name": "p1", "value": 25.0,
                          "description": "p1 (Extrude(1) Limit End)"}]},
        {"name": "Simple Hole(12)", "kind": "Hole", "timestamp": 2,
         "expressions": [{"name": "p7", "value": 13.0,
                          "description": "p7 (Simple Hole(12) Diameter)"}]},
    ],
    "expressions": [
        {"name": "p1", "value": 25.0, "description": "p1 (Extrude(1) Limit End)"},
        {"name": "p7", "value": 13.0,
         "description": "p7 (Simple Hole(12) Diameter)"},
        {"name": "p9", "value": 5.0, "description": "p9 (Edge Blend(3) Radius)",
         "formula": "wall/2"},
    ],
}


class Call:
    def __init__(self, name, arguments):
        self.name, self.input = name, arguments


class Block:
    def __init__(self, text):
        self.text = text


class Usage:
    input_tokens, output_tokens = 900, 120


class Reply:
    def __init__(self, text, calls=()):
        self.content = [Block(text)]
        self.tool_calls = list(calls)
        self.usage = Usage()


class Model:
    """A model that says what the test tells it to, and records the ask."""

    def __init__(self, reply):
        self._reply = reply
        self.system = ""
        self.task = ""
        self.tools = []
        self.messages = self

    def create(self, model, max_tokens, system, messages, tools):
        self.system = system
        self.task = messages[0]["content"]
        self.tools = tools
        return self._reply


def main() -> int:
    failures = 0

    def check(what: str, ok: bool, saw: str = "") -> None:
        nonlocal failures
        if not ok:
            failures += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {what}"
              + (f" - {saw}" if saw else ""))

    print("What the model is told")
    model = Model(Reply("Opening the mounting holes to 11.",
                        [Call("edit_expression",
                              {"name": "p7", "value": 11.0,
                               "intent": "open the mounting holes"})]))
    out = nxturn.turn(model, "m", "open the mounting holes to 11", PART)
    check("the part is described before anything is asked of it",
          "Simple Hole(12)" in model.task and "p7=13" in model.task,
          [l for l in model.task.splitlines() if "Hole" in l])
    check("and the engineer's words are passed through",
          "open the mounting holes to 11" in model.task, "")
    check("every operation is offered",
          {t["name"] for t in model.tools} == set(nxtools.OPERATIONS),
          str(sorted(t["name"] for t in model.tools)))

    print("\nWhat comes back")
    check("the operation is checked and passed on",
          out["operations"] == [{"name": "edit_expression",
                                 "arguments": {"name": "p7", "value": 11.0},
                                 "intent": "open the mounting holes"}],
          str(out["operations"]))
    check("with what it said, for the engineer to read",
          out["say"] == "Opening the mounting holes to 11.", out["say"])
    check("and the turn is not finished",
          out["done"] is False, str(out["done"]))

    print("\nWhat never reaches the part")
    # The model asking for something impossible must cost a turn, not a
    # part. This is the whole reason the check is on this side.
    bad = Model(Reply("Setting the blend.",
                      [Call("edit_expression", {"name": "p9", "value": 3.0}),
                       Call("hole", {"diameter": 0, "depth": 5})]))
    out = nxturn.turn(bad, "m", "make the blend 3", PART)
    check("an expression driven by a formula is refused here",
          any("wall/2" in one["why"] for one in out["refused"]),
          str(out["refused"])[:90])
    check("and so is a hole of no size",
          any("greater than zero" in one["why"] for one in out["refused"]),
          "")
    check("nothing is sent to NX when everything was refused",
          out["operations"] == [], str(out["operations"]))
    check("but the turn is not called finished - there is work to redo",
          out["done"] is False, str(out["done"]))

    print("\nSaying it is done")
    finished = Model(Reply("The holes are 11 now. Nothing else to change."))
    out = nxturn.turn(finished, "m", "thanks", PART)
    check("no operations and no refusals ends the turn",
          out["done"] is True and not out["operations"], str(out))

    print("\nToo much at once")
    many = Model(Reply("Doing it all.",
                       [Call("edit_expression", {"name": "p7", "value": 11.0})
                        for _ in range(12)]))
    out = nxturn.turn(many, "m", "change everything", PART)
    check("a turn is capped at what can be looked at afterwards",
          len(out["operations"]) == nxturn.MAX_OPERATIONS,
          str(len(out["operations"])))
    check("and the model is told the rest were not taken",
          any("too many" in one["name"] for one in out["refused"]),
          str(out["refused"])[:80])

    print("\nThe next turn knows what happened")
    tree = nxtools.tree_from(PART)
    told = nxturn.task(
        "and the other two", tree,
        results=[{"name": "edit_expression", "ok": True, "detail": "p7 = 11"},
                 {"name": "hole", "ok": False,
                  "why": "the face was not found"}],
        asked_before=["edit_expression p7=11", "hole at (0,0,0)"])
    check("what worked is reported back",
          "p7 = 11" in told, "")
    check("and what NX refused, with NX's reason",
          "the face was not found" in told, "")

    print("\nArguments that are not what they should be")
    # A model can return its arguments as a JSON string rather than an
    # object, and a plugin should never be handed the difference.
    stringy = Model(Reply("", [Call("edit_expression",
                                    '{"name": "p7", "value": 12}')]))
    out = nxturn.turn(stringy, "m", "twelve", PART)
    check("a JSON string of arguments is understood",
          out["operations"] and out["operations"][0]["arguments"]["value"] == 12.0,
          str(out["operations"]))
    broken = Model(Reply("", [Call("edit_expression", "{not json")]))
    out = nxturn.turn(broken, "m", "twelve", PART)
    check("and one that is not JSON at all is refused, not crashed on",
          out["refused"] and "JSON" in out["refused"][0]["why"],
          str(out["refused"]))

    print("\n" + "=" * 58)
    print("ALL CHECKS PASSED" if not failures else f"{failures} CHECK(S) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
