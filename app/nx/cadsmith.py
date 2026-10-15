"""The assistant, inside NX.

Run as a journal with a part open:  File -> Execute -> NX Open

Asks the engineer what they want, sends the request and the part's
feature tree to the CADSmith server on this machine, shows what the
model proposes, and performs it only if the engineer says yes.

Every NX Open call happens here, on NX's own thread, inside the journal
NX called. There is no listener, no background thread and no socket
server inside the session: NX Open is not documented as thread-safe,
and a part is not the place to find out.

**Nothing is performed without being shown first.** The operations for a
turn are known before any of them runs, so they are printed in the
engineer's own terms and approved as a set. On somebody's real part that
is the difference between a tool they will use and one IT will not
allow, and it costs one dialog.

The plugin never saves. The engineer saves, or closes without saving,
exactly as they would after any other change.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collect   # noqa: E402
import perform   # noqa: E402

#: Where the server is. Localhost by default: the whole point is that
#: nothing leaves the machine.
SERVER = os.environ.get("CADSMITH_SERVER", "http://127.0.0.1:8000")

#: How many times round the loop before stopping and showing what has
#: happened. A turn is a model call and a set of changes; a part that
#: needs more than this wants a person looking at it.
MAX_TURNS = 6


def ask(session, title, prompt, default=""):
    """One line of text from the engineer, however this NX can ask."""
    import NXOpen
    try:
        from NXOpen import UI
        answer = UI.GetUI().NXMessageBox  # noqa: F841  (presence check)
    except Exception:
        pass
    # NX has several input dialogs across versions and licences, so the
    # ones that might be there are tried in turn, and a plain console
    # prompt is the last resort rather than a failure.
    try:
        import NXOpen.UF
        ufsession = NXOpen.UF.UFSession.GetUFSession()
        got = ufsession.Ui.AskStringInput(prompt, default)
        if isinstance(got, (list, tuple)):
            got = got[-1]
        return str(got or "").strip()
    except Exception:
        pass
    try:
        return str(input(prompt + " ")).strip()
    except Exception:
        return ""


def confirm(session, text):
    """Show what is about to happen and get a yes or no."""
    import NXOpen
    try:
        ui = NXOpen.UI.GetUI()
        answer = ui.NXMessageBox.Show(
            "CADSmith", NXOpen.NXMessageBox.DialogType.Question,
            text + "\n\nPerform these changes?")
        # NX returns 1 for the first button on a question box.
        return int(answer) == 1
    except Exception:
        pass
    try:
        return str(input(text + "\n\nPerform these changes? [y/N] ")
                   ).strip().lower().startswith("y")
    except Exception:
        return False


def post(path, body):
    """Call the server. Plain urllib: no package to install inside NX."""
    import urllib.request
    data = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        SERVER.rstrip("/") + path, data=data,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as answer:
        return json.loads(answer.read().decode("utf-8"))


def readable(operation):
    """One operation as a line an engineer can judge."""
    arguments = operation.get("arguments") or {}
    intent = operation.get("intent") or ""
    detail = ", ".join(f"{k}={v}" for k, v in arguments.items())
    return (f'  {operation.get("name")}: {detail}'
            + (f"   ({intent})" if intent else ""))


def main():
    import NXOpen
    session = NXOpen.Session.GetSession()
    window = session.ListingWindow
    window.Open()

    def say(text):
        for line in str(text).splitlines():
            window.WriteLine(line)

    work = session.Parts.Work
    if work is None:
        say("Open a part first.")
        return

    wanted = ask(session, "CADSmith",
                 "What would you like changed about this part?")
    if not wanted:
        say("Nothing asked for.")
        return

    say("CADSmith")
    say("part: " + str(getattr(work, "Name", "(unnamed)")))
    say("you asked: " + wanted)
    say("")

    results, asked_before = None, None
    for turn in range(MAX_TURNS):
        tree = collect.part(work)
        try:
            answer = post("/api/nx/turn",
                          {"prompt": wanted, "tree": tree,
                           "results": results, "asked_before": asked_before})
        except Exception as error:
            say("Could not reach the CADSmith server at %s" % SERVER)
            say("%s: %s" % (type(error).__name__, error))
            say("Start it, or set CADSMITH_SERVER, and run this again.")
            return

        if answer.get("say"):
            say(answer["say"])
        for refusal in answer.get("refused") or []:
            say("  (not done: %s - %s)" % (refusal.get("name"),
                                           refusal.get("why")))

        operations = answer.get("operations") or []
        if not operations:
            if answer.get("done"):
                say("")
                say("Nothing further. The part has not been saved - that is "
                    "yours to do.")
                return
            # Everything was refused; let it try again with the reasons.
            results, asked_before = None, None
            continue

        shown = "\n".join(readable(one) for one in operations)
        say("")
        say("Proposed:")
        say(shown)
        if not confirm(session, shown):
            say("Nothing was changed.")
            return

        results = []
        for one in operations:
            outcome = perform.one(one)
            results.append(outcome)
            say(("  done: " if outcome.get("ok") else "  refused: ")
                + str(outcome.get("name"))
                + " - " + str(outcome.get("detail") or outcome.get("why", "")))
        asked_before = [readable(one).strip() for one in operations]

    say("")
    say("Stopped after %d turns. The part has not been saved." % MAX_TURNS)


if __name__ == "__main__":
    main()
