# What has actually been checked, on both branches

Both roads were run against the 61-prompt Yamaha Text-to-CAD library on
2026-10-07. This is the record of what was measured, what it measured
with, and what is still the model's to get right rather than the app's.
Nothing here is an estimate: every number below came out of a run whose
command is given at the end.

The two branches are two different answers to the same question, so they
are checked differently and the difference is the point:

| | `claude/freecad-mcp` | `claude/handlebar-case-study` |
|---|---|---|
| How a part is made | the model calls FreeCAD tools, one feature at a time | the model writes a CadQuery script, which is executed |
| Where geometry can go wrong | one tool call, measured and refused on the spot | anywhere in a script that only runs or does not |
| What the person ends up with | a FreeCAD document with a feature tree | a solid and the script that made it |
| What is shared | the request gate, the drawing, the standard-part catalogue, the model adapter | |

Because the second road reaches geometry only through a language model,
"does the branch handle this prompt" has two separate answers on it, and
they are reported separately below rather than rolled into one number.

---

## 1. `claude/freecad-mcp`: the tool road, against live FreeCAD

FreeCAD 26.3.0, headless, served on port 9875; every call went to the
real kernel.

| | |
|---|---|
| Prompts built | **61 of 61** |
| Tool calls accepted | **931 of 931** — nothing refused |
| Holes cut as hole features | **401** |
| Solids watertight | **61 of 61** |
| Drawing sheets produced | **61 of 61** |
| Parts with working parameter sliders | 14 |
| Kernel time, all 61 | 410 s |

The calls in this run were written by hand, one list per prompt. That is
a statement about the *vocabulary* - every one of the 61 parts is
reachable with the tools the app offers, and the kernel accepts all 931
calls - and not about any model's ability to choose them. Section 5 is
the measurement that settles that, and it is a different number.

## 2. `claude/handlebar-case-study`: the gate, the sheet and the catalogue

This branch has no FreeCAD road, and generating a CadQuery script needs a
model. What it does *not* need a model for is everything that happens to
a part once it exists - and that is where this branch was failing correct
parts on screen. So each of the 61 prompts was handed the **correct
solid** (the STEP the tool road built for the same prompt) and the
branch's own code was asked what it makes of it.

| | |
|---|---|
| Requests read by `stated.requirements` | 61 of 61, **no false size, no false hole count** |
| `spec.check` verdict on a correct part | **PASS on 61 of 61** |
| Measured checks run across the library | 180 |
| Advisory rows that differ (non-blocking) | 12 |
| Drawing sheets produced by this branch's `drawing.py` | **61 of 61** |

The 12 advisories are all correct and none of them blocks: nine are
holes that are not a stock drill size (a Ø22.2 handlebar bore, a Ø104
sprocket bore - bored, not drilled), two are parts genuinely thinner than
0.8 mm (a 0.15 mm interconnect foil, a 0.35 mm stator lamination), and one
is a 2 mm read out of the wheel-centre-cap request as an overall size,
which stays an advisory note and never a red row.

Read that table next to what it used to do: before the gate fix, **12 of
these 16 prompts handed the gate a size the request never stated**, and
several over-counted the holes, so correct parts came back red. Now none
do.

## 3. Both branches: the catalogue stops answering with hardware

The standard-part catalogue is identical on both branches and runs
*first* on both, before any model call. Over the 61 prompts it was
answering **7** of them from stock, **6 of them with the wrong part**, and
reporting the job converged:

| prompt | was served |
|---|---|
| handlebar vibration fixture pedestal | an M6 socket head cap screw |
| oil filler cap | an O-ring, 20 ID × 1.5 cord |
| lower triple clamp | an M8 socket head cap screw |
| handlebar display clamp | an M3 socket head cap screw |
| welding fixture V-block | a dowel pin, 100 × 80 |
| SCARA tool flange | a shaft, 6 dia × 42 |
| hex flange bolt M8x1.25 × 30 | a hex head *bolt* - no flange |

On this machine the two optional catalogue libraries are not installed,
so those six fell through to the pipeline and the damage was invisible.
On a machine with `app/requirements-catalog.txt` installed - which is the
machine a demo runs on - six of the 61 prompts return a screw.

**0 of 61 route now**, and every standard-part request in the existing
tests still routes to exactly what it did before.

## 4. Both branches: an endpoint behind a tunnel

A self-hosted vLLM is reached through a tunnel, and a Cloudflare quick
tunnel stops waiting on a slow generation after about 100 s and answers
524. That was ending whole runs - on the tool road, at the *planning*
step, before a feature had been built - and, worse, a 524 on the streamed
path was being read as "this endpoint cannot stream", which switched
streaming off for the rest of the session and made every later reply more
likely to time out.

