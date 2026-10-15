# Evidence | What We Measured

Every number quoted on the stand, in the deck, on the poster or in this
space, with where it came from. Nothing here is an estimate; the
percentages are computed from the counts beside them.

## Read this before quoting a figure

Three different kinds of number exist in this project and mixing them is
the one mistake that would damage its credibility:

1. **Measured in this application** — ours, reproducible, quotable.
2. **Published by the research team** — Carnegie Mellon's results on their
   own benchmark, quotable *with the citation attached*.
3. **Measured on the FreeCAD branch** — a separate, later thread that is
   **out of this project's scope**. In particular the figure
   "61 of 61 prompts built clean" belongs to that thread. **Do not quote
   it as evidence for this project**, on a slide, a poster or this wiki.

## Measured in this application

**Scale of the work** (`wc -l`, 2026-09-24)

| | Lines |
|---|---|
| Application — Python | 22,300 |
| Application — browser JavaScript | 3,940 |
| Application — CSS and HTML | 1,576 |
| Research pipeline, unmodified | 4,704 |

**Testing**

| | Count |
|---|---|
| Automated tests (pytest), across 18 modules | 33 |
| Browser test suites (Playwright), each driving the real interface | 11 |

**Catalogue**

| | |
|---|---|
| Standard part families served with no model call | 18 |
| Catalogue prompts built correctly in the evaluation | 7 of 7 |
| Mean time to serve a catalogue part | 2.2 s (range 2.0–2.8) |
| Model tokens spent on a catalogue part | 0 |

**Local end-to-end evaluation** — 32 prompts in five tiers (catalogue,
easy, medium, hard, very hard), against a Qwen3-VL-8B running on the
presenter's own machine.

| | |
|---|---|
| Prompts in the sweep | 32 |
| Prompts that reached the model | 25 |
| Prompts that produced a valid solid | 22 of 25 (88%) |
| Prompts correct on every measured check | 14 of 25 (56%) |
| Individual dimensional checks passed | 95 of 112 (85%) |
| Mean time for an agent-built part | 121 s (median 110), 15 builds |
| Model tokens across the sweep | 387,302 over 139 calls |

Per tier, on the "correct on every check" measure: catalogue 7/7,
easy 5/7, medium 1/6, hard 0/3, very hard 1/2.

**Two caveats that belong with those numbers.** Seven prompts never
reached the model — the tunnel between the application and the local model
timed out with HTTP 524 — which is an infrastructure limit of that setup
and not a result. And this is a small open model on a laptop: it is
evidence that the loop closes end to end, not a claim about the state of
the art.

**Outputs and controls**

| | |
|---|---|
| Views on the generated drawing sheet | 4 — front, left, top, isometric, A3, first angle |
| Export formats | 5 — STEP, STL, GLTF, DXF, and the CAD source |
| Interface languages | 2 — English and Japanese, including run log, verdicts, title block and example prompts |
| Default token ceiling per run | 250,000, checked before every call |

## Published by the research team

From Barkley, Loghmani & Barati Farimani, **arXiv:2603.26512**, Results
table. Measured on their 100-prompt benchmark — 100 hand-written prompts
in three tiers, every reference script written and inspected by hand.

| | |
|---|---|
| Executable output — zero-shot, single call | 95% |
| Executable output — full pipeline, no vision | 99% |
| Executable output — full pipeline with vision | 100% |
| Mean Chamfer Distance — zero-shot | 28.37 mm |
| Mean Chamfer Distance — full pipeline with vision | 0.74 mm (a 38× reduction) |
| Median volumetric IoU — full pipeline with vision | 0.9629 |

Always cite these. They are the research team's results, not ours — see
*Attribution & Licensing*.

## What has not been measured

Worth saying plainly, because a gap somebody finds is worse than one you
declared:

- **Whether a drawing carries enough to make the part from.** Every number
  on a sheet is verified to be a real measurement of the solid. Nothing
  yet asks whether the sheet is *sufficient*.
- **Legibility of a crowded sheet.** Truth and readability are different
  checks. See *Drawing Generation*.
- **Performance on a hosted model, end to end.** The 32-prompt sweep was
  run against a local model. The same sweep on Bedrock has not been run.
- **Whether a small model can drive it.** Qwen3-VL-8B was the judge and
  coder in that sweep; whether a 4B-class model can is untested.
- **Anything beyond single parts.** No assemblies, no tolerances.
