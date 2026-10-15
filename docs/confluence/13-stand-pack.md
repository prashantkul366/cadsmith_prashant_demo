# Exhibition Overview | Stand Pack

Everything needed to run the stand, as four files. Attach them to this
page; the summaries below are so somebody can decide which one they need
without opening any of them.

| File | What it is |
|---|---|
| `CADSmith-Exhibition-Overview.xlsx` | Six sheets: exhibit summary, visitor script, stand setup checklist, risks and fallbacks, every figure with its source, attribution |
| `CADSmith-Presentation-Overview.docx` | One page: abstract, what a visitor sees, key messages, evidence, audience, logistics, attribution |
| `CADSmith-Expo-Deck.pptx` | 15 slides with speaker notes. Slide 14 is the presenter slide |
| `img/` | Screenshots of the running application, captured 2026-09-24 |

Attach the PDF renders as well as the Office files — PDF previews
properly in Confluence and PPTX often does not.

## Still to fill in

Placeholders are written as `[ ... ]` in the deck and the document, and
shaded yellow in the workbook:

- presenter name, role and organisation
- event name, date and stand number
- contact email, and where the QR code should point

Then the presenter photo:

```bash
python docs/expo/insert_presenter_photo.py path/to/headshot.jpg
```

That writes `CADSmith-Expo-Deck-with-photo.pptx`; add `--in-place` to
overwrite. The photo is centre-cropped square, so supply a portrait or
square headshot, 1000 × 1000 or larger, plain background, even lighting.

## The two visitor scripts

**60 seconds, for a passing visitor.** Ask them for a part. Type
*spur gear 50 mm diameter* — it appears in about two seconds from the
catalogue with no model call. Point at the measured properties. Drag the
tooth slider from 18 to 34 and watch it rebuild with real involute teeth.
Switch to the drawing. Click 日本語.

**5 minutes, for someone who stays.** Type something no standard covers,
open the code panel while it runs, then the validation panel — every claim
the plan made, measured — then the iteration filmstrip including the
rejected attempts, then the token strip and the ceiling, then export a
STEP file and hand over the contact card.

Full minute-by-minute versions, including what to say and what to do if
each step goes wrong, are on the workbook's **Visitor Experience** sheet.

## The four risks that scored highest

From the workbook's **Risks & Fallbacks** sheet, which scores likelihood ×
impact:

| Risk | Score | Mitigation already in place | Fallback on the day |
|---|---|---|---|
| Venue network down or filtered | 16 | Catalogue parts, parameter edits, drawings, exports and replays were built to need no backend | Demo the catalogue path and replay a seeded run — both are real geometry |
| A visitor asks what is actually new here | 15 | The research is credited on the stand, in the deck and in the repository, and is unmodified | Answer directly — see *Attribution & Licensing* |
| Corporate TLS interception | 12 | OS certificate store, and `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` honoured. Verification never disabled | Phone hotspot, or run the offline path |
| Slow at the wrong moment | 12 | Catalogue parts answer in ~2 s; parameter edits rebuild in ~1 s with no model call | Open with the 2-second gear, start the long run, talk over it |

**The headline mitigation, worth remembering:** the parts of the demo a
visitor sees first — the catalogue, the sliders, the drawing, the exports
— need no network and no API key.

One risk on that sheet has no technical mitigation and is purely
operational: a laptop that sleeps or updates mid-show. Disable sleep and
automatic updates before the doors open, and leave the application
running.

## Setup checklist

The workbook's **Demo Setup** sheet has 17 items across hardware,
software, backend, network, space and content, each with an owner and a
status. Three are built in and ready; the rest are venue or presenter
items. Work from that sheet rather than from memory — the two that get
forgotten are a real mouse (the 3D view is orbited by dragging) and the
headless rasteriser.
