"""The journal. Run this one from inside NX.

    File -> Execute -> NX Open...  and pick this file.

It reads the task from `prompt.txt` beside it, hands it to Claude with
the five tools in `nxside.py`, performs whatever Claude asks for, hands
back what happened, and repeats until Claude stops asking. The whole
conversation goes into NX's Information window and into
`bare-transcript.txt` beside this file.

That is all of it. There is no planner, no retry, no repair, no library
of CAD operations, no state kept between runs. The loop below is about
forty lines and every one of them is here to carry a message or a tool
result; nothing in it knows anything about CAD.

`conversation` takes the NX module and the ask-Claude function as
arguments rather than reaching for them, which is what lets `check.py`
run this exact loop against a fake NX and a scripted model, with no NX
and no AWS bill.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

#: The entire prompt. One sentence of orientation and nothing else - the
#: point of this folder is to find out what Claude does with NX when
#: nobody has told it how. If you want to know what guidance is worth,
#: add some here and run the same task again.
SYSTEM = (
    "You are working in a live Siemens NX session through the tools "
    "provided. The user's part is open as the work part. Units are "
    "millimetres. Do the task you are given, then say what you did."
)


def _text(block_list):
    out = []
    for block in block_list or []:
        if block.get("type") == "text":
            out.append(block.get("text", ""))
    return "\n".join(part for part in out if part.strip())


def conversation(nx, ask, prompt, rounds=12, note=None):
    """Prompt in, transcript out. The whole program.

    `note` is called with each line so the caller decides where the
    transcript goes; the loop itself does not know about NX's
    Information window or about files.
    """
    if note is None:
        note = lambda line: None

    messages = [{"role": "user", "content": prompt}]
    note("TASK: " + prompt)

    for number in range(1, rounds + 1):
        reply = ask(messages, nx.TOOLS, SYSTEM)
        said = _text(reply.get("content"))
        if said:
            note("\nCLAUDE: " + said)

        calls = [block for block in (reply.get("content") or [])
                 if block.get("type") == "tool_use"]
        if not calls:
            if reply.get("stop_reason") == "max_tokens":
                note("\n(stopped: ran out of output tokens. Raise "
                     "max_tokens or ask for less.)")
            note("\n(done in %d round%s)" % (number, "" if number == 1 else "s"))
            return messages

        messages.append({"role": "assistant", "content": reply["content"]})
        results = []
        for call in calls:
            arguments = call.get("input") or {}
            note("\n  %s %s" % (call.get("name"),
                                json.dumps(arguments)[:2000]))
            answer = nx.perform(call.get("name"), arguments)
            note("  -> " + json.dumps(answer)[:2000])
            results.append({
                "type": "tool_result",
                "tool_use_id": call.get("id"),
                "content": json.dumps(answer),
                # The model should see a refusal as a refusal rather than
                # read `"ok": false` out of a success.
                "is_error": not answer.get("ok", True),
            })
        messages.append({"role": "user", "content": results})

    note("\n(stopped after %d rounds without Claude finishing. Raise "
         "BARE_ROUNDS if the task really needs more.)" % rounds)
    return messages


def task():
    """The task to do: the environment, else prompt.txt, else argv."""
    from_env = os.environ.get("BARE_PROMPT", "").strip()
    if from_env:
        return from_env
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return " ".join(sys.argv[1:]).strip()
    where = os.path.join(HERE, "prompt.txt")
    try:
        with open(where, "r") as handle:
            written = handle.read().strip()
    except IOError:
        written = ""
    if written:
        return written
    raise RuntimeError(
        "nothing to do. Write the task into %s, or set BARE_PROMPT."
        % where)


def main():
    import bedrock
    import nxside
    import sigv4

    lines = []

    def note(line):
        lines.append(str(line))
        nxside.say(line)

    try:
        work = nxside.session().Parts.Work
    except Exception as error:
        nxside.say("This has to run inside NX: File -> Execute -> NX Open..."
                   " (%s: %s)" % (type(error).__name__, error))
        return 1
    if work is None:
        nxside.say("No work part. Open a part - a copy of one - and run "
                   "this again.")
        return 1

    note("model %s in %s%s" % (bedrock.model(), sigv4.region(),
                               "  [BARE_DRY: nothing will change]"
                               if nxside.dry() else ""))
    try:
        conversation(nxside, bedrock.ask, task(),
                     rounds=int(os.environ.get("BARE_ROUNDS", "12") or 12),
                     note=note)
    except Exception as error:
        note("\nSTOPPED: %s: %s" % (type(error).__name__, error))
    finally:
        where = os.environ.get("BARE_LOG") or os.path.join(
            HERE, "bare-transcript.txt")
        try:
            with open(where, "w") as handle:
                handle.write("\n".join(lines) + "\n")
            nxside.say("\ntranscript: " + where)
        except IOError as error:
            nxside.say("\n(could not write the transcript: %s)" % error)
    return 0


# Called rather than sys.exit'd: a SystemExit raised inside NX's journal
# runner is reported as the journal having failed, which it has not.
if __name__ == "__main__":
    main()
