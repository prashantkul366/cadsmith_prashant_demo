"""The Claude backends stream real reasoning into the event log.

A fake SDK object stands in for the Anthropic client so the whole path runs
without a key or a network: ClaudeClient -> instrumentation -> EventSink, with
the real agents, real RAG retrieval, real CadQuery execution and a real VTK
render in between. Only the model is substituted.

What this pins down:

* thinking and output arrive as separate lanes, tagged with the agent that
  produced them, so the UI can file each fragment under the right step;
* deltas are coalesced rather than emitted one token at a time;
* the model is chosen by role - generation prompts get the generation model,
  the Judge's prompt gets the judge model - which the pipeline's hardcoded
  call-site ids would otherwise defeat;
* a model that rejects the thinking parameter still completes the run.

Run:  python -m app.tests.test_thinking_stream
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.server import providers  # noqa: E402
from app.server.events import PHASE_THINKING  # noqa: E402
from app.server.jobs import (  # noqa: E402
    JobManager, JobOptions, STATUS_DONE, STATUS_ERROR)

PROMPT = "A rectangular block 50mm long, 30mm wide and 20mm tall."

BLOCK = """import cadquery as cq
result = cq.Workplane("XY").box(50, 30, 20)
"""

PLAN = json.dumps({
    "description": "A rectangular block",
    "components": ["block"],
    "dimensions": {"overall_bbox": {"xlen": 50, "ylen": 30, "zlen": 20},
                   "key_dimensions": {"length": 50, "width": 30, "height": 20}},
    "constraints": {"volume_estimate": 30000, "num_holes": None,
                    "hole_diameter": None, "symmetry": None},
    "acceptance_criteria": {"volume_error_threshold_pct": 5,
                            "bbox_iou_threshold": 0.9},
    "notes": "",
})

VERDICT = json.dumps({"passed": True, "feedback": "All constraints met."})

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f" - {detail}" if detail else ""))
    if not ok:
        failures.append(label)


# ---------------------------------------------------------------------------
# A fake Anthropic SDK: streams thinking, then text.
# ---------------------------------------------------------------------------


class _Delta:
    def __init__(self, type_, **kw):
        self.type = type_
        for k, v in kw.items():
            setattr(self, k, v)


class _Event:
    def __init__(self, delta):
        self.type = "content_block_delta"
        self.delta = delta


class _Stream:
    def __init__(self, thinking: str, text: str, reject: bool):
        self._thinking, self._text, self._reject = thinking, text, reject

    def __enter__(self):
        if self._reject:
            raise RuntimeError("thinking: unsupported parameter for this model")
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        # Emitted in small pieces, the way a real stream arrives.
        for i in range(0, len(self._thinking), 17):
            yield _Event(_Delta("thinking_delta", thinking=self._thinking[i:i + 17]))
        for i in range(0, len(self._text), 23):
            yield _Event(_Delta("text_delta", text=self._text[i:i + 23]))

    def get_final_message(self):
        return types.SimpleNamespace(
            stop_reason="end_turn", stop_details=None,
            content=[types.SimpleNamespace(type="text", text=self._text)],
            usage=types.SimpleNamespace(input_tokens=900, output_tokens=120))


class FakeMessages:
    calls: list[dict] = []
    reject_thinking = False

    def stream(self, **kwargs):
        FakeMessages.calls.append(kwargs)
        system = kwargs.get("system", "") or ""
        if "Validator Agent" in system:
            body, think = VERDICT, "The render shows a rectangular block. "
        elif "Planner Agent" in system:
            body, think = PLAN, "Three explicit dimensions, no features. "
        else:
            body, think = BLOCK, "A single box() call is enough here. "
        reject = FakeMessages.reject_thinking and "thinking" in kwargs
        return _Stream(think, body, reject)


class FakeSDK:
    def __init__(self, *a, **kw):
        self.messages = FakeMessages()


def main() -> int:
    providers._build_sdk_client = lambda config: FakeSDK()   # noqa: SLF001

    runs = Path(tempfile.mkdtemp(prefix="cadsmith_thinking_"))
    manager = JobManager(runs)

    print("Running the pipeline on a streaming Claude backend")
    FakeMessages.calls.clear()
    job = manager.create(PROMPT, JobOptions(
        max_iterations=1, use_vision=True, provider="bedrock",
        generation_model="anthropic.claude-sonnet-5",
        judge_model="anthropic.claude-opus-5"))

    deadline = time.time() + 300
    while job.status not in (STATUS_DONE, STATUS_ERROR):
        if time.time() > deadline:
            raise TimeoutError("job did not finish")
        time.sleep(0.3)

    check("the job converged", job.converged, job.error or "")
    check("real geometry was built", (job.directory / "v0" / "model.stl").exists())

    events = [e for e in manager.sink(job.id).all() if e.phase == PHASE_THINKING]
    check("reasoning reached the event stream", bool(events), f"{len(events)} events")

    lanes = {e.data.get("stream") for e in events}
    check("thinking and output arrive as separate lanes",
          {"thinking", "text"} <= lanes, str(sorted(lanes)))

    agents_seen = {e.data.get("agent") for e in events if e.data.get("agent")}
    check("fragments are attributed to the agent that produced them",
          {"plan", "code"} <= agents_seen, str(sorted(agents_seen)))

    thinking_text = "".join(
        e.message for e in events if e.data.get("stream") == "thinking")
    check("the reasoning itself is carried, not just a marker",
          "box() call" in thinking_text or "explicit dimensions" in thinking_text,
          thinking_text[:60])

    # Coalescing: a token-per-event stream would produce far more events than
    # the number of characters divided by the flush threshold.
    check("deltas are coalesced, not one event per token",
          len(events) < 60, f"{len(events)} events for "
          f"{sum(len(e.message) for e in events)} characters")

    print("\nRole routing")
    models = [c["model"] for c in FakeMessages.calls]
    judge_calls = [c for c in FakeMessages.calls
                   if "Validator Agent" in (c.get("system") or "")]
    check("generation prompts used the generation model",
          any(m == "anthropic.claude-sonnet-5" for m in models), str(set(models)))
    check("the Judge used the judge model",
          bool(judge_calls) and all(
              c["model"] == "anthropic.claude-opus-5" for c in judge_calls))
    check("thinking was requested with a readable summary",
          all(c.get("thinking", {}).get("display") == "summarized"
              for c in FakeMessages.calls if "thinking" in c))
    check("the token ceiling was raised for thinking",
          all(c["max_tokens"] >= 8192 for c in FakeMessages.calls))

    print("\nA model that rejects the thinking parameter")
    FakeMessages.reject_thinking = True
    FakeMessages.calls.clear()
    job2 = manager.create(PROMPT, JobOptions(
        max_iterations=1, use_vision=False, provider="bedrock",
        generation_model="anthropic.claude-3-haiku-20240307-v1:0",
        judge_model="anthropic.claude-3-haiku-20240307-v1:0"))
    deadline = time.time() + 300
    while job2.status not in (STATUS_DONE, STATUS_ERROR):
        if time.time() > deadline:
            raise TimeoutError("fallback job did not finish")
        time.sleep(0.3)
    check("the run still completes without thinking", job2.converged,
          job2.error or "")
    check("and the retry dropped the parameter",
          any("thinking" not in c for c in FakeMessages.calls))

    shutil.rmtree(runs, ignore_errors=True)

    print(f"\n{'=' * 58}")
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED: {', '.join(failures)}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
