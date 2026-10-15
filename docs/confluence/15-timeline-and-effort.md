# Timeline & Effort

Measured from the repositories, not reconstructed from memory. Dates and
times are **IST (+05:30)**, which is where the work was done; git stores
them in UTC and they are converted here.

## Headline

| | |
|---|---|
| Span | 30 Aug 2026 → 15 Oct 2026 — **47 calendar days** |
| Days worked | **15** (32 days of the span had no commits) |
| Sittings | **34** — a sitting is a run of commits with no gap over 90 minutes |
| Active build time | **≈ 53 hours** |
| Commits | **222** — 220 in the main repository, 2 in the first one |
| Distinct changes | **193** — 27 commits are the same fix carried onto a second branch |
| Code written | **67,318 lines added, 4,598 removed**, across 871 file-touches |
| The application grew | **5,777 → 44,124** lines of our own Python |
| Tests grew | **10 → 52** test files |
| Branches | **9** — five on the expo line, four on the threads after it |

Two things that figure does **not** include, and both are substantial:
the upstream research pipeline (4,445 lines, used unmodified), and all of
the time spent outside the repositories — the meetings, the poster, the
two decks and their review rounds, running the application on a Windows
machine, capturing screenshots, and the expo itself.

## How effort was measured

Two independent methods, which agree:

1. **From the commits.** Sort every commit; a gap of more than 90 minutes
   starts a new sitting; each sitting counts as last − first + 20 minutes
   for the work that preceded its first commit. This is the standard way
   to recover effort from a repository and it is conservative: work that
   produced no commit is invisible to it.
2. **From a session log.** One Claude session transcript survives in the
   working container, covering **6 Oct 08:49 → 15 Oct 12:40 UTC**. Counting
   ten-minute windows that contain any activity gives **24.6 hours** over
   that period. The commit method gives **26.8 hours** for the same days —
   **within 9%.**

Earlier sessions ran in containers that no longer exist, so their logs
are gone; for 30 Aug → 9 Oct the commit method is the only evidence, and
the agreement above is the reason to trust it.

**Read "53 hours" as the build time visible in the repositories.** It is
a floor, not a ceiling.

## Phases

| Phase | Commits | Hours | From | To | Days |
|---|---|---|---|---|---|
| A — First web app | 24 | 3.9 | 30 Aug | 31 Aug | 2 |
| B — Bedrock, Japanese, catalogue, drawing | 20 | 7.3 | 7 Sep | 15 Sep | 3 |
| C — Measured checks, grading, first real-model eval | 20 | 5.3 | 21 Sep | 21 Sep | 1 |
| D — UI refresh and the expo pack | 22 | 6.4 | 21 Sep | 24 Sep | 3 |
| E — Handlebar case study (shared trunk) | 12 | 3.2 | 24 Sep | 25 Sep | 2 |
| G — FreeCAD tool road | 58 | 13.8 | 6 Oct | 9 Oct | 4 |
| F — Sheets and cost trunk | 28 | 5.9 | 7 Oct | 8 Oct | 2 |
| K — Handlebar case study, final | 6 | 1.0 | 8 Oct | 9 Oct | 2 |
| J — Cost, drawing audit, Confluence | 9 | 1.7 | 8 Oct | 15 Oct | 3 |
| H — YMRI feature tree | 15 | 3.2 | 14 Oct | 14 Oct | 1 |
| I — NX | 6 | 1.2 | 15 Oct | 15 Oct | 1 |
| **Total** | **220** | **52.9** | **30 Aug** | **15 Oct** | **15** |

Phases A–E are the expo work. G, H and I are the later threads — the
FreeCAD tool road, the YMRI feature tree and NX — which are **not** part
of the expo project. Where a sitting touched two branches its hours are
split between them in proportion to its commits.

## Day by day

