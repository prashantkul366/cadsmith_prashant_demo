"""Let a model build a part one step at a time, and measure every step.

The pipeline this app was built on asks a model for a whole CadQuery script,
runs it, judges the result, and on a failure asks for the whole script again.
Measured here: about 1,200 output tokens a call, five calls, sixty to ninety
seconds, and a full rewrite thrown away each time the Judge says no.

A tool call is forty tokens. Six of them is less generation than a fifth of
one of those scripts, the conversation prefix caches between them, and a
wrong step costs one step rather than the lot. That difference is why
driving a CAD through tool calls feels immediate and driving it through
script generation does not.

Two things make this worth more than speed.

**Every result carries numbers.** A tool here does not answer "ok"; it
answers with what it measured - the bounding box, the volume, the hole it
actually made. The model corrects itself at step two instead of failing at
step eight, and the correction costs one short call.

**Nothing invented gets run.** A name or an argument the toolbox does not
recognise is refused before the tool is reached, and the refusal names what
does exist. A model is allowed to be wrong; it is not allowed to be wrong
quietly.

**A model with no tool channel still works.** A small model served by a
vLLM started without ``--enable-auto-tool-choice`` has nowhere to put a
tool call, so the tools go into its prompt and it answers in JSON. Measured
on an 8B earlier in this project: hopeless at writing a whole script,
five out of five at choosing which of ten things to do, and thirty-seven
tokens to say it. That is the shape of a tool call, which is the reason to
keep the road open - it is what lets this run on hardware you own.
"""

from __future__ import annotations

import difflib

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

#: Enough for a part of a dozen features, short enough that a model talking
#: to itself stops costing money.
MAX_STEPS = 24

#: What a tool returns is fed back into the conversation, so a tool that
#: answers with a megabyte of mesh would blow the context on one call.
MAX_RESULT_CHARS = 4000

#: How many times a model that wrote out a call instead of making one is
#: told so before the run gives up on it. Two, because the first reminder
#: fixes it or nothing will, and a third is just money.
MAX_NUDGES = 2

#: How many times the same call may fail the same way before the loop stops.
#: Measured on an 8B against a solid with no parametric tree: nineteen
#: set_size calls, every one refused with the same sentence, fifty-nine
#: seconds and the whole step budget. A model that is going to recover does
#: it on the second try.
REPEAT_LIMIT = 3

NOT_A_CALL = (
    "You did not call a tool - you wrote one out as text. Nothing was built. "
    "Use the tool-calling channel: emit a call, not a description of one. If "
    "your reply cannot carry a tool call, answer with JSON on its own and "
    "nothing else: {\"tool\": \"<name>\", \"arguments\": {...}}"
)


