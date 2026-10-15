"""Print the open part's feature tree, exactly as the server reads it.

Run as a journal with a part open:  File -> Execute -> NX Open

Step two of three, and it changes nothing. The self-check says what the
API offers; this says what this particular part looks like through it.
Reading it is how you tell whether the plugin understands the part
before letting it change one - if the expressions come back with no
descriptions, or the features with no names, nothing above this can
work and it is better seen here than guessed at from a bad answer.

It also writes the tree to a file, which can be sent back and replayed
against the server with no NX in the room.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import collect  # noqa: E402  (beside this file, not an installed package)


def main():
    import NXOpen
    session = NXOpen.Session.GetSession()
    work = session.Parts.Work
    if work is None:
        _say(session, "Open a part first: there is no work part to read.")
        return

    tree = collect.part(work)
    where = os.path.join(HERE, "cadsmith-nx-tree.json")
    try:
        with open(where, "w") as handle:
            json.dump(tree, handle, indent=1, default=str)
    except Exception:
        where = os.path.join(os.path.expanduser("~"), "cadsmith-nx-tree.json")
        with open(where, "w") as handle:
            json.dump(tree, handle, indent=1, default=str)

    lines = [f'part {tree["part"]}',
             f'{len(tree["features"])} features, '
             f'{len(tree["expressions"])} expressions',
             f"written to {where}", ""]
    for one in tree["features"]:
        numbers = ", ".join(f'{e["name"]}={e["value"]:g}'
                            + (f' [{e["formula"]}]' if e["formula"] else "")
                            for e in one["expressions"])
        lines.append(f'  {one["name"]} ({one["kind"]})'
                     + (" SUPPRESSED" if one["suppressed"] else "")
                     + (f": {numbers}" if numbers else ""))
    # The descriptions are the thing to look at. Without them a part is
    # p1..p40 and nothing can tell which number is a hole diameter.
    lines.append("")
    lines.append("expressions, and what NX says each one drives:")
    for one in tree["expressions"][:40]:
        lines.append(f'  {one["name"]} = {one["value"]:g} '
                     f'{one["units"]}   {one["description"] or "(no description)"}')
    _say(session, "\n".join(lines))


def _say(session, text):
    try:
        window = session.ListingWindow
        window.Open()
        for line in text.splitlines():
            window.WriteLine(line)
    except Exception:
        print(text)


if __name__ == "__main__":
    main()
