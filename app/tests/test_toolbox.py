"""Building a part one step at a time, on a model that can call tools and
on one that cannot.

The second case is the one that matters for running this on your own
hardware. A small model served by a vLLM started without
``--enable-auto-tool-choice`` has no tool_calls channel at all: the request
is rejected outright. The tools then go into its prompt and it answers in
JSON, which is a shape an 8B was measured at five out of five on earlier in
this project. Both roads have to reach the same place, so both are driven
here against the same fake endpoint - once answering natively, once
refusing tools and answering in prose.

Run:  .venv/bin/python -m app.tests.test_toolbox
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.server import providers, toolbox  # noqa: E402

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


class Endpoint(BaseHTTPRequestHandler):
    """A chat/completions server that plays out a scripted set of turns."""

    #: Set per test: the turns to hand back, in order.
    script: list = []
    #: False to answer a request carrying tools the way a server with no
    #: tool parser does - rejecting the request, not the model.
    tools_supported: bool = True
    seen: list = []

    def log_message(self, *_):
        pass

    def do_GET(self):
        self._send(200, {"data": [{"id": "fake"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(
            int(self.headers.get("Content-Length", 0))) or b"{}")
        Endpoint.seen.append(body)

        if body.get("tools") and not Endpoint.tools_supported:
            self._send(400, {"error": {
                "message": '"auto" tool choice requires --enable-auto-tool-choice'}})
            return

        turn = Endpoint.script.pop(0) if Endpoint.script else {"content": "done"}
        # Every real OpenAI-compatible endpoint streams, and the client asks
        # for a stream whenever it is not sending tools. A fake that cannot
        # serve one makes the client probe, fail and re-ask - which looks
        # like a bug in the loop and is not.
        if body.get("stream"):
            self._stream(turn)
            return
        message = {"role": "assistant", "content": turn.get("content")}
        # One call, or several in the one reply - which is what a model does
        # when the things it wants do not depend on each other.
        wanted = (turn["tools"] if turn.get("tools")
                  else ([(turn["tool"], turn.get("arguments") or {})]
                        if turn.get("tool") else []))
        if wanted:
            message["tool_calls"] = [{
                "id": f"call_{len(Endpoint.seen)}_{i}", "type": "function",
                "function": {"name": name, "arguments": json.dumps(args)}}
                for i, (name, args) in enumerate(wanted)]
        self._send(200, {"choices": [{"message": message}],
                         "usage": {"prompt_tokens": 100,
                                   "completion_tokens": 40}})

    def _stream(self, turn: dict):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()

        def frame(payload: dict) -> None:
            self.wfile.write(b"data: " + json.dumps(payload).encode() + b"\n\n")
            self.wfile.flush()

        text = turn.get("content") or ""
        for at in range(0, max(len(text), 1), 48):
            frame({"choices": [{"delta": {"content": text[at:at + 48]}}]})
        frame({"choices": [], "usage": {"prompt_tokens": 100,
                                        "completion_tokens": 40}})
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _send(self, code: int, payload: dict):
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def build_toolbox() -> tuple[toolbox.Toolbox, dict]:
    """A toy CAD: every tool answers with what it measured, as the real ones do."""
    model = {"solids": {}, "cuts": 0}

    def add_box(name: str, length: float, width: float, height: float) -> dict:
        model["solids"][name] = {"l": length, "w": width, "h": height}
        return {"added": name, "bbox": [length, width, height],
                "volume": length * width * height}

    def drill(name: str, diameter: float) -> dict:
        if name not in model["solids"]:
            raise toolbox.ToolError(f"there is no solid called {name!r}")
        if diameter <= 0:
            raise ValueError("a hole needs a positive diameter")
        model["cuts"] += 1
        return {"drilled": name, "diameter": diameter, "holes": model["cuts"]}

    return toolbox.Toolbox([
        toolbox.Tool(
            name="add_box", description="Add a rectangular solid.",
            parameters={"type": "object", "properties": {
                "name": {"type": "string"},
                "length": {"type": "number"}, "width": {"type": "number"},
                "height": {"type": "number"}},
                "required": ["name", "length", "width", "height"]},
            run=add_box),
        toolbox.Tool(
            name="drill", description="Drill a through hole.",
            parameters={"type": "object", "properties": {
                "name": {"type": "string"}, "diameter": {"type": "number"}},
                "required": ["name", "diameter"]},
            run=drill),
    ]), model


def run_against(port: int, script: list, supported: bool, task: str = "Build it"):
    Endpoint.script = list(script)
    Endpoint.tools_supported = supported
    Endpoint.seen = []
    box, model = build_toolbox()
    config = providers.LLMConfig(
        provider="custom", kind="openai_compatible",
        base_url=f"http://127.0.0.1:{port}/v1", api_key="x",
        generation_model="fake", judge_model="fake")
    client = providers.build_client(config)
    return toolbox.converse(client, "fake", "You build parts.", task, box), model


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), Endpoint)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print("A model that can call tools")
    script = [
        {"tool": "add_box", "arguments": {"name": "Plate", "length": 60,
                                          "width": 40, "height": 12}},
        {"tool": "drill", "arguments": {"name": "Plate", "diameter": 6}},
        {"content": "Built a 60 x 40 x 12 plate with a 6 mm hole."},
    ]
    run, model = run_against(port, script, supported=True)
    check("it worked step by step rather than in one go", len(run.steps) == 2,
          f"{len(run.steps)} steps over {run.calls} calls")
    check("each step ran, and reported what it measured",
          all(s.ok for s in run.steps)
          and run.steps[0].result["volume"] == 60 * 40 * 12,
          str(run.steps[0].result))
    check("the model's last word is kept", "60 x 40 x 12" in run.answer,
          run.answer)
    check("and the loop knows it finished rather than ran out",
          run.stopped == "finished" and run.ok)
    check("the tools went across as tool definitions",
          [t["function"]["name"] for t in Endpoint.seen[0]["tools"]]
          == ["add_box", "drill"])
    check("and the result went back as a tool result, not as prose",
          any(m.get("role") == "tool" for m in Endpoint.seen[1]["messages"]),
          str([m.get("role") for m in Endpoint.seen[1]["messages"]]))
    check("the real work happened", model["solids"]["Plate"]["l"] == 60
          and model["cuts"] == 1)

    print("\nA model with no tool channel reaches the same place")
    # The server rejects the tools outright, as a vLLM without a tool
    # parser does. The tools move into the prompt and the model answers in
    # JSON - which the loop reads as the same call.
    plain = [
        {"content": json.dumps({"tool": "add_box",
                                "arguments": {"name": "Plate", "length": 60,
                                              "width": 40, "height": 12}})},
        {"content": json.dumps({"tool": "drill",
                                "arguments": {"name": "Plate", "diameter": 6}})},
        {"content": json.dumps({"done": True, "answer": "Plate done."})},
    ]
    run, model = run_against(port, plain, supported=False)
    check("the loop still took two steps", len(run.steps) == 2,
          f"{len(run.steps)} steps")
    check("it did the same work", model["solids"]["Plate"]["l"] == 60
          and model["cuts"] == 1)
    check("and the run says it had to improvise", run.improvised)
    check("the tools were described in the prompt instead",
          "add_box(" in Endpoint.seen[-1]["messages"][0]["content"],
          Endpoint.seen[-1]["messages"][0]["content"][-90:].replace("\n", " "))
    check("nothing was sent as a tool definition after the refusal",
          "tools" not in Endpoint.seen[-1])
    check("and the earlier turns were flattened to text a plain model reads",
          all(isinstance(m.get("content"), str)
              for m in Endpoint.seen[-1]["messages"]),
          str([type(m.get("content")).__name__
               for m in Endpoint.seen[-1]["messages"]]))
    # Asked once, remembered. A rejected request per call would double the
    # cost of every step for the whole run.
    rejected = sum(1 for body in Endpoint.seen if body.get("tools"))
    check("the refusal was paid for once, not on every step", rejected == 1,
          f"{rejected} request(s) carried tools")

    print("\nWhat the model makes up is refused, by name")
    run, _ = run_against(port, [
        {"tool": "add_hole", "arguments": {"name": "Plate", "diameter": 6}},
        {"content": "sorry"}], supported=True)
    check("an invented tool is refused before anything runs",
          run.steps[0].error and "no tool called 'add_hole'" in run.steps[0].error,
          run.steps[0].error[:80])
    check("and the refusal lists what does exist",
          "add_box" in run.steps[0].error and "drill" in run.steps[0].error)

    run, _ = run_against(port, [
        {"tool": "add_box", "arguments": {"name": "P", "length": 1, "width": 1,
                                          "height": 1, "colour": "red"}},
        {"content": "sorry"}], supported=True)
    check("an invented argument is refused too",
          "colour" in (run.steps[0].error or ""), run.steps[0].error[:80])

    run, _ = run_against(port, [
        {"tool": "add_box", "arguments": {"name": "P", "length": 1}},
        {"content": "sorry"}], supported=True)
    check("and a missing one names what is needed",
          "width" in (run.steps[0].error or ""), run.steps[0].error[:80])

    print("\nA tool that fails does not end the run")
    run, _ = run_against(port, [
        {"tool": "drill", "arguments": {"name": "Ghost", "diameter": 6}},
        {"tool": "add_box", "arguments": {"name": "Plate", "length": 10,
                                          "width": 10, "height": 10}},
        {"content": "recovered"}], supported=True)
    check("the failure is recorded as a step, not raised",
          len(run.steps) == 2 and not run.steps[0].ok and run.steps[1].ok,
          str([s.error or "ok" for s in run.steps]))
    check("the model saw it and carried on", run.answer == "recovered")

    # ToolError is the tool saying no on purpose. Anything else is the tool
    # breaking, and the loop has to survive that too - an exception out of
    # geometry code must not take the run down with it.
    run, _ = run_against(port, [
        {"tool": "add_box", "arguments": {"name": "P", "length": 1, "width": 1,
                                          "height": 1}},
        {"tool": "drill", "arguments": {"name": "P", "diameter": -5}},
        {"content": "my mistake"}], supported=True)
    check("a tool raising something unexpected is caught the same way",
          len(run.steps) == 2 and not run.steps[1].ok
          and "ValueError" in run.steps[1].error, run.steps[1].error[:70])
    check("and the model is told what broke, so it can try again",
          "positive diameter" in run.steps[1].error and run.ok,
          run.answer)

    print("\nThe loop is bounded")
    # A model that never stops calling tools must not cost an afternoon.
    forever = [{"tool": "add_box", "arguments": {"name": f"B{i}", "length": 1,
                                                 "width": 1, "height": 1}}
               for i in range(50)]
    run, _ = run_against(port, forever, supported=True)
    check("it gives up rather than looping forever",
          len(run.steps) == toolbox.MAX_STEPS and not run.ok,
          f"{len(run.steps)} steps, stopped: {run.stopped}")

    print("\nThe run is reportable")
    run, _ = run_against(port, script[:1] + [{"content": "done"}], supported=True)
    report = run.summary()
    check("every step is in the transcript, with its timing",
          report["steps"] and report["steps"][0]["tool"] == "add_box"
          and "ms" in report["steps"][0])
    check("and the tokens are counted for the budget",
          report["tokens"]["output"] > 0, str(report["tokens"]))

    print("\nAn endpoint that takes tools and then ignores them")
    # The state that is worse than having no tool channel at all: a vLLM
    # started without --enable-auto-tool-choice accepts a tools array,
    # answers 200, and never emits a tool_calls field. Measured against a
    # real one: the model wrote the call out as text, the loop read "no
    # calls" as "finished", and the run ended with an empty document and a
    # cheerful summary of a part that does not exist.
    run, _ = run_against(port, [
        {"content": 'add_box("Plate", length=80, width=50, height=10)'},
        {"content": json.dumps({"tool": "add_box", "arguments": {
            "name": "Plate", "length": 80, "width": 50, "height": 10}})},
        {"content": "Built the plate."},
    ], supported=True)
    check("a call written out as text is not mistaken for an answer",
          run.steps and run.steps[0].name == "add_box",
          f"{len(run.steps)} step(s), stopped: {run.stopped}")
    check("and the model was told so rather than left to it",
          run.calls >= 3, f"{run.calls} model calls")

    run, _ = run_against(port, [
        {"content": "I would build a plate."},
        {"content": "A plate, 80 by 50 by 10."},
        {"content": "Shall I build it?"},
    ], supported=True)
    check("a model that will not call anything stops, and does not pass",
          not run.ok and not run.built_anything,
          f"stopped: {run.stopped}")
    check("and it is told at most twice before that",
          run.calls == toolbox.MAX_NUDGES + 1, f"{run.calls} model calls")

    # A refused call is not a build. Ending on one would publish an empty
    # document with a summary of the part that was not made.
    run, _ = run_against(port, [
        {"tool": "add_box", "arguments": {"kind": "banana"}},
        {"content": "All done!"},
    ], supported=True)
    check("a run whose only call was refused has not finished",
          not run.built_anything, f"stopped: {run.stopped}")

    print("\nSeveral calls in one reply cost one round trip")
    # A round trip is seconds; a tool call is milliseconds. Three shapes
    # that do not depend on each other should cost one wait, not three, and
    # the loop has to execute them all from the one reply for that to be
    # true of anything but the prompt.
    run, _ = run_against(port, [
        {"tools": [("add_box", {"name": "A", "length": 10, "width": 10,
                                "height": 10}),
                   ("add_box", {"name": "B", "length": 20, "width": 10,
                                "height": 10}),
                   ("add_box", {"name": "C", "length": 30, "width": 10,
                                "height": 10})]},
        {"content": "Built all three."},
    ], supported=True)
    check("every call in one reply is run",
          len(run.steps) == 3 and all(s.ok for s in run.steps),
          ", ".join(f"{s.name}({s.arguments.get('name')})" for s in run.steps))
    check("and they cost one round trip between them",
          run.calls == 2, f"{run.calls} round trips for 3 calls")

    print("\nA call that keeps failing the same way stops the run")
    # Measured on an 8B asked to make a plate thicker, where the plate had
    # no parametric tree: nineteen set_size calls, every one refused with
    # the same sentence, fifty-nine seconds and the whole step budget spent
    # on one wrong idea.
    stuck = [{"tool": "add_box", "arguments": {"kind": "banana"}}
             for _ in range(10)] + [{"content": "done"}]
    run, _ = run_against(port, stuck, supported=True)
    check("it gives up well before the step limit",
          len(run.steps) == toolbox.REPEAT_LIMIT,
          f"{len(run.steps)} steps of {toolbox.MAX_STEPS} allowed")
    check("and says which call, and what it kept answering",
          "add_box" in run.stopped and "refused the same way" in run.stopped,
          run.stopped[:90])
    check("the model was told it was repeating itself before that",
          any("tried this" in (s.error or "") for s in run.steps),
          next((s.error[-60:] for s in run.steps if "tried this" in (s.error or "")), ""))

    server.shutdown()
    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