#: Names a model reaches for when it is writing FreeCAD or CadQuery from
#: memory instead of calling what it was offered, and the tool each one
#: means. Measured on an 8B against this toolbox: asked for a 25 mm cube it
#: answered ``Part.makeBox(25, 25, 25)``, was told three times that no such
#: tool exists, and the run ended with an empty document and a cheerful
#: summary. The intent was never in doubt - only the name - so the name is
#: translated and the call goes through.
#:
#: The second element is what the name itself says that the arguments do
#: not: ``makeBox`` names the primitive, so ``kind`` need not be asked for
#: again. Anything the model did pass wins over it.
ALIASES: dict[str, tuple[str, dict]] = {
    "box": ("add_shape", {"kind": "Part::Box"}),
    "cube": ("add_shape", {"kind": "Part::Box"}),
    "add_box": ("add_shape", {"kind": "Part::Box"}),
    "make_box": ("add_shape", {"kind": "Part::Box"}),
    "makebox": ("add_shape", {"kind": "Part::Box"}),
    "part.makebox": ("add_shape", {"kind": "Part::Box"}),
    "cylinder": ("add_shape", {"kind": "Part::Cylinder"}),
    "add_cylinder": ("add_shape", {"kind": "Part::Cylinder"}),
    "make_cylinder": ("add_shape", {"kind": "Part::Cylinder"}),
    "makecylinder": ("add_shape", {"kind": "Part::Cylinder"}),
    "part.makecylinder": ("add_shape", {"kind": "Part::Cylinder"}),
    "sphere": ("add_shape", {"kind": "Part::Sphere"}),
    "makesphere": ("add_shape", {"kind": "Part::Sphere"}),
    "part.makesphere": ("add_shape", {"kind": "Part::Sphere"}),
    "cone": ("add_shape", {"kind": "Part::Cone"}),
    "makecone": ("add_shape", {"kind": "Part::Cone"}),
    "part.makecone": ("add_shape", {"kind": "Part::Cone"}),
    "torus": ("add_shape", {"kind": "Part::Torus"}),
    "maketorus": ("add_shape", {"kind": "Part::Torus"}),
    "part.maketorus": ("add_shape", {"kind": "Part::Torus"}),
    "add_primitive": ("add_shape", {}),
    "create_shape": ("add_shape", {}),
    "primitive": ("add_shape", {}),
    "hole": ("drill", {}),
    "add_hole": ("drill", {}),
    "make_hole": ("drill", {}),
    "cut_hole": ("drill", {}),
    "cut": ("combine", {"operation": "cut"}),
    "part.cut": ("combine", {"operation": "cut"}),
    "subtract": ("combine", {"operation": "cut"}),
    "difference": ("combine", {"operation": "cut"}),
    "fuse": ("combine", {"operation": "union"}),
    "part.fuse": ("combine", {"operation": "union"}),
    "union": ("combine", {"operation": "union"}),
    "boolean": ("combine", {}),
    "common": ("combine", {"operation": "intersect"}),
    "intersect": ("combine", {"operation": "intersect"}),
    "pad": ("extrude_profile", {}),
    "extrude": ("extrude_profile", {}),
    "pocket": ("extrude_profile", {}),
    "sketch": ("extrude_profile", {}),
    "revolve": ("revolve_profile", {}),
    "fillet": ("add_fillet", {}),
    "round": ("add_fillet", {}),
    "fillet_edges": ("add_fillet", {}),
    "edge_fillet": ("add_fillet", {}),
    "round_edges": ("add_fillet", {}),
    "chamfer": ("add_chamfer", {}),
    "chamfer_edges": ("add_chamfer", {}),
    "edge_chamfer": ("add_chamfer", {}),
    "break_edges": ("add_chamfer", {}),
    "polar_pattern": ("pattern_circular", {}),
    "array_polar": ("pattern_circular", {}),
    "circular_pattern": ("pattern_circular", {}),
    "linear_pattern": ("pattern_linear", {}),
    "array": ("pattern_linear", {}),
    "set_parameter": ("declare_parameter", {}),
    "add_parameter": ("declare_parameter", {}),
    "material": ("set_material", {}),
    "thickness": ("shell", {}),
    "hollow": ("shell", {}),
    "translate": ("move", {}),
    "delete": ("remove_object", {}),
    "remove": ("remove_object", {}),
    "python": ("run_python", {}),
    "execute": ("run_python", {}),
}

