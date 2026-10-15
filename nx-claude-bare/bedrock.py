"""One Bedrock call, and nothing else.

This is the whole model layer: build the body Bedrock's Anthropic
endpoint expects, sign it, post it, hand back the parsed reply. No
retries, no streaming, no client object, no state. If a call fails the
error says what AWS said and the journal stops, which is what you want
the first time you run this on a machine nobody has run it on before.

The model id is the thing most likely to be wrong, so it is one
environment variable and the error message from a bad one is passed
through intact. A 404 from Bedrock means the account cannot call that
exact id - usually a version or an inference-profile prefix, not a typo -
and it is worth reading before changing anything else.
"""

import json
import os
import urllib.parse

import sigv4

#: What the handlebar bench on this account already calls successfully.
#: Override with BARE_MODEL. us-east-1 wants a bare `anthropic.` prefix;
#: some accounts need a geography prefix instead (`us.anthropic....`),
#: which is the first thing to try if the call comes back 404.
DEFAULT_MODEL = "anthropic.claude-sonnet-5"

#: Bedrock's name for "the body is in Anthropic's own format". It is not
#: a model version and it does not change when the model does.
WIRE = "bedrock-2023-05-31"


def model():
    return os.environ.get("BARE_MODEL", "").strip() or DEFAULT_MODEL


def _url(where, which):
    """Where InvokeModel lives, with the model id as one path segment.

    The id is percent-encoded because some of them carry a colon -
    `...-v2:0` - and that has to go on the wire as %3A. boto3 does the
    same, which is what `check.py` compares against; sending the raw
    colon instead is a 403 that looks like a credentials problem.
    """
    return "https://bedrock-runtime.%s.amazonaws.com/model/%s/invoke" % (
        where, urllib.parse.quote(which, safe=""))


def ask(messages, tools=None, system=None, max_tokens=4096):
    """Send the conversation, get Claude's reply back as a dict.

    The reply is Anthropic's own message shape - `content` a list of
    blocks, `stop_reason` saying whether it wants a tool - because that
    is what Bedrock returns here unchanged.
    """
    body = {
        "anthropic_version": WIRE,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system:
        body["system"] = system
    if tools:
        body["tools"] = tools
    if os.environ.get("BARE_THINKING", "").strip() in ("1", "yes", "true"):
        # Worth turning on once the plain path works: it is the
        # difference between a model that guesses at a tree and one that
        # reasons about it. Left off by default because a deployment that
        # does not accept the field answers 400, and the first run should
        # fail for interesting reasons only.
        body["thinking"] = {"type": "adaptive"}

    raw = json.dumps(body).encode("utf-8")
    where = sigv4.region()
    url = _url(where, model())
    headers = sigv4.sign(
        "POST", url, raw,
        {"Content-Type": "application/json", "Accept": "application/json"},
        sigv4.credentials(), where=where)
    return json.loads(sigv4.post(url, raw, headers).decode("utf-8"))


def text_of(reply):
    """Just the words, for printing."""
    said = []
    for block in reply.get("content") or []:
        if block.get("type") == "text" and block.get("text", "").strip():
            said.append(block["text"].strip())
        elif block.get("type") == "thinking" and block.get("thinking"):
            said.append("(thinking) " + block["thinking"].strip())
    return "\n".join(said)


def tool_calls(reply):
    """The tool_use blocks, in the order Claude asked for them."""
    return [block for block in (reply.get("content") or [])
            if block.get("type") == "tool_use"]