| IST date | Day | Window | Hours | Commits | What was done |
|---|---|---|---|---|---|
| 30 Aug | Sun | 22:57–00:50 | 2.2 | 14 | **The first app, in one sitting.** App scaffolding, zero-touch pipeline instrumentation, job manager, HTTP server, the front end — STL viewer, live pipeline, plan and verdict panels. Natural-language edits and replay. OpenAI, Ollama and any OpenAI-compatible backend. PowerShell launcher and Windows notes. **An engineering drawing sheet from real orthographic projections** — it was there from the first night. Upstream credit added to the README |
| 31 Aug | Mon | 10:11–11:33 | 1.7 | 10 | Hardening. A preflight that fails fast instead of hanging. Trust the OS certificate store, for networks that inspect TLS. Find a venv named either way. Clear the previous run's panels. Fix the active stage escaping its container. A mock provider |
| 7 Sep | Mon | 15:56–22:42 | 3.9 | 13 | **Bedrock, and the two apps merged.** Bedrock backend streaming the model's real reasoning. Catalogue, grounding, measured checks and the spend ceiling brought together. Japanese added, with the model kept reading English. UTF-8 instead of the locale codec. Token budget sized for thinking. A one-call check that the live SDK streams what the app expects, plus a model/config sweep. *Also, in the first repository: the Bedrock backend and the IoU/analyzer fixes, merged as PR #1 at 12:55* |
| 14 Sep | Mon | 09:17–15:16 | 2.2 | 5 | **The drawing became an engineering drawing**, lettered like one, with DXF through ezdxf. A parameters view on the code panel. The catalogue made to work when nothing else is configured |
| 15 Sep | Tue | 11:17–12:10 | 1.2 | 2 | The drawing built when the part is, not when someone asks. Reasoning effort on the panel, variable per run |
| 21 Sep | Mon | 01:48–20:00 | 7.3 | 27 | **The heaviest day — three threads.** *Measurement:* count what the model actually builds with; let a rejected attempt explain itself by measurement and not only by the Judge; grade by difficulty and by the edit chain an engineer works in; say where the holes are, not just how many; material and closeness; hold the request's own numbers fixed; stop handing keys to generated code. **The first real-model run recorded — Qwen3-VL-8B over the tiered prompt set.** *Bedrock diagnostics:* which AWS identity is in use, where each variable came from, global vs regional profile chosen on purpose, why Bedrock cannot run. *UI:* the design's shell, the left column as a conversation, the right column as four cards, dimensions beside the part they change, the reasoning given the centre |
| 22 Sep | Tue | 00:40–17:31 | 3.5 | 13 | **UI refresh continued.** A movable left rail; then one panel, every version numbered, and undo. The gizmo turns the model. The app made readable in Japanese. Gear sizing — above the undercut limit, askable by diameter, and serve the shaft it goes on. A sentence printing as NaN, and a size the kernel disputed, both fixed |
| 24 Sep | Thu | 14:25–19:23 | 2.0 | 8 | **The expo pack written** — exhibition overview, deck and stand documents — and the screenshots captured. Viewport kept out of the rails. Then the **handlebar case study** opened: bend a handlebar from the five numbers a bar is sold by, serve one from the catalogue in either language, measure a bar once it is bent and say what the bending cost |
| 25 Sep | Fri | 10:48–16:22 | 2.2 | 6 | Handlebar finished: four bends offered instead of declining, the words the trade actually uses, a bent tube dimensioned along its path rather than around its box. OpenAI-compatible calls streamed. **"Edit an imported solid that arrived without a feature tree"** — the commit all three later threads fork from |
| *26 Sep – 5 Oct* | | | | | *No commits — 10 days* |
| 6 Oct | Mon | 13:16–17:45 | 4.8 | 15 | **The FreeCAD tool road opens.** Plan a part, build it in FreeCAD, then measure what came out. Work in the part the engineer already has open. Give the loop real tools — catalogue, features, then primitives. Build one step at a time. Read a FreeCAD property as a number and pattern what repeats. Say in the health panel whether FreeCAD is actually there. Stop paying for round trips that bought nothing |
| 7 Oct | Tue | 10:25–00:01 | 6.9 | 36 | **Most commits of any day.** Read a request the way a drawing office writes one, threads included. Drill into a face, chamfer an edge, refuse a hole that cut nothing. Translate the FreeCAD API names a small model reaches for. Round a corner, so an outline can be a shape. Build the shape of the part, not a pile of boxes. Cut the part open where a drawing would. **All 61 library prompts built.** On the other branch: the gate stopped failing parts over numbers that are not sizes, and a tunnel hostname was taken out of a committed eval record |
| 8 Oct | Wed | 00:01–23:26 | 9.8 | 40 | **Most hours of any day.** **The cost model** — the stock a part starts from and the work on it, then on screen in the reader's language. **The sheet made machinable:** a hole's depth read off the solid rather than off the circle it projects to; a view dimensioning what it cuts, not only what it encloses; every number a callout prints counted. A Japanese run read in Japanese, Design Plan included. And a long run of Bedrock resilience across three branches: take the default from the account rather than a constant, probe for an id that answers, never re-address a run by an id the account has denied, probe the Judge's model too, and fit the reply to the window instead of guessing at it |
| 9 Oct | Thu | 10:38–11:02 | 0.7 | 9 | Short and sharp: save every drawing and say which of them can be trusted; stop a hole count being read as a dimension; spell the count sign the same way everywhere; take the overall dimension across the outline, not off a vertex |
| *10 – 13 Oct* | | | | | *No commits — 4 days. The YMRI meeting falls in here* |
| 14 Oct | Tue | 12:26–18:54 | 3.2 | 15 | **The YMRI thread.** The feature tree on screen, editable, over the live document. Read and write the document's tree. Give the model the same tree the engineer has, and an undo for both. A name means the part now, not the part it was four holes ago. Make a drawing from any solid, not only one this app built. The plan re-ordered to what the meeting asked for, and the pilot made something engineers can start on their own. Plus drawing legibility: count what makes a sheet unreadable as against untrue |
| 15 Oct | Wed | 13:10–14:12 + | 1.4 | 7 | **NX.** The half of it that can be made correct without NX, then one turn of the conversation testable with no NX and no model, a self-check for what NX Open actually offers, the three journals and the endpoint they talk to, and a bare Claude-plus-Bedrock-plus-NX folder whose request signer is verified against botocore. **Plus this Confluence space.** *Figure is partial — the day is not over* |

