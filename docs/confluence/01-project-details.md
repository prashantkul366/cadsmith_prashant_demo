# Project Details | Text to CAD

**Describe a part in plain English or Japanese; get a kernel-verified CAD
model, an A3 engineering drawing, a cost estimate and STEP/STL/DXF files.**

Exhibited at Yamaha Motor Tech Expo 2026, booth 15-05.

## In one paragraph

Text to CAD turns a written part description into manufacturable CAD. Five
AI agents plan the part, write parametric CAD source, build it in a real
CAD kernel, and measure what came out. The measurement is the point: a
text-to-CAD system that only generates will happily produce a part that
looks right and is 3 mm out, which cannot be manufactured. Here the
kernel's own measurements are checked against what the plan claimed, and a
part that falls short is rejected and corrected rather than handed over.

## At a glance

| | |
|---|---|
| Status | Working software, demonstrated live |
| Input | Natural language, English or Japanese |
| Output | Parametric CAD source, STEP, STL, GLTF, DXF, A3 drawing, cost estimate |
| Interface | Local web application, one laptop, no GPU |
| Model backend | Claude on Amazon Bedrock — Sonnet 5 plans and codes, Opus 5 judges |
| Works offline | Partly: standard parts, parameter edits, drawings, exports and run replays need no network at all |
| Languages | English and Japanese throughout, including the drawing title block |
| Research basis | CADSmith, Carnegie Mellon University, arXiv:2603.26512 — see Attribution |

## What a visitor saw

A text box, and no CAD interface to learn. Typing *spur gear 50 mm
diameter* returned a finished gear in about two seconds, served exactly
from the standard-parts catalogue with no model call at all. Dragging the
tooth-count slider from 18 to 34 rebuilt it with 34 real involute teeth in
about a second, still with no model call, because what was generated is
parametric source and not a mesh.

Typing something no standard covers — *a NEMA 23 motor mounting plate,
100 mm square and 8 mm thick, with a 38.1 mm pilot bore* — put the five
agents to work with their reasoning visible as it happened: the plan, the
CAD code as the Coder wrote it, the kernel's measurements, the Judge's
verdict, and every rejected attempt kept alongside the one that passed.

Then the Drawing tab: a dimensioned A3 sheet, four views, first-angle
projection, title block. Then 日本語, and the entire interface, run log,
verdicts and title block in Japanese. Then Export, and a STEP file in the
downloads folder that their own CAD system opens.

## Why it matters

Three claims, in the order they are worth making:

1. **A wrong part is caught.** The CAD kernel measures the solid and the
   measurement overrules the vision model. A plate specified with four
   holes that builds with one is blocked, however confident the Judge was.
2. **The output stays editable.** The artefact is parametric source, not
   geometry. Every dimension the plan named remains a number somebody can
   change, and the kernel rebuilds in about a second.
3. **It ends in something a shop can accept.** A dimensioned sheet, a
   STEP file and a DXF — not a picture of a part.

## Where everything is

| | |
|---|---|
| Scope, and what was deliberately left out | Project Scope \| Phase 1 |
| The five agents and the two correction loops | How It Works \| Architecture |
| What changed between the first version and the demonstrated one | Version History |
| The drawing, and the standards it follows | Drawing Generation |
| The cost estimate, and what it is not | Manufacturing Cost Estimate |
| Every number quoted anywhere, with its source | Evidence \| What We Measured |
| Whose work is whose | Attribution & Licensing |
| Video, sample parts, and how to run it | Demo |
| Decks, poster, stand pack | Documentation |
| What comes next | Roadmap \| Next Steps |
