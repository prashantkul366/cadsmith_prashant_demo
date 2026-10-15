# The NX side

Python that runs **inside** NX. None of it has been run: there is no NX
in the environment it was written in, so every NX Open call here is taken
from the reference and is a claim until a session proves it.

That is why `selfcheck.py` exists and why it is the first thing to run.
It does not try to do anything useful to a part. It reports what the API
on that machine actually looks like - which classes, which properties,
which of them answer - and writes it to a file. With that file the rest
of this can be corrected in an afternoon instead of guessed at twice.

Run order on the machine that has NX:

1. `selfcheck.py` - with any part open. Writes `cadsmith-nx-report.json`
   next to itself. Send that back.
2. `read_part.py` - with a part open. Prints the feature tree as the
   server expects it. Confirms the reading half.
3. `cadsmith.py` - the assistant itself. Needs the server running.

Each is a plain NX Open journal: **File → Execute → NX Open**, pick the
file. No ribbon entry, no menu files, no installation - those come once
the API underneath is known to work, because a menu that loads a broken
library is harder to debug than a journal that fails on one line.
