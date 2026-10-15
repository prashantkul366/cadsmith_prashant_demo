# Project Scope | Phase 1

## Objective

Build a working prototype that turns natural-language part descriptions,
in Japanese or English, into editable, kernel-verified CAD models, A3
engineering drawings and STEP/STL/GLTF/DXF files — and demonstrate it at
Yamaha Motor Tech Expo 2026.

## In scope

**Input and understanding**

- Single mechanical parts: prismatic, turned and revolved
- Japanese and English text input, including a Japanese request for a
  standard part understood as typed
- Standard-parts catalogue: 18 families built to published standards and
  served exactly, with no model call, plus a router that hands anything
  ambiguous to the agents rather than guessing

**Generation and verification**

- Multi-agent pipeline: Planner, Coder, Executor, Validator (CAD kernel
  plus vision Judge), Refiner
- Two correction loops — one for code that will not run, one for geometry
  that is wrong
- Measured specification checks: the built solid is measured for what the
  plan claimed, and a measurable shortfall blocks the version whatever the
  vision Judge said
- Per-run token ceiling, so a loop that will not converge cannot run up a
  bill

**Editing and output**

- Parameter sliders over the generated script's own parameters; the kernel
  rebuilds in about a second with no model call
- Numbered versions, undo, and a filmstrip of every attempt with its
  verdict, including the rejected ones
- A3 engineering drawing: four projected views, first-angle, dimensions,
  centre lines, title block
- Exports: STEP, STL, GLTF, DXF, and the CAD source itself
- Manufacturing cost estimate: stock plus operations, read off the
  geometry, in the reader's language
- Run history and replay, so a recorded run can be shown with no network

**Exhibition**

- Presentation, EN and JP
- A1 poster, booth 15-05
- Demo video
- Sample-parts prompt library
- Stand pack: visitor scripts, setup checklist, risks and fallbacks

## Out of scope (Phase 1)

| Not in Phase 1 | Where it stands |
|---|---|
| Full assemblies with mates and a BOM | Not started |
| Integration into NX, Teamcenter or any in-house CAD system | Separate thread, after Phase 1 |
| The FreeCAD tool-calling approach | Separate thread. **Not part of this project and not to be quoted as expo evidence** |
| Drawing or sketch input | Not started |
| Tolerances and GD&T on the sheet | Deliberately omitted — see Drawing Generation |
| A deployed, multi-user service | Phase 1 is one laptop, serving 127.0.0.1 only |
| On-premise model hosting as a product | A local-model path exists and was used for the offline evaluation, but it is not a deployment |

## Deliverables

| Deliverable | Status |
|---|---|
| Working web prototype | Done |
| Standard-parts catalogue, 18 families | Done |
| A3 engineering drawing with DXF export | Done |
| Manufacturing cost estimate | Done |
| Japanese interface, end to end | Done |
| Prompt library (sample parts) | Done |
| Tech Expo presentation (EN / JP) | Done |
| Tech Expo poster (booth 15-05) | Done |
| Demo video | Done |
| Stand pack (overview, visitor script, setup, risks) | Done |

## Success criteria — proposed, for the team to accept or change

Phase 1 was built and demonstrated before success criteria were agreed,
so these are written against what is already measurable, with the
measured baseline beside each one. The baseline comes from a 32-prompt
sweep against a local Qwen3-VL-8B; see Evidence for how it was run and
what it does and does not show.

| Criterion | Proposed bar | Measured baseline |
|---|---|---|
| Produces a valid, watertight solid | ≥ 90% of library prompts | 88% (22 of the 25 that reached the model) |
| Correct on every measured dimensional check | ≥ 70% of library prompts | 56% (14 of 25) |
| Individual dimensional checks passed | ≥ 90% | 85% (95 of 112) |
| Standard part served exactly, no model call | 100% | 100% (7 of 7), mean 2.2 s |
| Time to a part a visitor will wait for | ≤ 30 s on a hosted model | 121 s mean on a small local model on a laptop |
| A wrong part is never presented as right | no exceptions | no counter-example observed; this is what the measured checks exist to enforce |

Two honest notes on that table. The 56% figure is dominated by the harder
tiers — catalogue 7/7 and easy 5/7, against medium 1/6 and hard 0/3 — so
the useful bar is probably per-tier rather than overall, and the team
should say which tiers Phase 2 is expected to reach. And the 121-second
mean is a small open model running on one laptop; it is evidence that the
loop closes, not a figure to compare against a hosted model.
