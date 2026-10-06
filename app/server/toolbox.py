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

    def invoke(self, name: str, arguments: dict) -> Any:
        """Run one tool, having checked the model did not make it up.

        The checking is the point. A model that calls ``add_hole`` when the
        tool is ``drill`` gets told so, by name, with the real list - which
        it recovers from in one step. A model whose invented call is quietly
        dropped learns nothing and repeats it.
        """
        tool = self.tools.get(name)
        if tool is None:
            raise ToolError(
                f"there is no tool called {name!r}. There is: "
                + ", ".join(sorted(self.tools)))

        allowed = set((tool.parameters.get("properties") or {}))
        unknown = sorted(set(arguments) - allowed)
        if unknown and allowed:
            raise ToolError(
                f"{name} has no argument called {', '.join(repr(u) for u in unknown)}. "
                f"It takes: {', '.join(sorted(allowed)) or 'nothing'}")
        missing = sorted(set(tool.parameters.get("required") or []) - set(arguments))
        if missing:
            raise ToolError(
                f"{name} needs {', '.join(repr(m) for m in missing)}")

        return tool.run(**arguments)


def converse(client: Any, model: str, system: str, task: str,
             toolbox: Toolbox, max_steps: int = MAX_STEPS,
             on_step: Optional[Callable[[Step], None]] = None,
             max_tokens: int = 1500) -> Transcript:
    """Let the model work until it says it is done, or runs out of steps.

    The loop itself is deliberately dull. Everything that makes it work is
    either side of it: tools whose results carry measurements, and a
    toolbox that refuses what was never offered.
    """
    messages: list[dict] = [{"role": "user", "content": task}]
    transcript = Transcript()
    definitions = toolbox.definitions()

    for _ in range(max_steps):
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
            # Nothing left to do. A model that answers in prose has
            # finished, whether or not it says so.
            transcript.answer = said.strip()
            transcript.stopped = "finished"
            return transcript

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