#: Argument names from the same remembered vocabularies, per tool. Per
#: tool because they collide: ``position`` is what add_shape and move
#: really call it, and what drill calls ``at``. Only ever a rename onto a
#: property that tool declares, and never over something the model already
#: said properly - and the table is walked against the live toolbox by a
#: test, so an entry that stops being true fails rather than silently
#: dropping an argument.
ARGUMENT_ALIASES: dict[str, dict[str, str]] = {
    "drill": {"position": "at", "location": "at", "centre": "at",
              "center": "at", "point": "at", "xyz": "at",
              "direction": "axis", "normal": "axis", "along": "axis",
              "name": "target", "object": "target", "solid": "target",
              "part": "target", "base": "target",
              "dia": "diameter", "size": "diameter",
              "tapped": "thread", "thread_size": "thread",
              "clearance": "clearance_for"},
    "add_chamfer": {"edges": "where", "edge": "where", "which": "where",
                    "target": "where", "distance": "size", "length": "size",
                    "depth": "size", "chamfer": "size"},
    "add_fillet": {"edges": "where", "edge": "where", "which": "where",
                   "target": "where", "size": "radius", "r": "radius",
                   "fillet": "radius"},
    "combine": {"how": "operation", "op": "operation", "kind": "operation",
                "target": "base", "tool": "tools", "others": "tools"},
    "extrude_profile": {"profile": "points", "outline": "points",
                        "vertices": "points", "path": "points",
                        "height": "depth", "thickness": "depth",
                        "length": "depth", "distance": "depth",
                        "workplane": "plane",
                        "corner_radius": "fillet", "radius": "fillet",
                        "corners": "fillet"},
    "revolve_profile": {"profile": "points", "outline": "points",
                        "vertices": "points", "degrees": "angle",
                        "workplane": "plane"},
    "move": {"to": "position", "at": "position", "location": "position",
             "translation": "position", "offset": "position",
             "target": "name", "object": "name"},
    "rotate": {"angle": "degrees", "about": "axis", "around": "axis",
               "target": "name", "object": "name"},
    "set_size": {"target": "name", "object": "name"},
    "shell": {"target": "name", "object": "name", "wall": "thickness",
              "wall_thickness": "thickness", "open": "open_face"},
    "pattern_circular": {"target": "name", "object": "name",
                         "number": "count", "copies": "count",
                         "center": "centre", "about": "axis",
                         "total_angle": "angle"},
    "pattern_linear": {"target": "name", "object": "name",
                       "number": "count", "copies": "count",
                       "step": "spacing", "pitch": "spacing"},
    "loft": {"profiles": "sections", "outlines": "sections"},
    "resize_hole": {"feature": "feature_id", "id": "feature_id",
                    "dia": "diameter", "size": "diameter"},
    "place_standard_part": {"part": "description", "what": "description",
                            "at": "position"},
    "set_material": {"material": "name", "to": "name"},
    "add_shape": {"shape": "kind", "type": "kind", "primitive": "kind",
                  "at": "position", "location": "position",
                  # Part.makeBox takes its sides positionally, so a model
                  # naming them reaches for the property editor's labels.
                  "xsize": "Length", "ysize": "Width", "zsize": "Height",
                  "dx": "Length", "dy": "Width", "dz": "Height",
                  "depth": "Width", "side": "Length"},
    "run_python": {"script": "code", "source": "code", "python": "code"},
}


class ToolError(Exception):
    """The tool ran and could not do it.

    Distinct from the toolbox refusing a call: this is the kernel saying no,
    and the model should see it and try something else rather than the run
    ending.
    """


@dataclass
class Tool:
    """One thing a model may do, and the only way it may do it."""
    name: str
    description: str
    parameters: dict
    run: Callable[..., Any]

    def definition(self) -> dict:
        return {"name": self.name, "description": self.description,
                "parameters": self.parameters}


@dataclass
class Step:
    """One call and what came back, for the transcript and for the UI."""
    name: str
    arguments: dict
    result: Any = None
    error: str = ""
    ms: int = 0

    @property
    def ok(self) -> bool:
        return not self.error

    def summary(self) -> dict:
        return {"tool": self.name, "arguments": self.arguments,
                "ok": self.ok, "error": self.error, "ms": self.ms,
                "result": _short(self.result)}


@dataclass
class Transcript:
    """What a run did, which is the record the app shows and keeps."""
    steps: list[Step] = field(default_factory=list)
    answer: str = ""
    stopped: str = ""          # why the loop ended
    calls: int = 0             # model round trips
    input_tokens: int = 0
    output_tokens: int = 0
    improvised: bool = False   # the model had no tool channel

    @property
    def ok(self) -> bool:
        return self.stopped in ("finished", "")

    @property
    def built_anything(self) -> bool:
        """Whether any tool actually ran and did not refuse."""
        return any(step.ok for step in self.steps)

    def summary(self) -> dict:
        return {"steps": [s.summary() for s in self.steps],
                "answer": self.answer, "stopped": self.stopped,
                "calls": self.calls, "improvised": self.improvised,
                "tokens": {"input": self.input_tokens,
                           "output": self.output_tokens}}


def _short(value: Any) -> Any:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    if len(text) <= MAX_RESULT_CHARS:
        return value
    return text[:MAX_RESULT_CHARS] + f"... ({len(text):,} characters in all)"


