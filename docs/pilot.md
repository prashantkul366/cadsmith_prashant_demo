# The two-week pilot

What YMRI engineers get, what we are trying to learn from them using it,
and what is deliberately not in it yet.

The thing being piloted is an assistant that works in the CAD document the
engineer already has open. Two ways in, one document: the **feature tree**,
edited the way any CAD package is edited, and **asking in words**. Both go
through the same code, so a number dragged in the panel and a number set by
asking take the same path, get the same recompute, and are backed out by
the same undo.

This runs on FreeCAD. The NX plugin for **NX 2412.5000** is the step after,
and the pilot is how we find out what it should do before anyone writes it.

---

## Before you start

Run the preflight. It checks each layer separately so a failure names what
is broken rather than appearing later as a run that hangs:

```
python -m app.tools.doctor
```

Everything it reports comes with the fix beside it. The FreeCAD section is
the one that matters on this road — connection, addon, a script run and
read back, the documents open, the feature tree, and an export. If the
first line fails, nothing above it can work.

**What has to be running**

1. **FreeCAD**, with the MCP addon workbench started (*Start RPC Server*).
   The app talks to it over XML-RPC on port 9875 by default;
   `CADSMITH_FREECAD_HOST` and `CADSMITH_FREECAD_PORT` move it.
2. **A model endpoint.** For confidential work this is a local one and
   nothing leaves your network: Ollama and LM Studio have their own
   entries, and `CADSMITH_LLM_BASE_URL` points at vLLM, llama.cpp or
   anything else OpenAI-compatible. The app never needs an outside
   service; the catalogue and the CAD kernel are local already.
3. **The app**: `./app/run_app.sh`, then open the address it prints.

---

## What to try

Work in your own parts. The point of two weeks is what *your* parts do to
it, not what our test parts do.

**Start from a document you already have open.** The picker under the
prompt lists what FreeCAD has open; choose one and the assistant works in
it rather than making its own.

**The feature tree.** Open it from the toolbar (the tree icon). It shows
the document's own history — the pad, the sketch it came from, the pocket
cut into it — with every number that can still be changed. Change one and
the part on screen rebuilds. A value the part cannot be rebuilt with is
refused, says why, and puts the old one back.

**Asking.** "Open the mounting holes to 11", "lose the corner fillets",
"add a 6 mm rib down the middle". The assistant reads the same tree you are
looking at, so it sees what you changed by hand.

**Undo** is in the tree's header, and it is FreeCAD's own undo stack: it
backs out a change made by asking, one made in the panel, and one you made
in FreeCAD yourself.

**Drawings** (the sheet icon) project the part and dimension it. Every
number on the sheet is a measurement of the solid — that is checked across
the whole test library — but *which* dimensions appear, and where they sit
on a busy part, is the piece of work we are doing next. Tell us what is
missing rather than assuming we think it is finished.

---

## What we want back

The useful thing is not "it worked" or "it didn't". It is:

- **What you asked for and what you got**, where those differed.
- **What you had to do by hand** afterwards, and whether the tree let you.
- **Anything it refused** that you think it should have done.
- **Anything it did** that it should have refused.
- **The parts it was no use on at all** — those tell us the most.

Every run is recorded under `app/runs/` with the prompt, the steps and the
resulting document. Nothing is sent anywhere. If you want to send a run
back to us, send that run's folder; if the geometry is confidential, the
`meta.json` and `events.jsonl` in it carry what happened without carrying
the part.

---

## What is not in this yet, on purpose

- **NX.** This pilot is FreeCAD. What it teaches us about what engineers
  actually ask for is what the NX 2412.5000 plugin should do; building the
  plugin first would be guessing.
- **Teamcenter.** No check-in, no check-out, no item revisions. Work on
  files.
- **Which dimensions a drawing should carry.** Separate piece of work, in
  progress.
- **Assemblies.** One part at a time.
- **Sketch constraints.** The tree reaches a feature's numbers, not the
  constraints inside its sketch. Say if that is what you keep needing.

## Known rough edges

- Datum planes and origins show in the tree the way they do before
  FreeCAD's own tree hides them.
- A property driven by an expression shows its value, not the expression.
- Undo only reaches changes made since the document was opened, because
  that is as far as FreeCAD's own stack goes.