A 524, a 502/503/504, a Cloudflare 52x and a dropped connection are now
the one failure worth asking again: three attempts, 6 s then 18 s, each
wait in the run log, then it fails and names the count.
`CADSMITH_GATEWAY_ATTEMPTS` raises it. Nothing else is retried.

## 5. `claude/freecad-mcp`: with a model actually choosing the calls

Run against a `Qwen/Qwen3-VL-8B-Instruct` served by vLLM behind a tunnel -
a deliberately small model, and the slowest realistic transport.

The first attempt did not build anything at all. Asked for a 25 mm cube,
the model answered `Part.makeBox(25, 25, 25)`: it was writing the FreeCAD
API it had been trained on rather than reading the tools it had been
handed. The toolbox refused it by name, three times, correctly, and the
model answered the same way each time. Three frictions of that kind were
found and closed:

* **the names** - seventy-odd FreeCAD and CadQuery names mapped onto the
  tools that exist, with the argument the name itself states filled in,
  so `makeBox` arrives as `add_shape` with `kind="Part::Box"`.
* **the arguments** - eighteen tools' worth of renames, only ever onto a
  property that tool declares: `position` → `at` on `drill`, `edges` →
  `where` on the chamfers, `XSize` → `Length` on `add_shape`.
* **the threads** - every prompt in the library quotes the pitch, and the
  tool answered only to a bare `M8`. `M8x1.25` now reads, and the pitch
  is used: the tapping drill is the major diameter less the pitch, which
  is what the ISO 262 table is, so a fine thread taps correctly (M20x1.5
  → 18.5) instead of being given its coarse row.
* **the reply shape** - the loop's own reminder tells a model that cannot
  use the tool channel to answer with `{"tool": ..., "arguments": {...}}`,
  and when the model did exactly that it was still dropped. Asked for the
  300 mm plate it answered with an `extrude_profile` and a
  `pattern_circular`, one object per line, with the profile's points
  written as Python tuples. Two different readers disagreed about what a
  written-out call is: one parsed the reply as a single JSON document, so
  the second call was lost and the tuples made a syntax error of both.
  There is one reader now, it reads every brace-balanced object in a
  reply, and it accepts Python literals - which is what a model writing a
  call by hand actually writes.

Same prompt, same model, before and after: *"the builder did not make
anything in FreeCAD"* → **converged in 25 calls and 108 s**, as a FreeCAD
feature tree.

## 6. Two things found while checking, and fixed

* **A tunnel hostname was committed.** `app/tools/eval-qwen3vl-8b.json`
  carried a Cloudflare quick-tunnel hostname eight times, inside the HTML
  of 502 and 530 error pages an earlier eval recorded. No API key, and
  those hostnames are ephemeral and long dead, but they are not this
  repository's business: they are replaced with `the-endpoint.example` on
  both branches. They remain in the history of the commits that added
  them; say the word and that history can be rewritten.
* **`test_layout` had gone stale on `claude/handlebar-case-study`.** It was
  measuring `.rsplit > .rsec`, a structure the page stopped having on
  2026-09-22, so it threw instead of checking anything and the failure
  read as a browser problem. It now measures the cards the page does have,
  and passes across five viewports and both languages.

## 7. What is still the model's, not the app's

On the script road the geometry is whatever the model writes, and an 8B
writes a poor part. Measured on the 25 mm instrumentation cube: the
pipeline produced a watertight 25 × 25 × 25 cube with **one** Ø5.5 hole
where four tapped holes were asked for. Both of the app's own checks
caught it - the gate failed the hole count 4 vs 1, and the vision Judge
said the render shows one hole on the top face and none on the sides - so
the run reported itself *not converged* rather than claiming a part it had
not built. That is the app behaving correctly with a weak model, and no
amount of work on the app changes the part. A stronger generation model
does.

That is the honest shape of the difference between the two roads, and it
is the argument for the tool road: on it, a wrong number costs one
refused call and the part carries on; on the script road it costs the
part.

## 8. How to reproduce any of it

```sh
# the tool road, all 61, against a headless FreeCAD on 9875
python3 app/tools/freecad_server.py --port 9875 &
python3 -m app.tools.freecad_check --port 9875

# the whole test suite, both branches
for t in app/tests/test_*.py; do python3 -m app.tests.$(basename $t .py); done

# the catalogue's refusals, and the thread and alias tables
python3 -m app.tests.test_catalog
python3 -m app.tests.test_freecad_tools
python3 -m app.tests.test_toolbox
python3 -m app.tests.test_providers
```

Pointing the app at a self-hosted endpoint needs three settings in `.env`
and nothing else; `CADSMITH_LLM_BASE_URL`, `CADSMITH_LLM_MODEL` and
`CADSMITH_LLM_API_KEY`, with `provider: "custom"` on the job. No key or
URL belongs in this repository and none is in it.
