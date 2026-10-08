"""Check the pipeline against a non-Anthropic backend.

A real HTTP server speaking the OpenAI chat-completions API stands in for
OpenAI or a local Ollama, so the adapter is exercised over the wire: message
translation, the base64 image the Judge sends, token accounting, JSON replies
wrapped in prose, and the retry when a model refuses images.

CadQuery and VTK do real work throughout - only the model is substituted.

Run:  .venv/bin/python -m app.tests.test_providers
"""

from __future__ import annotations

import builtins
import json
import shutil
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.server import providers  # noqa: E402
from app.server.jobs import (  # noqa: E402
    JobManager, JobOptions, STATUS_DONE, STATUS_ERROR)
from app.server.providers import (  # noqa: E402
    LLMConfig, OpenAICompatibleClient, repair_json)

PROMPT = "A flat washer, 20mm outer diameter, 10.5mm bore, 2mm thick."

PLAN = {
    "description": "Flat washer",
    "components": ["annular disc"],
    "dimensions": {"overall_bbox": {"xlen": 20, "ylen": 20, "zlen": 2},
                   "key_dimensions": {"outer_diameter": 20, "thickness": 2}},
    "constraints": {"num_holes": 1},
    "acceptance_criteria": {"volume_error_threshold_pct": 5},
    "notes": "Concentric circles extruded.",
}

CODE = """import cadquery as cq

outer_diameter = 20.0
bore = 10.5
thickness = 2.0

result = (
    cq.Workplane('XY')
    .circle(outer_diameter / 2.0)
    .circle(bore / 2.0)
    .extrude(thickness)
)
"""


