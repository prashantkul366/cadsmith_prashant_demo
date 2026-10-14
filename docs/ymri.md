# YMRI branch — what it is for

Branched from `claude/freecad-mcp` after the YMRI meeting. The MCP road is
the one this work continues: a parametric CAD document that stays open and
gets worked on, rather than a script that gets regenerated.

## What the meeting settled

The order of work is not what this branch assumed when it started, so it
is written down here plainly.

**First deliverable: a locally deployable 3D-to-2D drawing generator.**
YMRI spend a lot of their time making drawings, and that is the part of
the tool they are most interested in. It is to run at their site, on their
data, and it is the first thing to be demonstrated.

**Then NX.** The demo is to be given in the NX environment; YMRI engineers
want an integrated tool, not a standalone one, and that means NX and
eventually Teamcenter. YMSLI is to confirm what integration is possible.

**Then the trial.** Once NX integration and the privacy question are
settled, the demo is installed at YMRI and **4-5 engineers use it for a
month**. A review follows, and their feedback defines the research
activities for the IITD project.

**Editability is the research thread, not the first demo.** YMRI need the
generated models to be editable, and said plainly that STEP and STL do not
carry enough to edit. That is what the feature-tree work on this branch is
for, and it is also what Prof. Sarangi's work on recovering a tree from
STEP and STL is for. It is a three-year project with annual milestones -
not the thing being shown first.

**They will sign an NDA so their drawings can be used for training.** That
changes what is possible: the question "which dimensions belong on this
sheet" stops being a matter of our judgement about ISO and becomes a
question their own drawings can answer. Worth knowing what to ask for -
drawings paired with the models they were made from, enough of them, and a
spread of part families rather than one.

**The application they named is motorcycle exterior panels.** Worth saying
early rather than after a demo: those are large freeform surfaces, and the
tool vocabulary here is prismatic - pads, pockets, revolves, lofts. The
drawing side cares much less, because it projects whatever solid it is
given, but a panel's drawing is mostly profiles, sections and a datum
scheme rather than holes and depths.

---

---

## 4. The app: tree, view, and changes by asking

This is the part that is built, and the part the branch exists for.

**The tree is read from the live document.** `app/server/tree.py` reports
every object with its place in the tree, and each property with its value,
its unit, its type, and whether it may be written. It runs as a script
inside FreeCAD over the same bridge everything else on this road uses,
which has two consequences worth stating: the addon's own `get_objects`
returns values with no metadata, and a panel that offers an editor for a
read-only property is a panel that lies; and a script runs through *any*
bridge, so the whole module is tested against a headless `freecadcmd`
rather than against a FreeCAD somebody has to have open.

**Editing writes to that document.** Every value in one request is set
before the single recompute, so two numbers that are only valid together
are not rejected one at a time. A change that leaves anything unable to
rebuild is put back, and the answer says whether the document rebuilds
after that rollback rather than claiming it does — the engineer either has
their part or has a broken one and a reassuring message.

**The viewport shows the live document.** `GET /api/freecad/documents/
{document}/mesh` exports the open document, not the saved version, because
the point of editing the tree is that the document has moved on from the
version.

**Changes by asking already work**: `freecad_run.amend` reopens the
version's own document and works the tree with the same toolbox the build
used. The tree panel and `amend` are two ways into one document.

What is not done yet: datum planes and origins clutter the tree the way
they do before FreeCAD's own tree hides them; there is no undo on a tree
edit beyond FreeCAD's own; and a property with an expression bound to it
is shown as its value, not as the expression.

---

## 1 and 5. NX and Teamcenter

**What is true of this codebase.** The FreeCAD road talks to CAD through
one narrow surface — `Bridge.run(code)` returns what a script printed, and
`Bridge.fetch(document, kind)` returns exported bytes. Everything above it
(the tool vocabulary, the tree module, the TechDraw sheet) is written
against that surface and not against FreeCAD. An NX backend is therefore a
second class with the same two methods, not a second application.

**What NX offers that fits that surface.** NX Open is the automation API;
it is reachable from C#, C++, Java and Python. Journals are run from the
GUI or in batch with Siemens' `run_journal`, which starts NX without a GUI
and needs a licence for whatever the journal does. That is the same shape
as `freecadcmd`: hand it a script, read what it printed. A journal may need
changing to work in batch — typically to open the part file it is given
rather than assuming an open session.

