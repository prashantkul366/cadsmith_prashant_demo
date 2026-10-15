# Drawing Generation

An A3 engineering drawing of the part as built, projected from its STEP
solid. Not a render, not a screenshot with numbers on it — real
orthographic projection through the CAD kernel's hidden-line algorithm, so
any part the pipeline can build gets a correct drawing rather than a
picture of one.

It is produced when the part is, not when somebody opens the tab, and it
needs no model call.

## What is on the sheet

- **Four views** — front, left, top and isometric
- **First-angle projection**, with the first-angle symbol on the sheet
- **One stated scale**, a preferred ratio, chosen as the largest that fits
- **Centre lines**, and hidden detail dashed
- **Dimensions**, including bore depths read off the solid
- **A title block**, in English or Japanese
- **DXF export** from the same geometry

## The conventions, and where they come from

What makes it a drawing rather than four pictures is the convention, so
each one is taken from the standard rather than from taste.

| | Standard | What it means here |
|---|---|---|
| Projection | ISO 128-30:2001, A.2 | First angle: the view from above goes underneath, the view from the left goes on the right. The sheet carries the first-angle symbol — the truncated cone drawn in that system |
| Line types | ISO 128-2 | Two widths in a 2:1 ratio: thick continuous for visible outlines, thin for everything else |
| Dimensions | ISO 129-1 | Extension lines start clear of the feature and run 1.5 mm past the dimension line; values sit above the line and read from the bottom of the sheet |
| Scale | ISO 5455 | A preferred ratio, stated in the title block. A drawing fitted to its frame cannot be measured; one drawn at 2:1 can |
| Sheet | ISO 5457 / ISO 216 | A3 landscape, 20 mm binding edge, 10 mm elsewhere. One SVG unit is one millimetre throughout |

First angle rather than third is deliberate: it is the convention in use
here, and the symbol on the sheet says which system a reader is in.

## What the sheet deliberately does not carry

**No tolerances and no material.** Nothing in the pipeline has specified
either, and a general tolerance note on a drawing nobody has toleranced
would be a claim rather than a fact. The sheet describes the model as
built. Adding tolerances is Phase 2 work and needs somebody to decide
them, not a default.

## The check that matters

A sheet nobody looks at is not a drawing, so every drawing the app has
produced is written out with an index page and each one is checked.

The check is not "is there a dimension here". Each number on the sheet is
read back and matched against a length derived from the projection
**independently of the code that chose it** — the bounding box, the
circles and where they sit, the pitch between any two like holes, the
pitch circle of a ring of them, the extent of every closed loop cut into
the outline, and the depth of every bore the kernel found. A sheet is
labelled with whether every number on it survived that.

The reason for going to that length: a missing dimension is a gap
somebody notices and asks about. A number that measures nothing is a
drawing that lies, and somebody machines to it.

```
.venv/bin/python -m app.tools.sheets [runs_dir] [out_dir]
```

## Known limits

- **Legibility is a separate question from truth.** The check above
  establishes that every number is a real measurement. It does not
  establish that no two dimensions overlap or that a crowded sheet reads
  well. A placement and legibility audit was written later, on the branch
  that is outside this project's scope, and its results should not be
  quoted here until it has been re-run against this branch.
- **Sufficiency is also a separate question.** Nothing yet asks whether
  the sheet carries *enough* to make the part from — only that what it
  carries is true. That is an open item on the roadmap.
- Projection runs in a subprocess, matching how the pipeline isolates
  kernel work: a kernel failure takes down the worker, not the server.
