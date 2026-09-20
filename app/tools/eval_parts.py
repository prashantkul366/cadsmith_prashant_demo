"""Score the app against a fixed set of prompts, so a change can be judged.

Every improvement from here on is a change to a prompt, a schema or a check,
and those are the highest-variance edits there are: one wording can lift a
whole family of parts or quietly break another.  Without a number measured
the same way twice, "this is better now" is a feeling.

What is scored is only what a kernel can settle - bounding box, hole count,
bore diameters, volume, whether the solid is watertight - read back out of
the exported STEP by ``server.spec``.  No model grades another model here.
That keeps the score boring and therefore comparable: two runs of this tool a
month apart differ because the app changed, not because a judge was in a
different mood.

Cases live in ``eval_prompts.json`` beside this file.

    python -m app.tools.eval_parts                        # every case
    python -m app.tools.eval_parts --case cylinder-bore   # one, by id
    python -m app.tools.eval_parts --catalogue-only       # no model calls, free
    python -m app.tools.eval_parts --effort low --provider bedrock
    python -m app.tools.eval_parts --baseline runs/eval-before.json

**This spends real money** on a metered backend - twenty parts, each a
Planner, a Coder and a Judge, plus refinement.  ``--catalogue-only`` runs the
seven standard-part cases, which cost nothing, and is the right smoke test
before paying for the rest.
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
from app.server.jobs import (  # noqa: E402
    JobManager, JobOptions, STATUS_DONE, STATUS_ERROR)

CASES_FILE = Path(__file__).with_name("eval_prompts.json")
DEFAULT_VOLUME_PCT = 10.0

#: How close a measured length has to be to a stated one. Deliberately not
#: server.spec's own tolerance: this asks "did it build what was asked for",
#: a coarser question than the one the Judge asks inside a run.
LENGTH_TOL_MM = 0.6
LENGTH_TOL_FRAC = 0.02


@dataclass
class CaseResult:
    id: str
    prompt: str
    built: bool = False
    converged: bool = False
    catalogue: bool = False
    checks: list[dict] = field(default_factory=list)
    seconds: float = 0.0
    iterations: int = 0
    llm_calls: int = 0
    tokens: int = 0
    error: str = ""

    @property
    def matched(self) -> int:
        return sum(1 for c in self.checks if c["ok"])

    @property
    def total(self) -> int:
        return len(self.checks)

    @property
    def passed(self) -> bool:
        """Built, watertight, and every stated expectation met."""
        return self.built and self.total > 0 and self.matched == self.total

    def to_dict(self) -> dict:
        return {
            "id": self.id, "prompt": self.prompt, "built": self.built,
            "converged": self.converged, "catalogue": self.catalogue,
            "passed": self.passed, "matched": self.matched,
            "total": self.total, "checks": self.checks,
            "seconds": round(self.seconds, 1), "iterations": self.iterations,
            "llm_calls": self.llm_calls, "tokens": self.tokens,
            "error": self.error,
        }


def _near(actual: float, target: float) -> bool:
    return abs(actual - target) <= max(LENGTH_TOL_MM, abs(target) * LENGTH_TOL_FRAC)


def _check(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def score(expect: dict, measured: dict, catalogue_served: bool) -> list[dict]:
    """Every expectation the measurements can settle, as a pass/fail row."""
    checks: list[dict] = [
        _check("watertight", measured.get("is_valid", False),
               "valid solid" if measured.get("is_valid") else "NOT watertight")
    ]

    box = expect.get("bbox")
    if box:
        got = measured["bbox"]
        for axis, want in zip(("xlen", "ylen", "zlen"), box):
            if want is None:      # the prompt did not fix this axis
                continue
            actual = got[axis]
            checks.append(_check(
                f"bbox {axis}", _near(actual, float(want)),
                f"{actual:.2f} vs {float(want):.2f} mm"))

    holes = expect.get("holes")
    if holes is not None:
        actual = measured["num_holes"]
        checks.append(_check("hole count", actual == int(holes),
                             f"{actual} vs {int(holes)}"))

    wanted_bores = expect.get("bore_dia")
    if wanted_bores:
        # Each wanted diameter must be matched by a distinct measured bore,
        # so a part with one hole cannot satisfy a request for six.
        remaining = list(measured["holes"])
        missing = []
        for want in wanted_bores:
            hit = next((d for d in remaining if _near(d, float(want))), None)
            if hit is None:
                missing.append(float(want))
            else:
                remaining.remove(hit)
        checks.append(_check(
            "bore diameters", not missing,
            "all present" if not missing
            else f"missing {', '.join(f'{d:g}' for d in missing)} mm "
                 f"(measured {', '.join(f'{d:.2f}' for d in measured['holes']) or 'none'})"))

    volume = expect.get("volume_mm3")
    if volume is not None:
        pct = float(expect.get("volume_pct", DEFAULT_VOLUME_PCT))
        actual = measured["volume"]
        off = abs(actual - float(volume)) / float(volume) * 100.0
        checks.append(_check("volume", off <= pct,
                             f"{actual:.0f} vs {float(volume):.0f} mm³ ({off:.1f}% off)"))

    if expect.get("catalogue"):
        checks.append(_check(
            "served from the catalogue", catalogue_served,
            "no model call" if catalogue_served else "went to the agents"))

    return checks


def run_case(manager: JobManager, case: dict, options: JobOptions,
             timeout: float) -> CaseResult:
    result = CaseResult(id=case["id"], prompt=case["prompt"])
    started = time.time()
    job = manager.create(case["prompt"], options)

    deadline = started + timeout
    while job.status not in (STATUS_DONE, STATUS_ERROR):
        if time.time() > deadline:
            result.error = f"timed out after {timeout:.0f}s"
            result.seconds = time.time() - started
            return result
        time.sleep(0.4)

    result.seconds = time.time() - started
    result.converged = bool(job.converged)
    result.iterations = len(job.versions)
    result.llm_calls = int(job.llm_calls or 0)
    result.tokens = sum(
        int(v or 0) for key, v in (job.tokens or {}).items()
        if key in ("input_tokens", "output_tokens"))
    # A catalogue answer costs no model call at all; that is the whole point
    # of it, and it is the cheapest thing in here to regress without noticing.
    result.catalogue = result.llm_calls == 0 and job.status == STATUS_DONE

    if job.status == STATUS_ERROR or not job.versions:
        result.error = job.error or "no version was produced"
        return result

    step = manager.artifact_path(job.id, job.versions[-1].get("iteration", 0),
                                 "model.step")
    if step is None or not step.is_file():
        result.error = "the run produced no STEP to measure"
        return result

    try:
        measured = spec.measure_step(step)
    except Exception as exc:                        # a STEP that will not read
        result.error = f"could not measure: {type(exc).__name__}: {exc}"
        return result

    result.built = True
    result.checks = score(case.get("expect") or {}, measured, result.catalogue)
    return result


def report(results: list[CaseResult], baseline: Optional[dict]) -> dict:
    built = [r for r in results if r.built]
    passed = [r for r in results if r.passed]
    rows = sum(r.total for r in results)
    hits = sum(r.matched for r in results)
    paid = [r for r in results if not r.catalogue]

    summary = {
        "cases": len(results),
        "built": len(built),
        "passed": len(passed),
        "checks": rows,
        "checks_passed": hits,
        "mean_seconds": round(sum(r.seconds for r in results) / max(1, len(results)), 1),
        "mean_seconds_paid": round(
            sum(r.seconds for r in paid) / max(1, len(paid)), 1),
        "total_tokens": sum(r.tokens for r in results),
        "total_llm_calls": sum(r.llm_calls for r in results),
    }

    print(f"\n{'=' * 72}")
    print(f"{'case':<22} {'build':<7} {'checks':<9} {'time':>7} {'calls':>6}  detail")
    print("-" * 72)
    for r in results:
        state = "ok" if r.built else "FAILED"
        checks = f"{r.matched}/{r.total}" if r.total else "-"
        mark = "PASS" if r.passed else ("fail" if r.built else "----")
        detail = r.error
        if not detail:
            bad = [c for c in r.checks if not c["ok"]]
            detail = "; ".join(f"{c['name']}: {c['detail']}" for c in bad[:2])
        print(f"{r.id:<22} {state:<7} {checks:<9} {r.seconds:>6.1f}s "
              f"{r.llm_calls:>6}  {mark}  {detail[:60]}")

    print("-" * 72)
    print(f"built {summary['built']}/{summary['cases']}   "
          f"fully correct {summary['passed']}/{summary['cases']}   "
          f"checks {summary['checks_passed']}/{summary['checks']}")
    print(f"mean {summary['mean_seconds']}s per case "
          f"({summary['mean_seconds_paid']}s for the ones that call a model), "
          f"{summary['total_tokens']} tokens over {summary['total_llm_calls']} calls")

    if baseline:
        before = baseline.get("summary", {})
        def delta(key: str, label: str, unit: str = "") -> None:
            was, now = before.get(key), summary.get(key)
            if was is None or now is None:
                return
            change = now - was
            arrow = "=" if change == 0 else ("+" if change > 0 else "")
            print(f"  {label:<26} {was}{unit} -> {now}{unit}  ({arrow}{change:g})")
        print("\nagainst the baseline")
        delta("passed", "fully correct")
        delta("built", "built at all")
        delta("checks_passed", "checks passed")
        delta("mean_seconds_paid", "mean seconds (paid)", "s")
        delta("total_tokens", "tokens")

        was_by_id = {c["id"]: c for c in baseline.get("cases", [])}
        regressed = [r.id for r in results
                     if was_by_id.get(r.id, {}).get("passed") and not r.passed]
        fixed = [r.id for r in results
                 if r.passed and was_by_id.get(r.id, {}).get("passed") is False]
        if regressed:
            print(f"  REGRESSED: {', '.join(regressed)}")
        if fixed:
            print(f"  newly correct: {', '.join(fixed)}")

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", default=[],
                        help="run only this case id (repeatable)")
    parser.add_argument("--catalogue-only", action="store_true",
                        help="only the cases the catalogue answers - no spend")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--provider", default="")
    parser.add_argument("--generation-model", default="")
    parser.add_argument("--judge-model", default="")
    parser.add_argument("--effort", default="", help="low, medium or high")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--no-vision", action="store_true")
    parser.add_argument("--timeout", type=float, default=900.0,
                        help="seconds one case may take")
    parser.add_argument("--runs-dir", default="")
    parser.add_argument("--out", default="", help="write the scored run here")
    parser.add_argument("--baseline", default="",
                        help="an earlier --out file to compare against")
    args = parser.parse_args()

    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))["cases"]
    if args.catalogue_only:
        cases = [c for c in cases if (c.get("expect") or {}).get("catalogue")]
    if args.case:
        wanted = set(args.case)
        cases = [c for c in cases if c["id"] in wanted]
        missing = wanted - {c["id"] for c in cases}
        if missing:
            print(f"no such case: {', '.join(sorted(missing))}")
            return 2
    if args.limit:
        cases = cases[:args.limit]
    if not cases:
        print("nothing to run")
        return 2

    baseline = None
    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))

    from app.server.app import RUNS_DIR      # the app's own runs directory
    manager = JobManager(Path(args.runs_dir) if args.runs_dir else RUNS_DIR)

    kwargs: dict[str, Any] = {
        "max_iterations": args.iterations,
        "use_vision": not args.no_vision,
        "effort": args.effort,
    }
    if args.provider:
        kwargs["provider"] = args.provider
    if args.generation_model:
        kwargs["generation_model"] = args.generation_model
    if args.judge_model:
        kwargs["judge_model"] = args.judge_model
    options = JobOptions(**kwargs)

    print(f"{len(cases)} case(s), provider {options.provider}"
          + (f", effort {options.effort}" if options.effort else ""))

    results = []
    for index, case in enumerate(cases, 1):
        print(f"\n[{index}/{len(cases)}] {case['id']}: {case['prompt'][:64]}")
        result = run_case(manager, case, options, args.timeout)
        results.append(result)
        state = "PASS" if result.passed else ("built" if result.built else "FAILED")
        print(f"      {state} in {result.seconds:.1f}s"
              + (f" - {result.error}" if result.error else ""))

    summary = report(results, baseline)

    payload = {
        "when": time.strftime("%Y-%m-%d %H:%M:%S"),
        "provider": options.provider,
        "generation_model": options.generation_model,
        "judge_model": options.judge_model,
        "effort": options.effort,
        "iterations": options.max_iterations,
        "summary": summary,
        "cases": [r.to_dict() for r in results],
    }
    if args.out:
        Path(args.out).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nwritten to {args.out}")

    # A non-zero exit means something did not build at all, which is a
    # different kind of problem from a part that built and missed a dimension.
    return 0 if all(r.built for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
