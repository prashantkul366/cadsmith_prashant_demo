# Decisions & Review Feedback

Two records. The first is what reviewers said about the expo material and
what changed as a result. The second is the engineering decisions that
shaped the application — the ones where a different choice would have
produced a visibly different demo.

There are no minutes of meetings for this project, so these two tables
are its history.

## Review feedback on the poster and the decks

Dates still to be filled in — the order is right, the days are not.

| Date | Feedback / decision | Action taken |
|---|---|---|
| YYYY-MM-DD | Key-point text should focus on the value proposition | Rewrote the summary around reduced design effort and less dependence on CAD specialists |
| YYYY-MM-DD | Summary wording: use 「変更はすぐにモデルへ反映します」 | Updated the Japanese summary |
| YYYY-MM-DD | Walkthrough and Demo slides overlap | Combined into one slide with the video and step timestamps |
| YYYY-MM-DD | Project name inconsistent (Text2CAD / Text-to-CAD) | Standardised on "Text to CAD" |
| YYYY-MM-DD | Poster too text-heavy | Rebuilt as a visual-first poster: What is it / Why it's useful / How it works / What can I do |
| YYYY-MM-DD | Development-phase row not needed on poster | Removed |
| YYYY-MM-DD | "Try the Demo" play icon adds nothing | Replaced with an interface screenshot |
| YYYY-MM-DD | Example parts (I-beam, washer, gear) not Yamaha-relevant | Replaced with steering wheel hub adapter, shaker head adapter plate, HTD 5M timing pulley and battery module end plate |

## Engineering decisions

Each of these is a place where the obvious choice was not the one taken,
and the reason is the interesting part.

| Decision | Why |
|---|---|
| **The kernel overrules the vision Judge** | A vision model is confident about a plate with the wrong number of holes. A measurement is not. Where they disagree the measurement wins, and the version is blocked |
| **The Judge is a stronger model than the Coder** | Opus 5 judges what Sonnet 5 wrote, so the pipeline is not grading its own homework |
| **Standard parts never reach a model** | A bearing has a published dimension. Asking a model for it introduces a chance of being wrong where there was no need for one. 18 families, served exactly, 2 seconds, zero tokens |
| **The catalogue refuses ambiguous requests** | A router that guesses is worse than no router, because it is wrong silently. Anything ambiguous goes to the agents |
| **What is generated is source, not geometry** | A mesh is a dead end. A parametric script means every dimension the plan named is still editable, and the sliders are real editing rather than re-generation |
| **A per-run token ceiling** | A loop that will not converge is a bill. 250,000 tokens by default, checked before every call; the run stops and keeps what it produced |
| **Every attempt is kept and shown, failures included** | A visible failure is better evidence than a hidden one, and on the stand it was more convincing than the successes |
| **The drawing is built when the part is** | Projection takes real time. Doing it on tab-open makes the interface feel broken; doing it with the build makes the tab instant |
| **First-angle projection** | It is the convention in use here, and the symbol on the sheet tells a reader which system they are in |
| **No tolerances on the drawing** | Nothing in the pipeline has specified any. A general tolerance note on an untoleranced drawing would be a claim rather than a fact |
| **Cost rates live in an editable file, not in code** | A number guessed inside the code is a number nobody can correct. Every rate, feed and allowance is in `rates.toml`, with its units stated |
| **The cost model refuses to price casting, moulding, printing and extrusion** | Those are paid for in tooling or machine hours, not time at a spindle. The wrong question answered precisely is worse than no answer |
| **Japanese is first-class, not a translation layer** | The interface, run log, verdicts, drawing title block and example prompts are all Japanese, and a Japanese request for a standard part is understood as typed. Text is read and written as UTF-8 rather than the locale codec, without which Japanese on Windows is mojibake |
| **The research pipeline is not modified** | It keeps the published benchmark reproducible and keeps the attribution honest. Instrumentation is attached from outside it |
| **The demo works without a network** | Catalogue parts, parameter edits, drawings, exports and run replays need no backend. This was the single most valuable decision on the stand |
| **The application serves 127.0.0.1 only** | Nothing is exposed. There is no inbound surface to review |

## Decisions still open

| Question | Who decides |
|---|---|
| Success criteria for Phase 1 — a proposal with measured baselines is on *Project Scope \| Phase 1* | The team |
| The upstream licence, and what it permits — see *Attribution & Licensing* | To be assigned |
| Shop rates in `rates.toml`: the defaults are starting values | Manufacturing |
| Which tiers Phase 2 is expected to reach | The team |
