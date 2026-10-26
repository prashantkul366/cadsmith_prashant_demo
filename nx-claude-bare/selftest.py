"""Checks that run here, with no NX and no AWS account.

    python check.py

Three things are worth checking before this folder is carried to a
machine with NX on it, and all three can be checked without one.

1. The signature. This is the only part that cannot be verified by
   reading it: AWS either agrees with the signature or answers 403 and
   says nothing useful. So the same request is signed by `sigv4.py` and
   by botocore, with the same fake key and the same frozen clock, and the
   two Authorization headers are compared character by character. If
   botocore is not installed the check says so and is skipped - it is a
   check on this folder, not a dependency of it.

2. The request. What goes to Bedrock is captured instead of sent, and
   read back: the model id in the path, the wire version, the tools, the
   thinking flag when it is asked for.

3. The loop. `bare.conversation` is run against a fake NX and a scripted
   model, so the message bookkeeping - who said what, which tool_result
   belongs to which tool_use, what an error looks like - is checked
   without spending a penny or opening NX.

What none of this checks is whether the NX calls in `nxside.py` are
right. They cannot be checked here. That is what the first run on a real
part is for, and why `read_tree` is the one to run first.
"""

import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import bare
import bedrock
import nxside
import sigv4

# AWS's own published example key and secret, from the SigV4 test suite.
# Not a credential, and nothing is ever sent with them: the signature is
# computed and compared, never posted.
FAKE = sigv4.Credentials("AKIDEXAMPLE",
                         "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY")
FAKE_WITH_TOKEN = sigv4.Credentials(FAKE.key, FAKE.secret, "FQoDYXdzEPT//tok")
FROZEN = datetime.datetime(2026, 3, 9, 11, 22, 33)

failures = []


def check(what, condition, detail=""):
    print(("  ok   " if condition else "  FAIL ") + what
          + (("  " + detail) if detail and not condition else ""))
    if not condition:
        failures.append(what)


# --------------------------------------------------------------------
# 1. the signature, against botocore
# --------------------------------------------------------------------

def botocore_signature(method, url, body, headers, creds, where):
    """What botocore makes of the same request, at the same instant."""
    import botocore.auth
    import botocore.awsrequest
    import botocore.credentials

    held = botocore.auth.get_current_datetime
    botocore.auth.get_current_datetime = lambda: FROZEN
    try:
        request = botocore.awsrequest.AWSRequest(
            method=method, url=url, data=body, headers=dict(headers))
        auth = botocore.auth.SigV4Auth(
            botocore.credentials.Credentials(
                creds.key, creds.secret, creds.token or None),
            "bedrock", where)
        auth.add_auth(request)
        return dict(request.headers)
    finally:
        botocore.auth.get_current_datetime = held


def check_signature():
    print("signature, against botocore:")
    try:
        import botocore.auth  # noqa: F401
    except ImportError:
        print("  skip  botocore is not installed here, so there is nothing "
              "to compare against")
        return

    cases = [
        ("a plain model id", "anthropic.claude-sonnet-5", FAKE),
        ("a versioned id, which has a colon in it",
         "anthropic.claude-3-5-sonnet-20241022-v2:0", FAKE),
        ("a geography-prefixed id",
         "us.anthropic.claude-sonnet-4-5-20250929-v1:0", FAKE),
        ("a session token in play", "anthropic.claude-sonnet-5",
         FAKE_WITH_TOKEN),
    ]
    for what, which, creds in cases:
        for where in ("us-east-1", "ap-south-1"):
            url = bedrock._url(where, which)
            body = json.dumps({"anthropic_version": bedrock.WIRE,
                               "max_tokens": 64,
                               "messages": [{"role": "user",
                                             "content": "hello"}]}
                              ).encode("utf-8")
            sent = {"Content-Type": "application/json",
                    "Accept": "application/json"}
            ours = sigv4.sign("POST", url, body, sent, creds,
                              where=where, now=FROZEN)
            theirs = botocore_signature("POST", url, body, sent, creds, where)
            check("%s in %s" % (what, where),
                  ours["Authorization"] == theirs["Authorization"],
                  "\n         ours:   %s\n         theirs: %s"
                  % (ours["Authorization"], theirs["Authorization"]))
            check("%s in %s: date header" % (what, where),
                  ours["X-Amz-Date"] == theirs["X-Amz-Date"])
            if creds.token:
                check("%s in %s: token header" % (what, where),
                      ours["X-Amz-Security-Token"]
                      == theirs["X-Amz-Security-Token"])