class Toolbox:
    """The tools one run may use, and the only place they are called."""

    def __init__(self, tools: list[Tool]) -> None:
        self.tools = {tool.name: tool for tool in tools}

    def definitions(self) -> list[dict]:
        return [tool.definition() for tool in self.tools.values()]

    def resolve(self, name: str) -> tuple[Optional["Tool"], dict]:
        """The tool this name means, and what the name itself already says.

        An exact name first, then the alias table. Nothing is guessed: a
        name that is in neither is refused, because a tool chosen by
        resemblance is a tool the model did not ask for.
        """
        tool = self.tools.get(name)
        if tool is not None:
            return tool, {}
        aliased, extra = ALIASES.get(name.strip().lower().lstrip("."), ("", {}))
        return self.tools.get(aliased), dict(extra)

    def invoke(self, name: str, arguments: dict) -> Any:
        """Run one tool, having checked the model did not make it up.

        The checking is the point. A model that calls ``add_hole`` when the
        tool is ``drill`` gets told so, by name, with the real list - which
        it recovers from in one step. A model whose invented call is quietly
        dropped learns nothing and repeats it.

        One class of wrong name is not worth a round trip, though: a small
        model that writes the FreeCAD API it was trained on rather than the
        tools it was handed. ``Part.makeBox`` is not ambiguous, and three
        reminders will not teach it a vocabulary it is not reading. Those
        names are translated, and the arguments the name implies are filled
        in - which is how a run that ended with an empty document now ends
        with a cube.
        """
        tool, implied = self.resolve(name)
        if tool is None:
            near = difflib.get_close_matches(name, list(self.tools), n=1)
            hint = ""
            if near:
                wanted = self.tools[near[0]]
                needs = ", ".join(wanted.parameters.get("required") or [])
                hint = (f" The closest is {near[0]}, which needs "
                        f"{needs or 'nothing'}.")
            raise ToolError(
                f"there is no tool called {name!r}.{hint} There is: "
                + ", ".join(sorted(self.tools)))
        if implied:
            # What the model passed wins: it may have named a different
            # primitive in `kind` than the alias assumed.
            arguments = {**implied, **arguments}

        # Named by the tool that will run, not by what was typed: a message
        # about `Part.makeBox`'s arguments teaches the wrong vocabulary.
        real = tool.name
        allowed = set((tool.parameters.get("properties") or {}))
        # FreeCAD spells a box's sides Length, Width, Height; a model
        # writing from memory spells them length, width, height, and a cube
        # refused over the case of its own letters is a round trip spent on
        # nothing. Folding a name onto the one this tool declares is not
        # guessing: where the two differ only in case there is exactly one
        # property it can mean.
        spelled = {key.lower(): key for key in allowed}
        renames = ARGUMENT_ALIASES.get(real) or {}
        folded: dict = {}
        for key, value in arguments.items():
            lowered = str(key).lower()
            if lowered in spelled:
                folded[spelled[lowered]] = value
            elif renames.get(lowered) in allowed:
                folded.setdefault(renames[lowered], value)
            else:
                folded[key] = value
        arguments = folded
        unknown = sorted(set(arguments) - allowed)
        if unknown and allowed:
            raise ToolError(
                f"{real} has no argument called {', '.join(repr(u) for u in unknown)}. "
                f"It takes: {', '.join(sorted(allowed)) or 'nothing'}")
        missing = sorted(set(tool.parameters.get("required") or []) - set(arguments))
        if missing:
            raise ToolError(
                f"{real} needs {', '.join(repr(m) for m in missing)}")

        return tool.run(**arguments)