## What the shape of it says

**The expo was built in 11 working days and about 28 hours**, across
30 Aug → 25 Sep. The first working application — viewer, live pipeline,
plan and verdict panels, multi-provider backend and an orthographic
drawing sheet — existed after **one 2.2-hour sitting on a Sunday
night**.

**The work was bursty, not steady.** 15 working days inside a 47-day
span, with a 10-day gap and a 4-day gap in it. Three days — 21 Sep, 7 Oct
and 8 Oct — account for **24 of the 53 hours and 103 of the 220
commits**: 45% of the effort in 20% of the working days.

**Over half the total went to what came after the expo.** Phases F, G, H,
I, J and K — the FreeCAD tool road, the drawing and cost work, the YMRI
feature tree and NX — are **26.8 hours**, against 26.1 for phases A–E.
The expo was the first half of the project, not the whole of it.

**Verification was a large and deliberate share.** Test files went from
10 to 52 over the period, and whole sittings produced no feature at all
— the Bedrock diagnostics on 21 Sep, the drawing audit on 9 Oct, the
re-run of all 61 prompts on 7 Oct that moved no number. That is the cost
of being able to say which figures are measured, and it is why the
evidence page can name a source for every one of them.

## Caveats

- Commit timestamps are when a commit was authored. Work that was done
  and not committed — reading, running the application, diagnosing on the
  Windows machine — leaves no trace in this and is not counted.
- The 90-minute gap threshold is a judgement. A longer one would report
  more hours, a shorter one fewer. It was chosen before the numbers were
  looked at, and the session-log cross-check above is what justifies it.
- 15 Oct is incomplete.
- Only one session transcript survives in the container. Earlier ones are
  gone, so the cross-check covers 6 of the 15 working days.
- Everything here measures the repositories. Nobody's calendar was
  consulted, and the hours spent on the poster, the decks, their review
  rounds, the meetings and the expo itself are not in these numbers at
  all.