# --------------------------------------------------------------------
# 2. the request that would go to Bedrock
# --------------------------------------------------------------------

def check_request():
    print("the request Bedrock would get:")
    captured = {}

    def capture(url, body, headers, timeout=180):
        captured["url"] = url
        captured["body"] = json.loads(body.decode("utf-8"))
        captured["headers"] = headers
        return json.dumps({"content": [{"type": "text", "text": "hi"}],
                           "stop_reason": "end_turn"}).encode("utf-8")

    held_post, sigv4.post = sigv4.post, capture
    held_env = dict(os.environ)
    os.environ["AWS_ACCESS_KEY_ID"] = FAKE.key
    os.environ["AWS_SECRET_ACCESS_KEY"] = FAKE.secret
    os.environ["AWS_REGION"] = "ap-south-1"
    os.environ["BARE_MODEL"] = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    os.environ.pop("BARE_THINKING", None)
    try:
        reply = bedrock.ask([{"role": "user", "content": "say hi"}],
                            tools=nxside.TOOLS, system="be brief")
        check("the model id rides in the path, its colon encoded the way "
              "boto3 encodes it",
              captured["url"].endswith(
                  "/model/anthropic.claude-3-5-sonnet-20241022-v2%3A0/invoke"),
              captured["url"])
        check("the region is the one in the environment",
              "bedrock-runtime.ap-south-1.amazonaws.com" in captured["url"],
              captured["url"])
        check("the body carries Bedrock's wire version",
              captured["body"]["anthropic_version"] == bedrock.WIRE)
        check("the five tools are offered",
              [tool["name"] for tool in captured["body"]["tools"]]
              == ["read_tree", "set_expression", "suppress_feature",
                  "delete_feature", "nx_python"])
        check("the system prompt is sent",
              captured["body"]["system"] == "be brief")
        check("thinking is off unless asked for",
              "thinking" not in captured["body"])
        check("the request is signed",
              captured["headers"]["Authorization"].startswith(
                  "AWS4-HMAC-SHA256 Credential=" + FAKE.key))
        check("the reply comes back parsed",
              bedrock.text_of(reply) == "hi")

        os.environ["BARE_THINKING"] = "1"
        bedrock.ask([{"role": "user", "content": "think"}])
        check("thinking is adaptive when asked for, with no budget",
              captured["body"].get("thinking") == {"type": "adaptive"})
    finally:
        sigv4.post = held_post
        os.environ.clear()
        os.environ.update(held_env)


# --------------------------------------------------------------------
# 3. the loop, against a fake NX and a scripted model
# --------------------------------------------------------------------

class FakeNX(object):
    """An NX that is a dictionary of expressions and nothing else."""

    TOOLS = nxside.TOOLS

    def __init__(self):
        self.values = {"p7": 12.0}
        self.done = []

    def perform(self, name, arguments):
        self.done.append((name, arguments))
        if name == "read_tree":
            return {"ok": True, "expressions":
                    [{"name": key, "value": value}
                     for key, value in sorted(self.values.items())]}
        if name == "set_expression":
            if arguments["name"] not in self.values:
                return {"ok": False, "why": "no expression called "
                                            + repr(arguments["name"])}
            self.values[arguments["name"]] = float(arguments["value"])
            return {"ok": True}
        return {"ok": False, "why": "no such tool"}


def scripted(*replies):
    """A model that says these things in order, ignoring what it is told."""
    said = list(replies)
    asked = []

    def ask(messages, tools=None, system=None, max_tokens=4096):
        asked.append((messages, tools, system))
        return said.pop(0) if said else {
            "content": [{"type": "text", "text": "nothing left to say"}],
            "stop_reason": "end_turn"}
    ask.asked = asked
    return ask


def use(identifier, name, arguments):
    return {"content": [{"type": "tool_use", "id": identifier,
                         "name": name, "input": arguments}],
            "stop_reason": "tool_use"}


