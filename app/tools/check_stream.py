"""Confirm the real SDK streams the event shapes the app expects.

The app's streaming path is covered by tests that use a fake SDK, which can
only prove the logic matches the fake. This makes ONE real call and reports the
event and delta types the SDK actually produces, so the assumption itself is
checked against the live service.

Prints no credentials and no prompt content beyond a trivial fixed request.

Run:  python -m app.tools.check_stream
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def main() -> int:
    backend = os.getenv("LLM_BACKEND", "bedrock").strip().lower()
    model = os.getenv("CODER_MODEL") or (
        "anthropic.claude-sonnet-5" if backend == "bedrock" else "claude-sonnet-5")
    region = os.getenv("AWS_REGION", "us-east-1")

    print(f"backend={backend}  model={model}"
          + (f"  region={region}" if backend == "bedrock" else ""))

    if backend == "bedrock":
        from anthropic import AnthropicBedrockMantle
        client = AnthropicBedrockMantle(aws_region=region)
    else:
        import anthropic
        client = anthropic.Anthropic()

    kwargs = {
        "model": model,
        "max_tokens": 8192,
        "thinking": {"type": "adaptive", "display": "summarized"},
        "messages": [{"role": "user", "content":
                      "In one sentence, why is a box() call enough for a "
                      "50x30x20mm block in CadQuery?"}],
    }

    events = Counter()
    deltas = Counter()
    thinking_chars = 0
    text_chars = 0

    try:
        with client.messages.stream(**kwargs) as stream:
            for event in stream:
                events[getattr(event, "type", "?")] += 1
                if getattr(event, "type", "") != "content_block_delta":
                    continue
                delta = getattr(event, "delta", None)
                kind = getattr(delta, "type", "?")
                deltas[kind] += 1
                if kind == "thinking_delta":
                    thinking_chars += len(getattr(delta, "thinking", "") or "")
                elif kind == "text_delta":
                    text_chars += len(getattr(delta, "text", "") or "")
            final = stream.get_final_message()
    except Exception as exc:
        print(f"\nFAILED: {type(exc).__name__}: {exc}")
        if "thinking" in str(exc).lower():
            print("  -> this model rejects the thinking parameter; the app "
                  "falls back automatically, but pick a Claude 4.6+ model to "
                  "see reasoning.")
        return 1

    print("\nstream event types:")
    for name, n in events.most_common():
        print(f"  {name:<28} {n}")
    print("\ncontent_block_delta types:")
    for name, n in deltas.most_common():
        print(f"  {name:<28} {n}")

    print(f"\nthinking characters streamed : {thinking_chars}")
    print(f"text characters streamed     : {text_chars}")
    print(f"stop_reason                  : {getattr(final, 'stop_reason', None)}")
    print(f"usage                        : in={final.usage.input_tokens} "
          f"out={final.usage.output_tokens}")

    ok_text = deltas.get("text_delta", 0) > 0
    ok_think = deltas.get("thinking_delta", 0) > 0
    print("\n" + "=" * 58)
    print(f"  text_delta handled by the app     : "
          f"{'YES' if ok_text else 'NO - the code panel would stay empty'}")
    print(f"  thinking_delta handled by the app : "
          f"{'YES' if ok_think else 'NO - the Reasoning panel would be empty'}")
    if ok_text and ok_think:
        print("  The app's assumptions match the live SDK.")
        return 0
    print("  MISMATCH - send this output back so the handler can be corrected.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
