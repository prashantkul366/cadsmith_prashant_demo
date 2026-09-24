# Handlebar case study — where the dimensions come from

The brief: one real part, several designs from one definition, dimensions
taken from bikes that exist, and a drawing that matches the reference ED.
This file is the grounding for the numbers. Nothing in the builder should
carry a dimension that is not either in this file or derived from it.

## How a handlebar is measured

Four measurements name a bar, and they are the four the industry uses
([Lowbrow Customs, Handlebars 101][lowbrow]):

| Term | What it measures |
|---|---|
| **Width** | tip to tip, at the widest point, where the grips go |
| **Rise / height** | bottom of the bar up to where the hands grip it |
| **Pullback / sweep** | how far back the tips sit from the clamp line |
| **Centre (clamp) area** | the straight at the bottom that the risers clamp, before the bends start |
| **Control length** | the straight at each end that the grip, throttle and switchgear need |

Riser spacing is its own constraint, not a bar dimension: 3½ in (88.9 mm)
centre to centre on most Harleys, 4¾ in (120.7 mm) on springer front ends.

## Tube

| Size | Where it is used |
|---|---|
| **7/8 in — 22.2 mm** | older metric bikes, and nearly all current sport and commuter bikes |
| **1 in — 25.4 mm** | Harley-Davidson standard after 1990 |
| **1¼ in — 31.8 mm** | thicker bars, turned down to a 1 in clamp area so standard risers still fit |

The reference ED is the metric case: **Ø22 outside, Ø18 inside — a 22 mm
tube with a 2 mm wall.**

## Real bars, measured

Four production bends from one maker, so the shape of the numbers is
consistent ([Renthal 7/8 in road bars][renthal], dimensions in mm):

| Bend | Width | Height | Rise | Clamp area | Sweep | Control length |
|---|---|---|---|---|---|---|
| 758 Ultra Low | 725 | 75 | 50 | 110 | 95 | 232 |
| 754 Low | 730 | 105 | 75 | 105 | 125 | 242 |
| 755 Medium | 725 | 115 | 85 | 105 | 105 | 223 |
| 756 High | 710 | 120 | 105 | 105 | 105 | 200 |

Two more points, from different classes of bike:

| Bar | Width | Rise | Tube |
|---|---|---|---|
| Royal Enfield Classic 350, OEM (591993/F) | 737 (29 in) | 152 (6 in) | 22 mm |
| The reference ED | 648 | 186 overall, 126 to the first bend | Ø22 × 2 wall |

Stated ranges for the styles that are not on the Renthal table
([Lowbrow][lowbrow]): mini apes rise 8–10 in (203–254), apes rise 12–16 in
(305–406), narrow apes 28–30 in wide (711–762), standard apes 33–38 in wide
(838–965). Drag bars are zero rise with a little pullback; trackers are a
slight rise and pullback.

## What the bends have to respect

A bar is a bent tube, and the bend radius is the constraint that decides
whether it can be made at all ([Xometry][xometry], [Listertube][lister]):

* **CLR ≥ 2 × OD** — the comfortable minimum. 44 mm on a 22 mm tube.
* **≈ 3 × OD** — what a thin wall wants. 66 mm on a 22 mm tube.
* **Below ~1.5 × OD** — needs a mandrel and a wiper die, and costs tooling.

Which puts the reference ED's own bends in perspective: **R31 on Ø22 is
1.4 × OD**, a mandrel bend and no more; **R14 is 0.64 × OD**, which is below
what a 2 mm wall will take without collapsing. Either those plan-view radii
are drawn to the tube's surface rather than its centreline, or the drawing
is nominal. Worth asking, and worth measuring: the app can report
CLR ÷ OD for every bend it builds, the same way it reports whether a hole
landed on a stock drill size.

[lowbrow]: https://www.lowbrowcustoms.com/blogs/motorcycle-how-to-guides/motorcycle-handlebars-101
[renthal]: https://www.revzilla.com/motorcycle/renthal-street-handlebars-78
[xometry]: https://www.xometry.com/resources/tube/tube-bending-design-tips/
[lister]: https://www.listertube.com/links/tube-bending-design-guide/
