# How to build the Text 2 CAD space

Every page below is a file in this folder. Paste them in the order given;
each one stands alone, so a half-built space still reads.

```
Text 2 CAD
├── 📄 Project Details | Text to CAD          01-project-details.md
├── 📄 Project Scope | Phase 1                02-scope-phase-1.md
├── 📄 How It Works | Architecture            03-how-it-works.md         ← new
├── 📄 Version History | What Changed When    04-version-history.md      ← new
├── 📄 Drawing Generation                     05-drawing-generation.md   ← new
├── 📄 Manufacturing Cost Estimate            06-manufacturing-cost.md   ← new
├── 📄 Evidence | What We Measured            07-evidence.md             ← new
├── 📄 Attribution & Licensing                08-attribution.md          ← new, read this one first
├── 📄 Decisions & Review Feedback            09-decisions.md
├── 📁 Demo
│   ├── 🎬 Demo Video                         10-demo-video.md
│   ├── 🧩 Sample Parts | Prompt Library      11-sample-parts.md
│   └── 🖥️ Run It Yourself                    12-run-it-yourself.md      ← new
├── 📁 Documentation
│   ├── 📄 Exhibition Overview | Stand Pack   13-stand-pack.md           ← new
│   ├── 📁 PPTs
│   │   ├── 💻 Tech Expo PPT (EN)
│   │   └── 💻 Tech Expo PPT (JP)
│   └── 📁 Poster
│       └── 💡 Tech Expo 2026 Poster | 15-05
└── 📄 Roadmap | Next Steps                   14-roadmap.md
```

## Three changes to the plan, and why

**Attribution & Licensing is not optional.** The agent pipeline and the
100-prompt benchmark are Carnegie Mellon's work, published as
arXiv:2603.26512 and used unmodified. What is ours is the application
around it. That division is already stated on the stand, in the deck and
in the repository — so the wiki is the one place it would be missing, and
the wiki is where somebody from legal or from another division will look
first. Put it up early and the question never becomes a problem.

**The expo scope is narrower than the repository.** The FreeCAD work and
the NX work are later, separate threads and are not part of this. That
matters for one specific reason: the "61 of 61 prompts built clean"
figure was measured on the FreeCAD branch, and it must not be quoted as
expo evidence. `07-evidence.md` says which numbers may be used and where
each came from.

**Scope needs the cost estimate and the catalogue in it.** Your draft
listed the pipeline, the sliders and the outputs, but not the
standard-parts catalogue (18 families, no model call), the measured
specification checks, the spend ceiling or the manufacturing cost
estimate. All four are expo work and all four are things a visitor saw.

## Confluence mechanics

* **Markdown pasting.** If a paste arrives as plain text, use
  Insert (+) → **Markup** → **Markdown**. Confluence tables, headings and
  code blocks all survive that route; checkbox lists do not, which is why
  nothing here uses them.
* **Folders.** Hover the space name → **+** → **Folder**. `Demo` and
  `Documentation` at the top level, then `PPTs` and `Poster` inside
  `Documentation`.
* **Attachments.** Type `/` → **Files & images**, or drag into the editor.
  PPTX, PDF and MP4 all preview in place.
* **Emoji.** Click **Add emoji** above the title. 💻 decks, 💡 poster,
  🎬 video, 🧩 parts, 🖥️ setup.
* **Poster and decks:** attach the PPTX *and* a PDF. PDF previews properly
  in Confluence; PPTX often does not.
* **Video:** Confluence's upload ceiling is commonly 100 MB and is set by
  your admin. If the sped-up MP4 is over it, put it on SharePoint or
  Stream and link it — do not shrink it to the point where the dimensions
  on screen stop being readable, because being able to read them is the
  whole point of the clip.
* **Page order.** Confluence sorts the sidebar manually: drag pages into
  the order above once they exist.

## What still needs you

Four things nobody else can fill in:

1. **Dates** in `09-decisions.md`. The order of events is recorded there;
   the days are not.
2. **Success criteria** in `02-scope-phase-1.md`. A proposal is written
   there with the measured baseline beside it — it needs the team to
   accept or change the numbers.
3. **Three slide fixes** before `Parts.pptx` is attached: TL6 and EV1 have
   the wrong titles, and MC7 carries MC4's prompt text.
4. **The upstream licence.** See the open item at the bottom of
   `08-attribution.md`.