class FakeOpenAIServer(BaseHTTPRequestHandler):
    """A minimal chat-completions server that records what it was sent."""

    requests: list[dict] = []
    reject_images: bool = False
    wrap_json_in_prose: bool = True
    #: Every real OpenAI-compatible endpoint streams, and the app asks for a
    #: stream first because a self-hosted one is usually behind a proxy that
    #: cuts off a quiet request. Set False to stand in for one that does not.
    streams: bool = True
    #: How many of the next requests answer 524 before one is served. A
    #: Cloudflare quick tunnel in front of a slow model does exactly this:
    #: it stops waiting, answers 524, and the generation behind it carries
    #: on. Counted down, so 2 means "fail twice, then work".
    gateway_failures: int = 0
    #: Non-zero makes the endpoint refuse a request whose prompt and
    #: requested ceiling will not fit together, the way vLLM does.
    context_window: int = 0

    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path.endswith("/models"):
            self._json(200, {"data": [{"id": "fake-large"}, {"id": "fake-small"}]})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        FakeOpenAIServer.requests.append(body)

        if FakeOpenAIServer.context_window:
            asked = int(body.get("max_tokens") or 0)
            prompt = 16769          # as a real refusal reports it
            if asked + prompt > FakeOpenAIServer.context_window:
                self._json(400, {"error": {"message":
                    f"This model's maximum context length is "
                    f"{FakeOpenAIServer.context_window} tokens. However, you "
                    f"requested {asked} output tokens and your prompt "
                    f"contains at least {prompt} input tokens, for a total "
                    f"of at least {asked + prompt} tokens."}})
                return

        if FakeOpenAIServer.gateway_failures > 0:
            FakeOpenAIServer.gateway_failures -= 1
            self._json(524, {"error": "origin timed out"})
            return

        has_image = any(
            isinstance(m.get("content"), list)
            and any(p.get("type") == "image_url" for p in m["content"])
            for m in body.get("messages", []))

        if has_image and FakeOpenAIServer.reject_images:
            self._json(400, {"error": {
                "message": "This model does not support image input."}})
            return

        system = next((m["content"] for m in body.get("messages", [])
                       if m.get("role") == "system"), "")
        text = self._reply_for(system)
        if body.get("stream") and FakeOpenAIServer.streams:
            self._stream(text)
            return
        self._json(200, {
            "choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 1234, "completion_tokens": 567},
        })

    def _stream(self, text: str):
        """The same reply, in server-sent chunks, usage last."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()

        def frame(payload: dict) -> None:
            self.wfile.write(b"data: " + json.dumps(payload).encode() + b"\n\n")
            self.wfile.flush()

        for at in range(0, len(text), 64):
            frame({"choices": [{"delta": {"content": text[at:at + 64]}}]})
        frame({"choices": [],
               "usage": {"prompt_tokens": 1234, "completion_tokens": 567}})
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()

    def _reply_for(self, system: str) -> str:
        if "Planner Agent" in system:
            payload = json.dumps(PLAN)
            return (f"Sure, here is the plan:\n```json\n{payload}\n```\nHope "
                    f"that helps!") if FakeOpenAIServer.wrap_json_in_prose \
                else payload
        if "Validator Agent" in system:
            return json.dumps({"passed": True, "feedback": "All constraints met."})
        return CODE

    def _json(self, code: int, payload: dict):
        raw = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
        if not ok:
            failures.append(label)

    server = HTTPServer(("127.0.0.1", 0), FakeOpenAIServer)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{port}/v1"

    print("\nJSON recovered from a chatty reply")
    check("prose around a fenced object",
          json.loads(repair_json('Sure!\n```json\n{"a": 1}\n```\nDone.'))["a"] == 1)
    check("prose around a bare object",
          json.loads(repair_json('Here you go: {"a": 2} — enjoy'))["a"] == 2)
    check("braces inside strings survive",
          json.loads(repair_json('x {"a": "} not the end", "b": 3} y'))["b"] == 3)
    clean = '{"already": "fine"}'
    check("a clean reply is untouched", repair_json(clean) == clean)
    check("non-JSON is returned as-is", repair_json("no object here") == "no object here")

    print("\nProvider registry")
    providers.set_session_key("custom", api_key="test-key", base_url=base_url)
    entry = next(p for p in providers.status() if p["id"] == "custom")
    check("a session key marks the provider ready", entry["ready"])
    check("the key came from the session", entry["key_from_session"])
    check("no key is ever exposed", "api_key" not in entry and "key" not in entry,
          str(sorted(entry)))
    check("models are read from the provider",
          providers.list_models("custom") == ["fake-large", "fake-small"])

    config = providers.resolve("custom", generation_model="fake-small",
                               judge_model="fake-large")
    check("configuration resolves", not providers.problems(config),
          str(providers.problems(config)))
    check("redaction hides the key",
          "api_key" not in config.redacted() and config.redacted()["has_key"])

    print("\nRunning the pipeline on the fake provider")
    FakeOpenAIServer.requests.clear()
    runs = Path(tempfile.mkdtemp(prefix="cadsmith_providers_"))
    manager = JobManager(runs)
    job = manager.create(PROMPT, JobOptions(
        max_iterations=1, use_vision=True, provider="custom",
        generation_model="fake-small", judge_model="fake-large"))

    deadline = time.time() + 300
    while job.status not in (STATUS_DONE, STATUS_ERROR):
        if time.time() > deadline:
            raise TimeoutError("job did not finish")
        time.sleep(0.3)

    check("job converged", job.converged, job.error or "")
    check("real geometry was built",
          (job.directory / "v0" / "model.stl").exists())
    geometry = json.loads((job.directory / "v0" / "geometry.json").read_text(encoding="utf-8"))
    check("the kernel measured the washer",
          abs(geometry["bounding_box"]["xlen"] - 20.0) < 1e-6
          and geometry["is_valid"])

    sent = FakeOpenAIServer.requests
    check("every agent reached the provider", len(sent) >= 3, f"{len(sent)} calls")
    models_used = {r["model"] for r in sent}
    check("generation used the generation model", "fake-small" in models_used)
    check("judging used the judge model", "fake-large" in models_used,
          str(models_used))

    judge_calls = [r for r in sent if r["model"] == "fake-large"]
    judge_content = judge_calls[0]["messages"][-1]["content"]
    check("the render reached the Judge as a data URL",
          isinstance(judge_content, list)
          and any(p.get("type") == "image_url"
                  and p["image_url"]["url"].startswith("data:image/png;base64,")
                  for p in judge_content))
    check("the system prompt is a system message",
          any(m["role"] == "system" for m in judge_calls[0]["messages"]))
    check("token usage was mapped from the OpenAI shape",
          job.tokens.get("input_tokens", 0) >= 1234
          and job.tokens.get("output_tokens", 0) >= 567,
          str(job.tokens))

    print("\nThe reply is streamed, so a proxy has nothing to time out on")
    # A self-hosted endpoint is usually reached through a tunnel or a
    # reverse proxy, and those cut a request off when the origin has sent
    # nothing for a while - Cloudflare's limit is 100 seconds. An 8B model
    # writing a whole CadQuery script goes past that, and the Coder died on
    # a 524 while the model was working perfectly well. Streaming keeps the
    # first byte close and nothing in between idle.
    FakeOpenAIServer.requests.clear()
    deltas: list[tuple[str, str]] = []
    streaming = OpenAICompatibleClient(
        LLMConfig(provider="custom", kind="openai_compatible", base_url=base_url,
                  api_key="test-key", generation_model="fake-small",
                  judge_model="fake-large"),
        on_delta=lambda kind, text: deltas.append((kind, text)))
    reply = streaming.messages.create(
        model="ignored", max_tokens=1024, system="You are the Coder Agent.",
        messages=[{"role": "user", "content": "Write it."}])
    check("the request asked for a stream",
          FakeOpenAIServer.requests[-1].get("stream") is True,
          str(FakeOpenAIServer.requests[-1].get("stream")))
    check("and for the usage that does not come with one by default",
          (FakeOpenAIServer.requests[-1].get("stream_options") or {})
          .get("include_usage") is True)
    check("the chunks are reassembled into the whole reply",
          reply.content[0].text == CODE,
          f"{len(reply.content[0].text)} chars of {len(CODE)}")
    check("usage survives the stream",
          reply.usage.input_tokens == 1234 and reply.usage.output_tokens == 567,
          f"{reply.usage.input_tokens}/{reply.usage.output_tokens}")
    check("and the fragments were published as they arrived",
          len(deltas) > 1 and all(kind == "text:generation" for kind, _ in deltas)
          and "".join(text for _, text in deltas) == CODE,
          f"{len(deltas)} fragment(s)")

    print("\nAn endpoint that will not stream is asked the old way")
    FakeOpenAIServer.requests.clear()
    FakeOpenAIServer.streams = False
    notes: list[str] = []
    stubborn = OpenAICompatibleClient(
        LLMConfig(provider="custom", kind="openai_compatible", base_url=base_url,
                  api_key="test-key", generation_model="fake-small",
                  judge_model="fake-large"),
        on_note=notes.append)
    first = stubborn.messages.create(
        model="ignored", max_tokens=1024, system="You are the Coder Agent.",
        messages=[{"role": "user", "content": "Write it."}])
    check("the reply comes back anyway", first.content[0].text == CODE)
    check("and it said so rather than failing the run",
          notes and "would not stream" in notes[0], str(notes))
    tried = len(FakeOpenAIServer.requests)
    second = stubborn.messages.create(
        model="ignored", max_tokens=1024, system="You are the Coder Agent.",
        messages=[{"role": "user", "content": "Again."}])
    check("the next call does not pay for a failed stream again",
          second.content[0].text == CODE
          and len(FakeOpenAIServer.requests) == tried + 1
          and FakeOpenAIServer.requests[-1].get("stream") is None,
          f"{len(FakeOpenAIServer.requests) - tried} request(s)")
    FakeOpenAIServer.streams = True

    print("\nA ceiling that will not fit the window is refitted, not guessed")
    FakeOpenAIServer.requests.clear()
    FakeOpenAIServer.context_window = 32768
    fitted = OpenAICompatibleClient(
        LLMConfig(provider="custom", kind="openai_compatible", base_url=base_url,
                  api_key="test-key", generation_model="fake-small",
                  judge_model="fake-large"),
        on_note=notes.append)
    notes.clear()
    try:
        reply = fitted.messages.create(
            model="ignored", max_tokens=16000,
            system="You are the Coder Agent.",
            messages=[{"role": "user", "content": "Write it."}])
        check("the reply comes back on the second ask",
              reply.content[0].text == CODE, reply.content[0].text[:40])
        asked = [b.get("max_tokens") for b in FakeOpenAIServer.requests]
        check("the ceiling was cut to what the window had left",
              asked[0] == 16000 and asked[-1] < 16000 and asked[-1] > 256,
              str(asked))
        check("and it said so rather than failing quietly",
              any("would not fit beside" in n for n in notes), str(notes)[:140])
    finally:
        FakeOpenAIServer.context_window = 0

    print("\nA tunnel that stops waiting is asked again, not reported as failed")
    FakeOpenAIServer.requests.clear()
    FakeOpenAIServer.gateway_failures = 2
    was_backoff = providers.GATEWAY_BACKOFF
    providers.GATEWAY_BACKOFF = (0.01, 0.01, 0.01)
    notes = []
    tunnelled = OpenAICompatibleClient(
        LLMConfig(provider="custom", kind="openai_compatible", base_url=base_url,
                  api_key="test-key", generation_model="fake-small",
                  judge_model="fake-large"),
        on_note=notes.append)
    try:
        reply = tunnelled.messages.create(
            model="ignored", max_tokens=1024, system="You are the Coder Agent.",
            messages=[{"role": "user", "content": "Write it."}])
        check("two 524s cost the run nothing but time",
              reply.content[0].text == CODE,
              reply.content[0].text[:40])
        check("and it asked exactly as many times as it needed",
              len(FakeOpenAIServer.requests) == 3,
              f"{len(FakeOpenAIServer.requests)} request(s)")
        check("each wait was said out loud",
              sum("stopped waiting" in n for n in notes) == 2, str(notes)[:160])

        # The other direction: an endpoint that is simply gone must still
        # fail, and say what it tried, rather than retrying for ever.
        FakeOpenAIServer.requests.clear()
        FakeOpenAIServer.gateway_failures = 99
        notes.clear()
        try:
            tunnelled.messages.create(
                model="ignored", max_tokens=1024,
                system="You are the Coder Agent.",
                messages=[{"role": "user", "content": "Write it."}])
            check("an endpoint that never answers fails", False, "it returned")
        except RuntimeError as exc:
            check("an endpoint that never answers fails, with the count",
                  "3 attempts" in str(exc), str(exc)[:120])
        check("and it stopped at the ceiling rather than hammering",
              len(FakeOpenAIServer.requests) == providers.GATEWAY_ATTEMPTS,
              f"{len(FakeOpenAIServer.requests)} request(s)")
    finally:
        providers.GATEWAY_BACKOFF = was_backoff
        FakeOpenAIServer.gateway_failures = 0

    print("\nA model that refuses images falls back instead of failing")
    FakeOpenAIServer.requests.clear()
    FakeOpenAIServer.reject_images = True
    notes: list[str] = []
    client = OpenAICompatibleClient(
        LLMConfig(provider="custom", kind="openai_compatible", base_url=base_url,
                  api_key="test-key", generation_model="fake-small",
                  judge_model="fake-large"),
        on_note=notes.append)

    from autofab import agents

    response = client.messages.create(
        model="ignored", max_tokens=1024, system=agents.VALIDATOR_SYSTEM,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64",
                                         "media_type": "image/png",
                                         "data": "aGVsbG8="}},
            {"type": "text", "text": "Evaluate and return JSON."},
        ]}])
    check("the Judge still answered",
          json.loads(response.content[0].text)["passed"] is True)
    check("it retried without the image", len(FakeOpenAIServer.requests) == 2,
          f"{len(FakeOpenAIServer.requests)} attempts")
    check("the fallback was reported, not hidden",
          notes and "kernel metrics alone" in notes[0],
          str(notes))
    FakeOpenAIServer.reject_images = False

    print("\nThe Claude backends")
    providers.clear_session_keys()
    default = providers.resolve("anthropic")
    check("a weaker coder paired with a stronger judge",
          default.generation_model == "claude-sonnet-5"
          and default.judge_model == "claude-opus-5",
          f"{default.generation_model} / {default.judge_model}")

    # The account that caught this one, listed exactly as its own
    # pre-flight check printed it: three spellings of the same model, and
    # the Messages endpoint serving only one of them. A listing is a guess
    # about which namespace answers, so the client probes down the list
    # rather than betting a run on the guess.
    account = ["global.anthropic.claude-sonnet-5-5",
               "us.anthropic.claude-sonnet-5-5",
               "global.anthropic.claude-sonnet-5",
               "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
               "global.anthropic.claude-opus-5-5",
               "us.anthropic.claude-opus-5-5"]
    ranked = providers.rank_claude(account, "sonnet")
    check("the newest is tried first", ranked[0].endswith("sonnet-5-5"),
          ranked[0])
    check("and a cross-region profile before a regional one",
          ranked[0].startswith("global.") and ranked[1].startswith("us."),
          " then ".join(ranked[:2]))
    check("every spelling is a candidate, not just the winner",
          len(ranked) == 4, str(len(ranked)))

    providers._model_list_cache[os.getenv("AWS_REGION") or "us-east-1"] = (
        time.time(), tuple(account))
    try:
        asked = []
        # The two this account really refused, and the one left. Picking
        # the third rather than the first is the point: a test whose
        # server answers the first candidate never walks the list at all.
        served = "global.anthropic.claude-sonnet-5"

        class Probe(providers.ClaudeClient):
            def __init__(self):
                self.config = LLMConfig(
                    provider="bedrock", kind="bedrock", base_url="",
                    api_key="", generation_model="anthropic.claude-sonnet-5-5",
                    judge_model="anthropic.claude-opus-5-5")
                self._on_note = None
                self._thinking_ok = False
                self._effort_ok = False
                self._serves, self._refused = {}, set()

            def _note(self, message): pass

            def _stream(self, target, system, messages, max_tokens, role,
                        *rest):
                asked.append(target)
                if target != served:
                    raise RuntimeError(
                        f"Error code: 404 - {{'type': 'error', 'error': "
                        f"{{'type': 'not_found_error', 'message': \"The "
                        f"model '{target}' does not exist\"}}}}")
                return "ok"

        probe = Probe()
        check("a 404 on the first id is not the end of the run",
              probe.create(system="You are the Coder Agent") == "ok",
              " -> ".join(asked))
        check("it walked down to the one the endpoint serves",
              asked == ["global.anthropic.claude-sonnet-5-5",
                        "us.anthropic.claude-sonnet-5-5", served],
              " -> ".join(asked))
        before = len(asked)
        probe.create(system="You are the Coder Agent")
        check("and does not walk the dead ids again",
              len(asked) == before + 1 and asked[-1] == served,
              " -> ".join(asked[before:]))
    finally:
        providers._model_list_cache.clear()

    claude = providers.build_client(
        LLMConfig(provider="anthropic", kind="anthropic", base_url="",
                  api_key="x", generation_model="gen", judge_model="jud"))
    check("wrapped in the streaming client, not the bare SDK",
          isinstance(claude, providers.ClaudeClient))
    check("which still presents the SDK surface",
          hasattr(claude.messages, "create"))

    # The pipeline hardcodes a model id at each call site; the wrapper must
    # substitute the configured one, keyed on the agent's own system prompt.
    check("generation prompts route to the generation model",
          providers.OpenAICompatibleClient._role_for(
              "You are the Coder Agent") == "generation")
    check("the Judge's prompt routes to the judge model",
          providers.OpenAICompatibleClient._role_for(
              agents.VALIDATOR_SYSTEM) == "judge")

    print("\nBedrock")
    bedrock = providers.resolve("bedrock")
    check("model ids carry the anthropic. prefix Bedrock requires",
          bedrock.generation_model.startswith("anthropic.")
          and bedrock.judge_model.startswith("anthropic."),
          f"{bedrock.generation_model} / {bedrock.judge_model}")
    check("needs no API key - it uses the AWS credential chain",
          providers.BUILTIN["bedrock"].needs_key is False)
    check("and says so plainly when credentials are absent",
          any("AWS credentials" in p for p in providers.problems(bedrock))
          or providers._aws_identity() != "",
          "; ".join(providers.problems(bedrock)) or "credentials present")

    # A compiled-in default is a guess about somebody else's AWS account.
    # One account serves `anthropic.claude-sonnet-5-5`; the next serves
    # everything as `global.anthropic.*` cross-region inference profiles
    # and answers 404 to the bare id. So the account's own list decides,
    # and the constant is only the answer when Bedrock cannot be asked.
    offered = ["global.anthropic.claude-haiku-4-5-20251001-v1:0",
               "global.anthropic.claude-haiku-5-5",
               "global.anthropic.claude-opus-4-5-20251101-v1:0",
               "global.anthropic.claude-sonnet-4-5-20250929-v1:0",
               "global.anthropic.claude-opus-4-6",
               "anthropic.claude-3-5-sonnet-20240620-v1:0"]
    check("the newest Sonnet the account has is chosen",
          providers.best_claude(offered, "sonnet")
          == "global.anthropic.claude-sonnet-4-5-20250929-v1:0",
          providers.best_claude(offered, "sonnet"))
    check("and the newest Opus, by version rather than by listing order",
          providers.best_claude(offered, "opus")
          == "global.anthropic.claude-opus-4-6",
          providers.best_claude(offered, "opus"))
    check("an undated id wins a tie, because a dated one pins a snapshot",
          providers.best_claude(["x.claude-opus-5-5-20260401-v1:0",
                                 "x.claude-opus-5-5"], "opus")
          == "x.claude-opus-5-5")
    check("a family the account does not carry falls back, not guesses",
          providers.best_claude(offered, "fable") == "")

    # And what happens when the account carries Claude but not the family
    # this role wanted. Returning the constant there is the worst answer
    # available: it is a guess about another account, made while holding a
    # list that says it is wrong. A run went out under
    # `anthropic.claude-sonnet-5-5` and died on a 404 while 33 invokable ids
    # sat in the model box beside it.
    no_sonnet = [i for i in offered if "sonnet" not in i]
    providers._model_list_cache[os.getenv("AWS_REGION") or "us-east-1"] = (
        time.time(), tuple(no_sonnet))
    try:
        chosen = providers.bedrock_default("sonnet", "anthropic.claude-sonnet-5-5")
        check("an account with no Sonnet gets its best other Claude",
              chosen in no_sonnet, chosen)
        check("the best one, not merely any one",
              chosen == "global.anthropic.claude-opus-4-6", chosen)
        check("and the picker offers exactly the list it was picked from",
              providers._list_bedrock_models() == no_sonnet)
        providers._model_list_cache.clear()
        check("with no list at all the compiled-in default still stands",
              providers.bedrock_default("sonnet", "stands.in")
              in (offered + ["stands.in"]))
    finally:
        providers._model_list_cache.clear()

    # The likeliest way Bedrock fails is a virtualenv without boto3, which
    # `pip install anthropic` leaves behind unless the [bedrock] extra is
    # asked for. That used to be reported as bad AWS credentials, sending
    # the reader off to rotate keys over a missing import - and, worse, the
    # health banner announced Bedrock ready while the first Generate
    # answered 503, because the picker and the gate asked different
    # questions. Both halves are checked here.
    real_import = builtins.__import__

    def no_boto(name, *args, **kwargs):
        if name.split(".")[0] in ("boto3", "botocore"):
            raise ModuleNotFoundError("No module named 'boto3'")
        return real_import(name, *args, **kwargs)

    providers._aws_cache = (0.0, "", "")
    builtins.__import__ = no_boto
    try:
        blind = providers.problems(bedrock)
        blind_ready = next(p["ready"] for p in providers.status()
                           if p["id"] == "bedrock")
    finally:
        builtins.__import__ = real_import
        providers._aws_cache = (0.0, "", "")
    check("without boto3 it names the dependency, not the credentials",
          any("boto3" in issue for issue in blind), "; ".join(blind))
    check("and the picker calls Bedrock unready rather than offering a 503",
          blind_ready is False)

    # Whatever this machine's credentials are, the banner and the gate have
    # to give the same answer - that disagreement is what produced a ready
    # health check and a refused job on the same server.
    bedrock_ready = next(p["ready"] for p in providers.status()
                         if p["id"] == "bedrock")
    check("the picker's readiness and the job gate agree",
          bedrock_ready == (not providers.problems(bedrock)),
          f"ready={bedrock_ready} problems={providers.problems(bedrock)}")

    server.shutdown()
    shutil.rmtree(runs, ignore_errors=True)

    print(f"\n{'=' * 58}")
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED: {', '.join(failures)}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
