# The demo YMRI engineers will run

Four or five engineers, a month, at their site, on their data. This is what
has to be true before that starts, in the order the meeting put it.

The first thing to be shown is **3D to 2D**: a drawing made from a solid.
That is the part of the tool YMRI are most interested in, because drawing
creation is where their time goes. Everything else on this branch - the
feature tree, changing a part by asking - is the research thread behind the
IITD project, and is not what gets demonstrated first.

---

## The one decision that unblocks the timeline

**The drawing generator does not need NX integration to be useful at
YMRI.** It takes a solid and gives back a drawing. NX writes STEP; the
generator reads STEP; it writes DXF, which NX reads back. Nothing in that
loop needs an NX licence, an NX plugin, or a Siemens API.

That matters because the sequence as it stands is "confirm NX integration,
then build the demo, then install it", and NX integration is the step with
the most unknowns in it - the NX release, the Teamcenter release, whether
automation is licensed on those machines, and whether a listener can be
hosted inside a running NX at all. If the first demo waits on all of that,
the month-long trial waits on it too.

A file-in, file-out drawing generator can be installed and used while that
is still being worked out. It is also honest about what it is: the
integrated version is better, and this is the version that can be in an
engineer's hands sooner.

What it costs: the drawing is made from the solid, so it carries no NX
part attributes, no Teamcenter metadata and no title block of theirs
unless we are given one. Those are worth asking for early, because a
drawing that does not look like their drawings will be judged on that
before anybody reads a dimension.

---

## What has to be good before four engineers see it

The numbers on the sheets are right. Measured across the 208 solids built
from the 61-prompt library: every number printed on every sheet is
traceable to a measurement of the solid it was drawn from, on both
renderers. That was not true two days ago - the audit found three real
faults and they are fixed.

What is not yet good enough is **which** dimensions appear and **where**
they sit. On a simple part the sheet is clean. On a dense one - a plate
with a hundred holes, a heat sink with two hundred pins - dimensions
overlap each other and cross the view, and some features get no callout at
all because the leader count is capped. A drawing nobody can read is not a
drawing, and this is the thing YMRI will judge the tool on.

That work is in progress and is the priority. It has three parts:

1. **Selection** - which dimensions a reader needs to make the part, and
   which are noise. Their own drawings, once the NDA is in place, answer
   this better than our reading of ISO does.
2. **Placement** - ISO 129-1 order, nothing crossing, each dimension in
   the view that shows the feature's true shape.
3. **Sufficiency** - whether the sheet carries enough to make the part at
   all, which is a different question from whether every number on it is
   true.

---

## Confidentiality

Nothing has to leave their network. The CAD kernel and the catalogue are
local already; the model endpoint can be Ollama, LM Studio, vLLM or
llama.cpp through `CADSMITH_LLM_BASE_URL`. The drawing generator needs no
model at all - it is geometry in and geometry out - which makes the first
deliverable the easiest one to clear with their IT.

---

## Before they start

```
python -m app.tools.doctor
```

Checks each layer separately so a failure names what is broken. The
FreeCAD section matters only for the parts of the tool that drive FreeCAD;
the drawing generator does not.

---

## What we want back after the month

- **Which drawings they would have sent out as-is**, and which they
  redrew.
- **What they had to add by hand** - that is the selection problem, stated
  by the people who know.
- **What was wrong**, as against merely missing.
- **The parts it was no use on at all.** Those tell us the most.

---

## What is not in the first demo, on purpose

- **NX and Teamcenter integration.** Being worked out in parallel; see
  `docs/ymri.md`.
- **Assemblies.** One part at a time.
- **Their title block and drawing standard**, until we are given them.
- **Anything learned from their drawings.** That needs the NDA and the
  data first.
