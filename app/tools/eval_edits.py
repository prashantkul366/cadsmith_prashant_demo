"""Score the app the way an engineer actually uses it: one change at a time.

``eval_parts`` asks whether a prompt produces the right part.  That is half
the job.  Nobody describes a bracket once and takes what comes - they get
something close, then say "make it 12mm thick", then "add four M6 holes",
then "move the bore 5mm off centre".  Each of those has to land on the part
the last one produced, and the failure mode that matters is not a bad first
attempt, it is the fourth edit quietly undoing the second.

So this drives the edit path: one base prompt, then a chain of instructions,
measuring the built solid after every one.  Each step states what it expects
of the part *after* that step, and the check is cumulative - an edit that
gets its own change right while dropping the holes added two steps earlier
fails, which is exactly the behaviour worth catching.

Two things it watches that a single-shot run cannot show:

* **drift** - a dimension nobody asked to change, changing anyway;
* **cost** - which steps went through the parameter patcher for nothing and
  which went to the Refiner, because a chain where every step calls a model
  is a chain that will be abandoned.

    python -m app.tools.eval_edits
    python -m app.tools.eval_edits --chain plate
    python -m app.tools.eval_edits --provider custom \
        --generation-model Qwen/Qwen3-VL-8B-Instruct
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.server import spec  # noqa: E402
from app.server.events import (  # noqa: E402
    PHASE_CODE, PHASE_ERROR_FIX, PHASE_JUDGE, PHASE_PLAN, PHASE_REFINE,
    STATUS_STARTED)
from app.server.jobs import (  # noqa: E402
    JobManager, JobOptions, STATUS_DONE, STATUS_ERROR)
from app.tools.eval_parts import score  # noqa: E402

#: The phases that mean a model was asked something. Counted from the event
#: log rather than read off ``job.llm_calls``, which the edit path never
#: updates - only generation sets it - so every edit read as free, including
#: ones that spent ten Judge calls over two minutes. A cost signal that is
#: wrong in the cheap direction is worse than none: it says the expensive
#: path is free.
MODEL_PHASES = (PHASE_PLAN, PHASE_CODE, PHASE_JUDGE, PHASE_REFINE,
                PHASE_ERROR_FIX)

#: Chains an engineer would plausibly work through. Each step's ``expect``
#: describes the whole part after that step, not just what changed, so a step
#: that loses an earlier feature fails even when its own change landed.
CHAINS: list[dict] = [
    {
        "id": "plate",
        "prompt": "A flat steel plate 100mm by 60mm by 8mm thick.",
        "expect": {"bbox": [100, 60, 8], "holes": 0},
        "steps": [
            {"say": "make it 12mm thick",
             "expect": {"bbox": [100, 60, 12], "holes": 0}},
            {"say": "add four 6mm holes, one 12mm in from each corner",
             "expect": {"bbox": [100, 60, 12], "holes": 4,
                        "bore_dia": [6, 6, 6, 6]}},
            {"say": "make the plate 120mm long",
             "expect": {"bbox": [120, 60, 12], "holes": 4}},
            {"say": "increase the holes to 8mm",
             "expect": {"bbox": [120, 60, 12], "holes": 4,
                        "bore_dia": [8, 8, 8, 8]}},
        ],
    },
    {
        "id": "spacer",
        "prompt": "A cylindrical spacer 30mm outside diameter, 12mm bore, 20mm long.",
        "expect": {"bbox": [30, 30, 20], "bore_dia": [12]},
        "steps": [
            {"say": "make it 35mm long",
             "expect": {"bbox": [30, 30, 35], "bore_dia": [12]}},
            {"say": "open the bore to 16mm",
             "expect": {"bbox": [30, 30, 35], "bore_dia": [16]}},
            {"say": "make the outside diameter 40mm",
             "expect": {"bbox": [40, 40, 35], "bore_dia": [16]}},
        ],
    },
    {
        "id": "bracket",
        "prompt": "An L-shaped bracket 80mm tall, 60mm deep, 50mm wide, 6mm thick.",
        "expect": {},
        "steps": [
            {"say": "make it 8mm thick", "expect": {}},
            {"say": "add two 7mm holes in the upright leg", "expect": {"holes": 2}},
            {"say": "add two 7mm holes in the base as well", "expect": {"holes": 4}},
        ],
    },
    {
        "id": "gear",
        "prompt": "A 20 tooth spur gear, module 2.",
        "expect": {},
        "steps": [
            {"say": "make the face width 15mm", "expect": {"bbox": [44, 44, 15]}},
            {"say": "open the bore to 10mm", "expect": {"bore_dia": [10]}},
        ],
    },
]


@dataclass
class StepResult:
    say: str
    ok: bool = False
    checks: list[dict] = field(default_factory=list)
    seconds: float = 0.0
    llm_calls: int = 0
    drift: list[str] = field(default_factory=list)
    error: str = ""

    @property
    def matched(self) -> int:
        return sum(1 for c in self.checks if c["ok"])


@dataclass
class ChainResult:
    id: str
    prompt: str
    base_ok: bool = False
    steps: list[StepResult] = field(default_factory=list)
    error: str = ""

    @property
    def survived(self) -> int:
        """How many steps in a row landed before the first that did not."""
        count = 0
        for step in self.steps:
            if not step.ok:
                break
            count += 1
        return count


def _wait(job, timeout: float) -> bool:
    deadline = time.time() + timeout
    while job.status not in (STATUS_DONE, STATUS_ERROR):
        if time.time() > deadline:
            return False
        time.sleep(0.4)
    return job.status == STATUS_DONE


def _calls(manager: JobManager, job) -> int:
    """How many times a model has been asked something in this job so far."""
    sink = manager.sink(job.id)
    if sink is None:
        return 0
    return sum(1 for event in sink.all()
               if event.phase in MODEL_PHASES and event.status == STATUS_STARTED)


def _measure(manager: JobManager, job) -> Optional[dict]:
    if not job.versions:
        return None
    step = manager.artifact_path(job.id, job.versions[-1].get("iteration", 0),
                                 "model.step")
    if step is None or not step.is_file():
        return None
    try:
        return spec.measure_step(step)
    except Exception:
        return None


def _drift(before: dict, after: dict, expect: dict) -> list[str]:
    """Dimensions that changed without being asked to.

    Only reported where the step said what it expected of that axis - a step
    that does not mention the length is not evidence the length should hold,
    since "make it longer" legitimately moves it.
    """
    moved: list[str] = []
    box = expect.get("bbox") or []
    for index, axis in enumerate(("xlen", "ylen", "zlen")):
        wanted = box[index] if index < len(box) else None
        if wanted is not None:
            continue          # already checked directly
        was, now = before["bbox"][axis], after["bbox"][axis]
        if abs(now - was) > max(0.5, abs(was) * 0.02):
            moved.append(f"{axis} {was:.1f} -> {now:.1f}")
    if before["num_holes"] and not after["num_holes"] \
            and expect.get("holes") is None:
        moved.append(f"holes {before['num_holes']} -> 0")
    return moved


def run_chain(runs_dir: Path, chain: dict, options: JobOptions,
              timeout: float) -> ChainResult:
    """One chain, in a JobManager of its own.

    A chain has to share a manager across its own steps - the edits land on
    the job the base prompt created - but not across chains: JobManager runs
    one job at a time, so abandoning a chain on timeout would leave the next
    one queued behind the run the timeout was meant to escape.
    """
    manager = JobManager(runs_dir)
    out = ChainResult(id=chain["id"], prompt=chain["prompt"])
    job = manager.create(chain["prompt"], options)
    if not _wait(job, timeout):
        out.error = job.error or f"the base part did not build in {timeout:.0f}s"
        return out

    measured = _measure(manager, job)
    if measured is None:
        out.error = "the base part produced nothing to measure"
        return out
    checks = score(chain.get("expect") or {}, measured, False)
    out.base_ok = all(c["ok"] for c in checks)
    print(f"      base: {'ok' if out.base_ok else 'off'} "
          + "; ".join(c["detail"] for c in checks if not c["ok"])[:70])

    for raw in chain["steps"]:
        result = StepResult(say=raw["say"])
        before = measured
        calls_before = _calls(manager, job)
        started = time.time()
        try:
            manager.submit_edit(job, raw["say"], len(job.versions) - 1)
        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"
            out.steps.append(result)
            break
        finished = _wait(job, timeout)
        result.seconds = time.time() - started
        result.llm_calls = _calls(manager, job) - calls_before
        if not finished:
            result.error = job.error or "the edit did not finish"
            out.steps.append(result)
            break

        measured = _measure(manager, job) or before
        result.checks = score(raw.get("expect") or {}, measured, False)
        result.ok = all(c["ok"] for c in result.checks)
        result.drift = _drift(before, measured, raw.get("expect") or {})
        out.steps.append(result)
        mark = "ok " if result.ok else "OFF"
        detail = "; ".join(c["detail"] for c in result.checks if not c["ok"])
        print(f"      {mark} \"{raw['say'][:44]}\" {result.seconds:5.1f}s "
              f"{result.llm_calls} call(s) {detail[:52]}")
        if result.drift:
            print(f"           drift: {'; '.join(result.drift)}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chain", action="append", default=[])
    parser.add_argument("--provider", default="")
    parser.add_argument("--generation-model", default="")
    parser.add_argument("--judge-model", default="")
    parser.add_argument("--effort", default="")
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--no-vision", action="store_true")
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--runs-dir", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    # Before the first case, not after the last one. A missing directory is
    # a typo caught in a second at the start, or half an hour of real model
    # calls thrown away at the end - which is what it was.
    if args.out:
        out_path = Path(args.out)
        try:
            if out_path.parent != Path(""):
                out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.touch()
        except OSError as exc:
            print(f"cannot write to {args.out}: {exc}")
            return 2

    chains = CHAINS
    if args.chain:
        wanted = set(args.chain)
        chains = [c for c in chains if c["id"] in wanted]
    if not chains:
        print("nothing to run")
        return 2

    from app.server.app import RUNS_DIR
    runs_dir = Path(args.runs_dir) if args.runs_dir else RUNS_DIR

    kwargs: dict[str, Any] = {
        "max_iterations": args.iterations,
        "use_vision": not args.no_vision,
        "effort": args.effort,
    }
    for name, value in (("provider", args.provider),
                        ("generation_model", args.generation_model),
                        ("judge_model", args.judge_model)):
        if value:
            kwargs[name] = value
    options = JobOptions(**kwargs)

    results = []
    for index, chain in enumerate(chains, 1):
        print(f"\n[{index}/{len(chains)}] {chain['id']}: {chain['prompt'][:60]}")
        results.append(run_chain(runs_dir, chain, options, args.timeout))

    print(f"\n{'=' * 72}")
    print(f"{'chain':<12} {'base':<6} {'steps held':<12} {'model calls':<12} detail")
    print("-" * 72)
    total_steps = held = 0
    for r in results:
        steps = len(r.steps)
        total_steps += steps
        held += r.survived
        calls = sum(s.llm_calls for s in r.steps)
        drifted = sum(1 for s in r.steps if s.drift)
        note = r.error or (f"{drifted} step(s) drifted" if drifted else "")
        print(f"{r.id:<12} {'ok' if r.base_ok else 'off':<6} "
              f"{r.survived}/{steps:<10} {calls:<12} {note[:36]}")
    print("-" * 72)
    print(f"{held}/{total_steps} edits landed and kept everything before them")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "provider": options.provider,
            "generation_model": options.generation_model,
            "chains": [{
                "id": r.id, "base_ok": r.base_ok, "survived": r.survived,
                "error": r.error,
                "steps": [{"say": s.say, "ok": s.ok, "seconds": round(s.seconds, 1),
                           "llm_calls": s.llm_calls, "drift": s.drift,
                           "error": s.error, "checks": s.checks}
                          for s in r.steps],
            } for r in results],
        }, indent=2), encoding="utf-8")
        print(f"written to {args.out}")
    return 0 if held == total_steps else 1


if __name__ == "__main__":
    raise SystemExit(main())
