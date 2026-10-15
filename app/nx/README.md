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

---

## What is written, and what is not

| file | what it does | run against NX? |
|---|---|---|
| `selfcheck.py` | reports what NX Open offers here | **no** |
| `collect.py` | NX objects to plain data | **no**, but tested against stand-ins |
| `read_part.py` | prints the tree the server would read | **no** |
| `perform.py` | performs one operation | **no** |
| `cadsmith.py` | the assistant: ask, propose, confirm, perform | **no** |

"No" means exactly that: there was no NX in the environment this was
written in. The names come from the NX Open reference. Some will be
wrong, which is what `selfcheck.py` is for.

Of the operations, the ones that change an **existing** part are
written - `edit_expression`, `suppress_feature`, `delete_feature`. The
ones that create geometry say plainly that they are not implemented
rather than half-working. That is the right order: editing an expression
is how a part somebody else designed gets changed, it is the operation
everything else rests on, and it is the simplest to verify - set a
number, update, read it back.

## Nothing happens without being shown

`cadsmith.py` prints every operation in the engineer's own terms and
waits for a yes before performing any of them. The operations for a turn
are all known before the first one runs, so this costs one dialog and
nothing else.

The plugin never saves. The engineer saves, or closes without saving.
