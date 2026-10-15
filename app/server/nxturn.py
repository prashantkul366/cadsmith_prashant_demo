"""One turn of the conversation with an engineer working in NX.

The plugin inside NX starts a turn: here is what the engineer typed,
here is the part's feature tree, here is what happened to the operations
from last time. This answers with the operations to perform next, or
with a sentence and nothing to do.

Why a turn rather than a loop. On the FreeCAD road the server drives the
CAD and the agent loop runs here from start to finish. In NX the plugin
drives, because NX Open must be called on NX's own thread - so the loop
is split across HTTP calls, and the conversation is carried in the
request rather than held in memory. That also means a turn is a pure
function of what it is given, which is why it can be tested with no NX
and no model.

Nothing here performs anything. Every operation it returns has been
checked by :mod:`nxtools` first, so an operation that cannot work is
refused before it reaches somebody's part rather than after.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from app.server import nxtools

#: How many operations one turn may ask for. A turn is a round trip
#: through NX, so this is not about cost - it is that a model which has
#: just been handed a tree should look at what its first few changes did
#: before deciding on twenty more.
MAX_OPERATIONS = 8

SYSTEM = """\
You are changing a part in Siemens NX for the engineer who owns it.

You are not building a model from nothing. The part is already there -
somebody designed it, possibly years ago, and you are being asked to
change it. Read the feature tree you are given before you touch it.

How a part is changed:

* To change a size, edit the expression that drives it. NX names them
  p1, p7, p9 and says what each one drives: "p7 (Simple Hole(12)
  Diameter)". Find the one that means what the engineer asked about and
  set it. You do not need to know how the part was built.
* To add material or cut it, use sketch_extrude. To put a hole in, use
  hole - it is an NX Hole feature and carries its thread, counterbore
  and depth into the drawing. Never model a hole as a subtracted solid.
* An expression driven by a formula will be refused, and it should be:
  writing a number over "wall/2" destroys a relation the designer put
  there on purpose. If that is what the engineer wants, say so and ask.

Say what you are about to do in one short sentence, in the engineer's
own terms - "opening the four mounting holes to 11" - then ask for the
operations. Every operation takes an `intent` saying what it is for.

If the request is ambiguous in a way that changes the part, ask instead
of guessing. A wrong change to somebody's production part costs more
than a question.

When the part is as asked, say so and ask for nothing.
"""


def task(prompt: str, tree: nxtools.Tree, results: Optional[list] = None,
         asked_before: Optional[list] = None) -> str:
    """What the model is told at the start of a turn."""
    parts = [f"The engineer says:\n{prompt.strip()}\n",
             "The part as it is now:\n" + tree.summary()]
    if asked_before:
        parts.append("Last turn you asked for:\n" + "\n".join(
            f"  {one}" for one in asked_before))
    if results:
        done = []
        for one in results:
            name = one.get("name", "?")
            if one.get("ok"):
                done.append(f"  {name}: done. {one.get('detail', '')}".rstrip())
            else:
                done.append(f"  {name}: NX refused it. "
                            f"{one.get('why', 'no reason given')}")
        parts.append("What happened:\n" + "\n".join(done))
    return "\n\n".join(parts)


def definitions() -> list:
    """The operations, as tool definitions for the model."""
    out = []
    for entry in nxtools.definitions():
        out.append({
            "name": entry["name"],
            "description": entry["description"],
            # Deliberately loose: the real checking is nxtools.checked,
            # which knows the part. A schema cannot know that p9 is
            # driven by a formula, and two places that both half-check
            # disagree eventually.
            "input_schema": {
                "type": "object",
                "properties": {
                    "intent": {"type": "string",
                               "description": "what this is for, in the "
                                              "engineer's terms"}},
                "additionalProperties": True},
        })
    return out


def answer(reply: Any, tree: nxtools.Tree) -> dict:
    """What the model said, turned into a turn's answer.

    Operations that will not work are refused here and reported back as
    refusals rather than sent to NX. The plugin performs what is
    returned and posts the results, which become the next turn's "what
    happened".
    """
    said = "".join(getattr(block, "text", "")
                   for block in (getattr(reply, "content", None) or []))
    calls = list(getattr(reply, "tool_calls", None) or [])

    operations, refused = [], []
    for call in calls[:MAX_OPERATIONS]:
        name = getattr(call, "name", "") or ""
        arguments = getattr(call, "input", None)
        if arguments is None:
            arguments = getattr(call, "arguments", None) or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                refused.append({"name": name,
                                "why": "the arguments were not JSON"})
                continue
        try:
            operations.append(nxtools.checked(name, arguments, tree))
        except nxtools.NXToolError as error:
            refused.append({"name": name, "why": str(error)})

    over = len(calls) - MAX_OPERATIONS
    if over > 0:
        refused.append({
            "name": "(too many at once)",
            "why": f"{len(calls)} operations were asked for and the first "
                   f"{MAX_OPERATIONS} were taken. Look at what those did "
                   "before asking for the rest."})

    return {
        "say": said.strip(),
        "operations": [one.as_json() for one in operations],
        "refused": refused,
        # Nothing to do and nothing refused means the model has finished
        # or is asking a question. Either way the plugin stops and shows
        # what it said.
        "done": not operations and not refused,
    }


def turn(client: Any, model: str, prompt: str, raw_tree: dict,
         results: Optional[list] = None, asked_before: Optional[list] = None,
         max_tokens: int = 1500) -> dict:
    """One exchange: the part and the request in, operations out."""
    tree = nxtools.tree_from(raw_tree or {})
    reply = client.messages.create(
        model=model, max_tokens=max_tokens, system=SYSTEM,
        messages=[{"role": "user",
                   "content": task(prompt, tree, results, asked_before)}],
        tools=definitions())
    out = answer(reply, tree)
    usage = getattr(reply, "usage", None)
    out["usage"] = {
        "input_tokens": getattr(usage, "input_tokens", 0),
        "output_tokens": getattr(usage, "output_tokens", 0),
    }
    return out