def check_loop():
    print("the loop, against a fake NX:")
    nx = FakeNX()
    ask = scripted(
        use("a", "read_tree", {}),
        use("b", "set_expression", {"name": "p9", "value": 20}),
        use("c", "set_expression", {"name": "p7", "value": 20}),
        {"content": [{"type": "text", "text": "p7 is 20 now."}],
         "stop_reason": "end_turn"},
    )
    lines = []
    messages = bare.conversation(nx, ask, "make p7 twenty",
                                 note=lines.append)

    check("every tool call was performed, in order",
          [name for name, _ in nx.done]
          == ["read_tree", "set_expression", "set_expression"], str(nx.done))
    check("the part actually changed", nx.values["p7"] == 20.0,
          str(nx.values))
    check("the task is the first message",
          messages[0] == {"role": "user", "content": "make p7 twenty"})
    check("the turns alternate",
          [message["role"] for message in messages]
          == ["user", "assistant", "user", "assistant", "user",
              "assistant", "user"],
          str([message["role"] for message in messages]))

    results = [block for message in messages
               if isinstance(message.get("content"), list)
               for block in message["content"]
               if block.get("type") == "tool_result"]
    check("each result is tied to the call it answers",
          [result["tool_use_id"] for result in results] == ["a", "b", "c"])
    check("a refusal is marked as an error",
          [result["is_error"] for result in results] == [False, True, False],
          str([result["is_error"] for result in results]))
    check("the refusal reached the model as a refusal",
          "no expression called 'p9'" in results[1]["content"])
    check("the system prompt went with every call",
          all(system == bare.SYSTEM for _, _, system in ask.asked))
    check("the transcript names the tools and the answers",
          any("read_tree" in line for line in lines)
          and any("p7 is 20 now." in line for line in lines))

    print("the loop, when the model never stops:")
    nx = FakeNX()
    ask = scripted(*([use("x", "read_tree", {})] * 40))
    lines = []
    bare.conversation(nx, ask, "loop forever", rounds=3, note=lines.append)
    check("it gives up after the rounds it was given",
          len([one for one in nx.done if one[0] == "read_tree"]) == 3,
          str(len(nx.done)))
    check("and says that is why it stopped",
          any("stopped after 3 rounds" in line for line in lines))

    print("the loop, when the model runs out of output:")
    nx = FakeNX()
    lines = []
    bare.conversation(nx, scripted({"content": [], "stop_reason":
                                    "max_tokens"}), "x", note=lines.append)
    check("it says so rather than looking finished",
          any("ran out of output tokens" in line for line in lines))


# --------------------------------------------------------------------
# 4. the NX side, as far as it can be checked without NX
# --------------------------------------------------------------------

def check_nxside():
    print("the NX side, without NX:")
    check("an unknown tool is refused, not raised",
          nxside.perform("fly", {})["ok"] is False)
    answer = nxside.perform("read_tree", {})
    check("no NX means a refusal with NX's own words, not a traceback "
          "out of the journal",
          answer["ok"] is False and "NXOpen" in answer["why"],
          json.dumps(answer)[:200])

    held = dict(os.environ)
    os.environ["BARE_DRY"] = "1"
    try:
        check("BARE_DRY is read", nxside.dry() is True)
        for name, arguments, wanted in (
                ("set_expression", {"name": "p7", "value": 20}, "p7 = 20"),
                ("suppress_feature", {"name": "Hole(3)"}, "suppress Hole(3)"),
                ("delete_feature", {"name": "Hole(3)"}, "delete Hole(3)"),
                ("nx_python", {"code": "workPart.Expressions"},
                 "workPart.Expressions")):
            answer = nxside.perform(name, arguments)
            check("BARE_DRY stops %s and reports what it would have done"
                  % name,
                  answer["ok"] is False and answer.get("would") == wanted,
                  json.dumps(answer)[:200])
    finally:
        os.environ.clear()
        os.environ.update(held)


def main():
    check_signature()
    check_request()
    check_loop()
    check_nxside()
    print("")
    if failures:
        print("%d check%s failed:" % (len(failures),
                                      "" if len(failures) == 1 else "s"))
        for one in failures:
            print("  - " + one)
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
