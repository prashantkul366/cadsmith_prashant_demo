# CADSmith for NX 2412.5000

An NX plugin: the engineer types what they want, and the model changes
their part using NX's own features, expressions and update manager. No
FreeCAD, no second kernel, no exported file in the middle. Parasolid
makes the geometry and the NX feature tree is the model.

---

## The one design decision everything follows from

On the FreeCAD road, **our server drives the CAD**: it opens a socket into
a running FreeCAD and sends it Python. Copying that into NX would mean a
socket server inside an NX session, and that is where it stops being a
good idea.

NX Open is not documented as thread-safe, and the field reports are
discouraging: a Siemens Community thread records giving up on opening a
window from a background thread inside NX Open Python and moving the work
to a separate interpreter. A socket listener needs a thread to accept on,
and anything it then does to the part has to happen on NX's own thread.
There is a standard way to arrange that - queue the work and have the main
thread drain it - but it needs a main-thread pump, and in a session that
is idle in its own event loop there is no documented hook to pump from.

So the direction is reversed. **NX calls us.**

```
   engineer types in a dialog inside NX
            |
            v
   plugin reads the feature tree        (NX Open, main thread)
            |
            v
   POST  /api/nx/turn   prompt + tree   (plain HTTP to 127.0.0.1)
            |
            v
   server runs the model, returns the operations to perform
            |
            v
   plugin performs them                 (NX Open, main thread)
            |
            v
   POST  /api/nx/turn   what happened --> loop until done
```

Every NX Open call happens on NX's own thread, inside a dialog callback,
which is the one place NX is documented to call your code. No threads, no
listener, no pump. The agent loop, the model, the conversation and the
gate live in the server, which never touches NX.

What this costs: NX cannot be driven while the engineer is doing something
else - they start the turn. For an assistant that is asked for things,
that is the right shape rather than a limitation.

What it buys, beyond safety: the server is testable without NX, because
from its side a turn is an HTTP request carrying a tree and returning
operations.

---

## What is verified, and what is not

Nothing in this document has been run against NX. There is no NX in the
development environment. That is the single most important fact about
this branch and it is written here rather than discovered later.

**Verified** (by building it on FreeCAD first, where there is a kernel to
run against): the shape of the tool vocabulary, the rule that a refused
change must leave the part as it was, the gate that measures the finished
solid against what was asked for, and that a model can drive a document
feature by feature.

**Taken from documentation, not run**: every NX Open call named here.
`Feature.GetExpressions`, `Expressions.Edit`, `MenuBarManager.RegisterApplication`
and the MenuScript files come from the NX Open reference and community
sources. Method names and signatures must be checked against the NX 2412
reference before any of it is trusted.

**Unknown until there is a seat**: whether a dialog callback can make an
outbound HTTP call without upsetting NX, how long NX tolerates a callback
blocking, and whether the ribbon entry needs the DTX files that one
community report says NX 2412 wants.

---

## What is needed to go further

1. **An NX 2412.5000 seat** we can develop against.
2. **An author licence**, because unsigned NX Open code needs one to run
   at all. Which licence - the Python author feature or the Toolkits
   bundle - is a question for the Siemens reseller, not for us.
3. **A decision on signing.** A signed application runs on ordinary
   execute licences; an unsigned one needs every engineer to hold an
   author licence. That is the difference between "install it" and "buy
   five more licences", and it should be settled before the plugin is
   costed.

Until 1 and 2 exist, what can be built is everything on the server side
of that arrow, and the plugin written against the documented API ready to
be corrected the first time it runs.
