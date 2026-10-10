"""Fitting a reply beside a prompt in a window that will not hold both.

A self-hosted model has a window measured in tens of thousands of tokens,
not hundreds, and the Coder asks for a ceiling big enough to write a whole
program without being cut off. The two meet, and the endpoint answers 400.

The reply to that is arithmetic, not a guess - the endpoint says how big
its window is and roughly how big the prompt is - but its "your prompt
contains **at least** N input tokens" is a lower bound that can be out by
a factor of two. Across one run of the 61-prompt library, sixteen died
here: four refusals in a row, four minutes each, and then a sentence
asserting which part did not fit that the loop had no way of knowing.

So this drives the loop against a fake endpoint with a known window and a
known prompt, and checks both things that matter: that it converges on a
ceiling that fits, and that it does not hand the Coder less room than
there really is - a program cut off mid-function is a failed run, not a
cheaper one.

Run:  .venv/bin/python -m app.tests.test_context_fit
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.server import providers  # noqa: E402
from app.server.providers import LLMConfig  # noqa: E402

#: The FreeCAD branch carries a tool channel through every call, so its
#: _post_once answers with a third element. One file, both shapes.
_TOOLS = hasattr(providers, "ToolCall")


def drive(window: int, prompt: int, admits: int, ceiling: int):
    """``(ceilings tried, "fitted" or the error)`` for one fake endpoint.

    ``prompt`` is how big the prompt really is; ``admits`` is the number
    the endpoint puts in its refusal, which is allowed to be smaller.
    """
    tried: list[int] = []

    class Fake(providers.OpenAICompatibleClient):
        def __init__(self) -> None:
            self.config = LLMConfig(
                provider="custom", kind="openai_compatible",
                base_url="http://fake/v1", api_key="k",
                generation_model="m", judge_model="m")
            self._on_note = None
            self._stream_ok = False

        def _note(self, message: str) -> None:
            pass

        # `tools` only on the branch that has a tool channel; accepted
        # here either way so one test file serves both.
        def _post_once(self, model, messages, max_tokens,
                       role="generation", tools=None):
            tried.append(max_tokens)
            if prompt + max_tokens > window:
                raise providers._ContextTooLong(
                    window, admits,
                    f"This model's maximum context length is {window} "
                    f"tokens. However, you requested {max_tokens} output "
                    f"tokens and your prompt contains at least {admits} "
                    f"input tokens.")
            return ("ok", None, []) if _TOOLS else ("ok", None)

    try:
        Fake()._post_fitted("m", [], ceiling)
        return tried, "fitted"
    except RuntimeError as exc:
        return tried, str(exc)


def main() -> int:
    failures = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        if not ok:
            failures += 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}"
              + (f" - {detail}" if detail else ""))

    print("Both of the endpoint's ways of saying no")
    for said, want in (
            ("This model's maximum context length is 32768 tokens. However, "
             "you requested 16000 output tokens and your prompt contains at "
             "least 16769 input tokens.", (32768, 16769)),
            # The same refusal with the prompt left out. Unrecognised, this
            # one was fatal where its twin was merely refittable.
            ("max_tokens=200000 cannot be greater than max_model_len=32768. "
             "Please request fewer output tokens.", (32768, 0)),
    ):
        full = providers._window_refusal(said)
        check(said[:48], full is not None
              and (full.window, full.prompt_tokens) == want,
              f"{(full.window, full.prompt_tokens)}" if full else "no match")
    check("and a 400 that is about something else is left alone",
          providers._window_refusal("you must provide a model parameter")
          is None)

    print("\nFitting the ceiling to the window")
    tried, how = drive(32768, 16769, 16769, 16000)
    check("an honest report is believed, and believed once", how == "fitted"
          and len(tried) == 2, f"{tried} -> {how[:40]}")
    # The whole point of the raised ceiling: ask for every token that fits.
    check("and it asks for the room there is, not half of it",
          tried[-1] > 15000, str(tried[-1]))

    tried, how = drive(32768, 30000, 16769, 16000)
    check("a report out by a factor of two still converges",
          how == "fitted", f"{tried} -> {how[:40]}")
    check("by halving once the arithmetic has been refused",
          tried[1] > tried[2] > tried[3], str(tried))

    tried, how = drive(200000, 5000, 5000, 16000)
    check("a window with room to spare is not refitted at all",
          how == "fitted" and tried == [16000], str(tried))

    print("\nWhen no reply fits, it says so in the endpoint's own words")
    tried, how = drive(32768, 32500, 32500, 16000)
    check("a prompt that nearly fills the window stops at once",
          how != "fitted" and len(tried) == 1, str(tried))
    check("quoting what the endpoint said, not a sentence written in advance",
          "maximum context length is 32768" in how, how[:70])
    tried, how = drive(32768, 33000, 32000, 16000)
    check("a prompt past the window gives up quickly too",
          how != "fitted" and len(tried) <= 3, str(tried))

    print("\n" + "=" * 58)
    print("ALL CHECKS PASSED" if not failures else f"{failures} CHECK(S) FAILED")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
