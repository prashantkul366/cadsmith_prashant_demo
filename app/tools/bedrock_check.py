"""Check a Bedrock setup before spending anything real on it.

The expensive way to discover that a model id is wrong for your region, or
that your SSO session expired, or that the account has Claude enabled but not
the model you named, is to start a run: five agents, a vision Judge, several
refinement rounds, and a bill for all of it before the failure surfaces.

This does the same discovery for the price of one very small completion.

    .venv/bin/python -m app.tools.bedrock_check
    .venv/bin/python -m app.tools.bedrock_check --region eu-west-1
    .venv/bin/python -m app.tools.bedrock_check --no-call     # never bills

Every step reports separately, so a failure says which one broke rather than
"Bedrock did not work". Nothing here needs an Anthropic key: Bedrock
authenticates with your AWS credentials, resolved by botocore exactly as the
AWS CLI resolves them.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from app.server import budget, providers, tls  # noqa: E402

#: The smallest useful request: a handful of input tokens, a two-token answer.
#: Enough to prove the whole path - credentials, region, model access, quota -
#: without being worth worrying about on any price list.
PROBE = [{"role": "user", "content": "Reply with the single word: ready"}]
PROBE_MAX_TOKENS = 8


def line(ok: bool | None, label: str, detail: str = "") -> None:
    mark = {True: "  ok ", False: "FAIL ", None: "  -- "}[ok]
    print(f"{mark} {label}" + (f": {detail}" if detail else ""), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--region", default="",
                        help="AWS region; otherwise AWS_REGION or your profile")
    parser.add_argument("--profile", default="",
                        help="AWS named profile; otherwise AWS_PROFILE")
    parser.add_argument("--model", default="",
                        help="Bedrock model id to probe; otherwise the app's "
                             "default generation model")
    parser.add_argument("--no-call", action="store_true",
                        help="check credentials and configuration only, and "
                             "never send a request")
    args = parser.parse_args()

    if args.region:
        os.environ["AWS_REGION"] = args.region
    if args.profile:
        os.environ["AWS_PROFILE"] = args.profile

    spec = providers.BUILTIN.get("bedrock")
    if spec is None:
        line(False, "the app knows about Bedrock")
        return 1

    # Both before anything reaches the network. Without the trust store this
    # fails on any corporate network that re-signs TLS, and the failure looks
    # like an empty model list rather than a certificate problem; without
    # .env, a region set only in the file is not seen.
    trust = tls.configure()
    env_file = ROOT / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_file)
        except Exception:
            pass

    print("\nConfiguration")
    line(trust["ok"], "certificate trust", trust["detail"])
    region = os.getenv("AWS_REGION", "")
    line(bool(region), "region",
         region or "not set - export AWS_REGION or pass --region")
    profile = (os.getenv("AWS_PROFILE") or "").strip()
    line(None, "profile", profile or "none (using the default chain)")
    if profile and os.getenv("AWS_ACCESS_KEY_ID"):
        line(None, "note",
             "AWS_PROFILE and AWS_ACCESS_KEY_ID are both set. The profile "
             "wins and the keys are ignored.")

    print("\nCredentials")
    arn, why = providers._aws_check()
    line(bool(arn) and not why, "botocore can resolve credentials",
         providers.mask_arn(arn) if arn
         else why or "resolved, but AWS could not confirm them")
    if why:
        return 1

    config = providers.resolve("bedrock")
    print("\nModels this account can invoke")
    offered, empty_because = providers.bedrock_models()
    for name in offered:
        line(None, name)
    if not offered:
        line(False, "none listed", empty_because)

    model = args.model or config.generation_model
    print("\nModels the app will ask for")
    # `model`, not config.generation_model: with --model given, the config
    # still holds the declared default, and printing that beside a tick
    # computed from the id actually being probed marked a wrong id as fine.
    # Reported, not judged. These were a tick or a cross against the list
    # above, and the cross was wrong: the app calls Bedrock's Messages
    # endpoint through AnthropicBedrockMantle, whose ids carry a bare
    # `anthropic.` prefix, while list_foundation_models and
    # list_inference_profiles describe the older InvokeModel path and answer
    # in `us.` and `global.` inference profiles. The two catalogues do not
    # overlap, so membership says nothing - and a red FAIL under a correct
    # configuration sends people to change a setting that was already right.
    line(None, "generation", model)
    line(None, "judge", config.judge_model)
    if offered and model not in offered:
        line(None, "note",
             f"{model!r} is not in the list above, and is not expected to be. "
             f"That list is the control plane's view of the InvokeModel path; "
             f"the app uses the Messages endpoint, which takes ids like this "
             f"one. Only the probe settles whether it serves.")

    print("\nSpend guard")
    line(True, "token budget per run", f"{budget.DEFAULT_BUDGET:,} tokens")
    rates = budget.rates()
    line(None, "your per-MTok rates",
         f"in ${rates[0]}, out ${rates[1]}" if rates else
         f"not set - optional, from your AWS pricing page, via "
         f"{' and '.join(budget.RATE_ENV)}")

    if args.no_call:
        print("\nStopping before the probe (--no-call). Nothing was billed.")
        return 0

    print(f"\nProbe ({PROBE_MAX_TOKENS} max output tokens)")
    problems = providers.problems(config)
    if problems:
        for problem in problems:
            line(False, "configuration", problem)
        return 1

    # Both of them. The Judge is a different model from the Coder on
    # purpose, so it can 404 on its own - and it does so after a part has
    # been built, which is the most expensive moment to find out.
    # The same walk the app does, per role. Printing one id and calling
    # it a day was what let two wrong guesses through: the account lists
    # `anthropic.`, `us.` and `global.` spellings of one model and serves
    # exactly one of them, and which one is not knowable from the listing.
    roles = [("generation", model, "sonnet")]
    if config.judge_model and config.judge_model != model:
        roles.append(("judge", config.judge_model, "opus"))

    spent = {"input_tokens": 0, "output_tokens": 0, "calls": 0}
    answered: dict[str, str] = {}
    client = providers._build_sdk_client(config)

    for role, asked, family in roles:
        tries = ([asked] if args.model
                 else providers.bedrock_candidates(family, asked))
        for which in tries:
            try:
                response = client.messages.create(
                    model=which, max_tokens=PROBE_MAX_TOKENS,
                    system="Answer in one word.", messages=PROBE)
            except Exception as exc:                   # noqa: BLE001
                unknown = (type(exc).__name__ == "NotFoundError"
                           or providers._NO_SUCH_MODEL.search(str(exc)))
                line(None if unknown else False, f"{role}: {which}",
                     "not served here - trying the next" if unknown
                     else f"{type(exc).__name__}: {exc}")
                if unknown:
                    continue        # exactly what the app does
                break
            text = "".join(getattr(b, "text", "")
                           for b in response.content).strip()
            line(True, f"{role}: {which}", f"replied {text!r}")
            answered[role] = which
            usage = getattr(response, "usage", None)
            if usage is not None:
                spent["input_tokens"] += usage.input_tokens
                spent["output_tokens"] += usage.output_tokens
                spent["calls"] += 1
            break

    if len(answered) == len(roles):
        line(None, "these probes spent",
             f"{spent['input_tokens']} in, {spent['output_tokens']} out")
        cost = budget.estimate(spent)
        if cost is not None:
            line(None, "at your rates", f"${cost:.6f}")
        print("\nBedrock is reachable. The app will use:")
        for role, which in answered.items():
            print(f"  {role:<11s} {which}")
        return 0

    # Only reached when a role had no id that answered.
    print("\n  A validation error naming the model usually means the id "
          "\n  is not available in this region, or the account has not "
          "\n  been granted access to it. `aws bedrock list-foundation-models"
          "\n  --region " + (region or "<region>") + "` lists what you can "
          "actually call;"
          "\n  models needing a cross-region inference profile are listed by"
          "\n  `aws bedrock list-inference-profiles`.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
