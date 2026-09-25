# Tech expo material

Four deliverables, plus the screenshots they are built from. Everything here is
content-first and format-agnostic: if the organisers hand over a corporate
template later, the text and figures lift straight into it.

| File | What it is |
|---|---|
| `CADSmith-Exhibition-Overview.xlsx` | Six sheets: the exhibit summary, the visitor script, the stand setup checklist, risks and fallbacks, every figure with its source, and the attribution. |
| `CADSmith-Presentation-Overview.docx` | One page: abstract, what a visitor sees, key messages, evidence, audience, logistics, attribution. |
| `CADSmith-Expo-Deck.pptx` | 15 slides with speaker notes. Slide 14 is the presenter slide. |
| `insert_presenter_photo.py` | Drops the presenter's headshot into slide 14 and removes the placeholder. |
| `img/` | Screenshots of the running application, captured 2026-09-24. |
| `*.pdf` | Rendered copies, for anyone without Office. |

## Before it goes out

Fill in the placeholders, which are written as `[ ... ]` in the deck and the
document, and shaded yellow in the workbook:

- presenter name, role and organisation;
- event name, date and stand number;
- contact email, and where the QR code should point.

Then add the photo:

```bash
python docs/expo/insert_presenter_photo.py path/to/headshot.jpg
```

That writes `CADSmith-Expo-Deck-with-photo.pptx` (add `--in-place` to overwrite
the original). The photo is centre-cropped to a square, so supply a portrait or
square headshot, 1000 × 1000 px or larger, plain background, even lighting.

## Where the figures come from

Every number in the deck and the document also appears on the workbook's
**Facts & Figures** sheet with its source. Two kinds are mixed deliberately and
are always labelled:

- **Measured here** — code size, test counts, catalogue families, and the
  32-prompt evaluation against a local Qwen3-VL-8B.
- **Published by the research team** — execution rate, Chamfer Distance, F1 and
  volumetric IoU, from arXiv:2603.26512.

## Attribution

The CADSmith pipeline in `autofab/` and the benchmark in `data/` are the work of
Jesse Barkley, Rumi Loghmani and Amir Barati Farimani (Carnegie Mellon
University), and are used unmodified. What is exhibited is the application built
around that pipeline. This division is stated on the stand, in the deck, in the
document and on the workbook's Attribution sheet — say it before you are asked.

## Rebuilding the material

The generators live outside the repository; the screenshots are reproducible
from a running server with Playwright. To reshoot them, start the app on port
8077 and capture at a viewport of 2000 × 1180 with `device_scale_factor` left at
1 — at 2 the browser's hit-testing and the viewer's camera framing both go
wrong, and the screenshots come out unusable.