**What could not be verified here, and should not be guessed at.** The
sources reachable from this container are community posts and vendor blogs;
Siemens' own NX Open and Teamcenter documentation is behind a login. The
exact `run_journal` invocation, the Python environment NX expects, and
which NX and Teamcenter releases YMRI runs are all things to take from
their documentation and their installation, not from here. The same goes
for Teamcenter: community sources describe check-in and check-out through
ITK (`WSOM_check_out` / `WSOM_check_in`), SOA services, and a REST layer
under Active Workspace, and one thread reports that checking out an NX
dataset does not necessarily check out the item revision — which is exactly
the kind of detail that decides an integration and must come from their
environment.

**The target is NX 2412.5000.** Still to establish from their side: the
Teamcenter release, whether `run_journal` is licensed for automation on
the machines this would run on, and whether the parts live in Teamcenter
or on disk.

**One thing that shapes the plugin and should be settled first.**
`run_journal` is a batch runner: a process per call. This app assumes a
session - a document that stays open between calls - and that assumption
is what makes "change this, now change that" work at all. So the NX plugin
cannot be `run_journal` driven; it needs a listener hosted inside a running
NX session, the way the FreeCAD addon is. `run_journal` is the right tool
for the integration *check* and the wrong one for the interactive loop.
That reading comes from how the batch runner is described rather than from
Siemens' own documentation, so it is the first thing to confirm.

**Who has what.** The engineers in the pilot run NX; FreeCAD is on our
side only, for building and showing this. That means the two weeks cannot
be "install this and use it" unless FreeCAD goes onto their machines -
see `docs/pilot.md` for the three shapes that leaves and what each one
buys.

**The integration check.** "Does NX integration work here" should be a
thing that runs and prints, not a conversation. It belongs next to the
existing health checks: NX found, version, `run_journal` present, licence
obtained, a trivial journal run and its output read back. That is the first
NX work to do, because it is also how every later step is debugged.

---

## 2. The 3D-to-2D converter

This already exists twice on these branches and the choosing is already
separated from the drawing:

* `app/server/holes.py` decides what a part needs called out and how to
  word it, from the solid.
* `app/server/drawing.py` renders that as SVG and DXF by projecting the
  solid itself.
* `app/server/techdraw.py` renders the same choices as a real TechDraw page
  in the engineer's own document, with dimension objects attached to edges
  so they follow the part when it changes.

An NX Drafting backend is a third renderer behind the same chooser. Nothing
about which dimensions to show is in either renderer, which is what makes
that possible — and that question is the separate piece of work.

Measured on the 208 solids built from the 61-prompt library, every number
on every sheet is traceable to a measurement of the solid it was drawn
from, on both renderers. Legibility is a different question and an open
one: on a dense part the dimensions overlap each other and the view.

---

## 3. Local models

Already supported, and already used. `app/server/providers.py` speaks to
any OpenAI-compatible endpoint: Ollama and LM Studio have entries of their
own, and `custom` takes `CADSMITH_LLM_BASE_URL` for vLLM, llama.cpp or
anything else served locally. Nothing in the pipeline is specific to a
hosted model.

The pilot is sized for a **Qwen around 8B**, and must stay usable at 4B.
That size of model is the reason the tool surface is now scoped: changing
an existing part offers thirteen tools instead of twenty-six - the same
tools, 60% less schema - because a 4B model given twenty-six spends its
context reading about tools it will not use and chooses worse among the
ones it will. The `run_python` escape hatch is deliberately not in that
list.

What has not been measured, and should be before the pilot: whether a
model that size calls these tools correctly at all. There is no local
model on this machine to try it against. It is the single biggest risk to
the asking half of the demo, and the tree half does not depend on it.

For confidentiality the thing to establish is not whether it runs — it does
— but what leaves the machine. Worth stating plainly to YMRI: with a local
endpoint configured, the prompt, the tool calls and the geometry stay on
their network; the catalogue and the kernel are local already; and the only
outbound traffic is whatever the operating system and the browser do.
