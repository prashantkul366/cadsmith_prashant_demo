# Manufacturing Cost Estimate

What the part costs to make: the stock it starts from, and the work on it.
Two numbers, and the reasoning between them, shown on screen in the
reader's language.

## What it is not

**It is not a quotation.** It is an estimate for comparing one design
against another — is the lightening pocket worth the machining time, is
stainless worth four times the aluminium — and the output says so on
screen. Nobody should put a figure from it in front of a customer.

## How it reaches a number

**The operations are read off the geometry, not asked for.** The geometry
is what is true: a hole is a hole whatever the plan called it, and a
pocket's volume is the volume the mill has to remove. What the Planner
contributes is the **material** and the **process**, because those are the
only two things the geometry cannot tell you — a 100 × 60 plate is
laser-cut sheet or a milled billet depending on nothing in the model.

The process decides the shape of the answer:

| Process | Stock | Why it differs |
|---|---|---|
| Milled | Billet, with an allowance on each face | Faced, then carved out of the envelope |
| Turned | Bar | The envelope is a cylinder, not a box |
| Sheet / fabricated | Sheet | Cut to outline — there is no envelope of metal to machine away, and costing one as a billet overstates it by an order of magnitude |

Then the operations, each one derived from something measurable:

| Operation | Driven by |
|---|---|
| Face the stock | The area of two faces |
| Rough out | Stock volume minus part volume, at the material's removal rate in cm³/min |
| Finish | The wall area the roughing leaves |
| Drill | Hole count × diameter × depth, at a feed scaled by material |
| Ream to fit | Fits named in the specification — a fit is reamed, not drilled, and that is read from the spec rather than guessed from a diameter |
| Deburr | Metres of edge |
| Setup | Per machine the part actually visits, divided across the batch quantity |

## What it refuses to price

Casting, moulding, 3D printing and extrusion. A moulded part is paid for
mostly in tooling, amortised over a run of thousands; a printed part is
paid for in machine hours against build volume. Neither is time at a
spindle. Costing one as a milled billet is not a rough answer — it is the
wrong question answered precisely — so the estimate says which process it
could not price rather than letting a number stand alone.

## The rates are meant to be edited

Every rate, feed and allowance lives in `app/costing/rates.toml`, and that
file exists so the numbers can be argued with. A number guessed inside the
code would be a number nobody could correct.

- **Currency:** JPY. **Rates last revised:** 2026-10-08, and the estimate
  shows that date, so a figure six months old says so.
- **Materials:** aluminium, steel, stainless, brass, titanium, plastic,
  plus an `unknown` fallback — each with density (physics, leave it
  alone), price per kilogramme as bought (the number to argue with), and
  removal rate in cm³/min (what turns a volume into minutes). Grade
  aliases are included, so *6061*, *SUS304*, *S45C*, *SPHC* and *A5052*
  all resolve.
- **Machines:** mill, lathe, laser, press, bench — each with an hourly
  rate and a setup time.
- **Times, stock allowance and batch quantity** are in the same file.

Units are stated on every line in that file, because getting them wrong
is the easiest way to be out by a thousand.

**Before this is used for anything real, somebody who knows the shop's
actual rates should go through that file once.** The defaults are starting
values, not local truth.

## On screen

The breakdown names the line each figure came from, so a number can be
traced to the rate that produced it. Each line is stored as what it says
rather than as the words — a key plus its numbers — so the card reads in
Japanese as readily as in English, the same way the validation checks and
the drawing notes already do.