def converse(client: Any, model: str, system: str, task: str,
             toolbox: Toolbox, max_steps: int = MAX_STEPS,
             on_step: Optional[Callable[[Step], None]] = None,
             max_tokens: int = 1500,
             before_call: Optional[Callable[["Transcript"], str]] = None) -> Transcript:
    """Let the model work until it says it is done, or runs out of steps.

    The loop itself is deliberately dull. Everything that makes it work is
    either side of it: tools whose results carry measurements, and a
    toolbox that refuses what was never offered.

    ``before_call`` is asked, before every model call, whether to carry on;
    it returns a reason to stop or nothing to continue. That is where a
    token ceiling goes. It stops the loop rather than raising, because the
    part built so far is worth having - a run halted at its ceiling should
    hand back eight finished features, not nothing.
    """
    messages: list[dict] = [{"role": "user", "content": task}]
    transcript = Transcript()
    definitions = toolbox.definitions()
    nudges = 0
    tried: dict[tuple, int] = {}

    for _ in range(max_steps):
        halt = before_call(transcript) if before_call is not None else ""
        if halt:
            transcript.stopped = halt
            return transcript
        reply = client.messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=messages, tools=definitions)
        transcript.calls += 1
        transcript.input_tokens += getattr(reply.usage, "input_tokens", 0)
        transcript.output_tokens += getattr(reply.usage, "output_tokens", 0)
        transcript.improvised = (transcript.improvised
                                 or getattr(reply, "improvised", False))

        said = "".join(block.text for block in reply.content)
        calls = list(getattr(reply, "tool_calls", []) or [])
        if not calls:
            # A model that has built something and then answers in prose has
            # finished, whether or not it says so. A step that was *refused*
            # does not count: a run whose only call was rejected by name has
            # not finished, it has stalled, and ending there publishes an
            # empty document.
            if transcript.built_anything:
                transcript.answer = said.strip()
                transcript.stopped = "finished"
                return transcript

            # Nothing has been built, so this is not an answer - it is a
            # model that wrote out the calls it meant to make instead of
            # making them. Measured on an 8B against a vLLM that accepts a
            # tools array and then ignores it: the reply was the literal
            # text `place_standard_part("Pipe Flange", ...)`. Reading that
            # as "finished" ends the run with an empty document and a
            # cheerful summary of a part that does not exist.
            nudges += 1
            if nudges > MAX_NUDGES:
                transcript.answer = said.strip()
                transcript.stopped = ("answered without calling anything, "
                                      f"after {MAX_NUDGES} reminder(s)")
                return transcript
            messages.append({"role": "assistant", "content": said or "(nothing)"})
            messages.append({"role": "user", "content": NOT_A_CALL})
            continue

        # The model's own turn goes back verbatim, tool requests and all.
        # Anthropic rejects a tool_use with no tool_result after it, and
        # the OpenAI-shaped and promptless roads are translated from this
        # same shape, so there is one conversation and three spellings.
        messages.append({"role": "assistant", "content":
                         ([{"type": "text", "text": said}] if said.strip() else [])
                         + [{"type": "tool_use", "id": call.id or call.name,
                             "name": call.name, "input": call.arguments}
                            for call in calls]})

        results = []
        for call in calls:
            started = time.time()
            step = Step(name=call.name, arguments=dict(call.arguments))
            try:
                step.result = toolbox.invoke(call.name, call.arguments)
            except ToolError as refused:
                step.error = str(refused)
            except Exception as broke:               # the tool itself failed
                step.error = f"{type(broke).__name__}: {broke}"
            step.ms = int((time.time() - started) * 1000)
            transcript.steps.append(step)

            # The same call, refused the same way, over and over. Telling the
            # model it is repeating itself is the signal it needs; stopping
            # after a few is what keeps a stuck loop from spending an
            # afternoon and the whole step budget on one wrong idea.
            if step.error:
                mark = (step.name, step.error[:120])
                tried[mark] = tried.get(mark, 0) + 1
                if tried[mark] >= REPEAT_LIMIT:
                    if on_step is not None:
                        on_step(step)
                    transcript.stopped = (
                        f"{step.name} was refused the same way "
                        f"{tried[mark]} times: {step.error[:200]}")
                    return transcript
                if tried[mark] > 1:
                    step.error += (
                        f" (You have tried this {tried[mark]} times now and it "
                        f"has failed the same way each time. Do something "
                        f"different.)")

            if on_step is not None:
                on_step(step)
            results.append({
                "type": "tool_result",
                "tool_use_id": call.id or call.name,
                "is_error": bool(step.error),
                "content": step.error or json.dumps(_short(step.result),
                                                    default=str)})
        messages.append({"role": "user", "content": results})

    transcript.stopped = f"gave up after {max_steps} steps"
    return transcript
