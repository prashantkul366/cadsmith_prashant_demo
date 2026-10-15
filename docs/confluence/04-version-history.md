# Version History | What Changed When

Five versions between the first working prototype and what was shown at
the expo. The names are for this wiki; the repository branch is given for
each one so anybody can check out that exact state and run it.

| | Version | Repository branch | What it added |
|---|---|---|---|
| V1 | First working app | `main` | The pipeline, in a browser |
| V2 | Bilingual, catalogued, drawn | `claude/bedrock-backend-and-live-thinking` | Bedrock, Japanese, standard parts, real drawings, DXF, spend ceiling |
| V3 | Backend made diagnosable | `claude/engineering-grade` | Says why a backend cannot run, instead of failing silently |
| V4 | **The UI refresh** | `claude/ui-refresh` | The interface as demonstrated. Versions, undo, Japanese throughout |
| V5 | Drawings and cost | `claude/manufacturing-cost` | Sheets that can be machined from, and a cost estimate |

Two later threads — the FreeCAD tool-calling approach and the NX work —
are **not** part of this project. See *Project Scope | Phase 1*.

---

## V1 — First working app

A front end for the research pipeline. Type a part in English, watch the
five agents work, then inspect the solid, its source, and every attempt
along the way.

What made it more than a viewer: everything on screen came from the
pipeline. The mesh was the STL the kernel exported, the dimensions were
the kernel's own measurements, the code was what the Coder actually wrote,
the verdict was the Judge's. No progress bar ran on a timer and nothing
was simulated — which sounds like a small thing and is the reason the
demo survived contact with visitors.

The research code was not touched, and still has not been. Observability
is attached from outside it.

## V2 — Bilingual, catalogued, drawn

The version where it stopped being a demo of a pipeline and started being
an application.

- **Japanese**, with the model kept reading English internally, so a
  Japanese request did not become a translation problem.
- **Standard-parts catalogue**, 18 families, served exactly from the
  published standard with no model call — and working when nothing else is
  configured.
- **Measured specification checks**: the solid measured against what the
  plan claimed, blocking a version the vision Judge would have passed.
- **The drawing became an engineering drawing** rather than four pictures
  — projected views, title block, conventions — and then a **DXF** through
  ezdxf.
- **The drawing is built when the part is**, not when somebody opens the
  tab, so the tab opens instantly.
- **A parameters view** on the code panel: the generated script's own
  parameters, as controls.
- **A spend ceiling** per run.
- Text read and written as UTF-8 rather than the locale codec — without
  which Japanese on a Windows machine is mojibake.

## V3 — Measured, graded, and diagnosable

Two kinds of work in one day, 21 September.

**The checks got sharper.** A rejected attempt learned to explain itself
by measurement rather than only by the Judge's opinion. The app learned to
say *where* the holes are and not just how many. What a part is made of
and how closely it has to be held became things the plan can state and
the checks can test. The request's own numbers are held fixed, so a
dimension the engineer gave cannot drift. Results were graded by
difficulty and by the edit chain an engineer actually works in — and
**the first run against a real model was recorded here**, Qwen3-VL-8B
over the tiered prompt set, which is the evaluation the Evidence page
reports.

**And the backend became diagnosable**, because one that fails for an
unclear reason costs an afternoon, and on a stand it costs the demo. It
now says which AWS identity is actually in use, whether the variables
reached the process, where each one came from — shell or file — whether a
global or a regional profile was chosen, and why Bedrock cannot run when
it cannot, rather than announcing itself ready and failing at the first
prompt.

## V4 — The UI refresh

The interface as demonstrated, rebuilt around the three things a visitor
actually does: ask, watch, adjust.

- **The left column became a conversation**, with one place to type. The
  prompt box is never taken away, and the settings yield to it.
- **The centre is the part.** One view switch, controls floating on the
  model, and a gizmo that turns it. The viewport is kept clear of the
  rails at every window size.
- **The right column is four cards that shut away**, each with the part's
  own colour, so four panels of detail do not compete with the model.
- **The dimensions sit beside the part they change**, and the version
  strip scrolls.
- **The reasoning got the centre of the left rail** — a 296-pixel rail is
  not a window to read five agents' thinking through — with a cap on how
  much any one agent shows.
- **The rail can be moved**, and the browser stops serving yesterday's
  app.
- **Every version is numbered, and there is undo.**
- **Japanese throughout** — interface, run log, verdicts, drawing title
  block, example prompts.
- The expo material (overview, deck, stand documents) was written against
  this version, and the screenshots in `docs/expo/img` were captured from
  it on 2026-09-24.

Also fixed here, both of which were visible on screen: a sentence printing
as `NaN`, and the app stating a size the kernel disputed.

## V5 — Drawings and cost

Two things, both about handing the part to somebody who has to make it.

**The sheet became something you can machine from.** A hole's depth is
read off the solid rather than off the circle it projects to. A view
dimensions what it cuts, not only what it encloses. A callout's numbers
are all counted, not just the one it measures. A hole count is not read as
a dimension, and the count sign is spelt the same way everywhere on the
sheet. Every drawing is saved, each one labelled with whether every number
on it is a measurement of the solid it was drawn from — because a missing
dimension is a gap somebody notices, and a number that measures nothing is
a drawing that lies.

**The cost estimate.** Stock plus operations, read off the geometry, shown
on screen in the reader's language. See *Manufacturing Cost Estimate*.

Also: the Design Plan reads in Japanese, including its dimension names,
and a Japanese run is read in Japanese the whole way through.
