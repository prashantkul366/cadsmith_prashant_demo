# What the app builds from the prompt library

Every part below was built on real FreeCAD 26.3.0 by calling the app's own
CAD tools, measured off the exported STEP by the app's own kernel, and put
through the same gate a run goes through. The numbers are readings.

**43 of 45 built clean**, in 624 tool calls and 121 seconds of kernel time,
cutting 268 holes between them. 13 of them carry a working slider.

Each part's outputs are saved together: `model.step`, `model.stl`,
`part.FCStd` (the live tree), `drawing.svg`, `geometry.json`,
`specification.json` and a render.

One caveat that matters: this container has no model backend, so the tool
calls were written by hand rather than chosen by a builder model. What is
proven here is that the geometry, the gate and the drawing are sound for
these prompts - not that a model will pick the same calls.


## Test lab fixtures

| id | part | calls | measured mm | holes | slider | gate |
|---|---|---|---|---|---|---|
| TL1 | accelerometer mounting cube | 8/8 | 25 x 25 x 25 | 4 | side | PASS |
| TL3 | shaker head adapter plate | 41/41 | 300 x 300 x 25 | 37 | thickness | PASS |
| TL4 | load-cell clevis | 9/9 | 50 x 50 x 80 | 2 | - | PASS |
| TL5 | load introduction pad, spherical seat | 10/10 | 100 x 100 x 30 | 4 | - | PASS |
| TL6 | handlebar vibration fixture pedestal | 15/16 | 120 x 120 x 205 | 7 | column_height | PASS ⚠ |
| TL7 | outboard transom test block | 22/22 | 600 x 300 x 533 | 4 | - | PASS |

## Motorcycle

| id | part | calls | measured mm | holes | slider | gate |
|---|---|---|---|---|---|---|
| MC1 | rear axle spacer collar | 3/3 | 32 x 32 x 28.5 | - | length | PASS |
| MC2 | footpeg mounting bracket | 8/8 | 120 x 55 x 6 | 3 | thickness | PASS |
| MC3 | oil filler cap | 16/16 | 35.65 x 35.65 x 26 | 12 | - | PASS |
| MC4 | handlebar riser top clamp | 8/8 | 60 x 62 x 20 | 5 | height | PASS |
| MC5 | front brake disc | 43/43 | 267 x 267 x 5 | 41 | - | PASS |
| MC7 | lower triple clamp (simplified) | 14/14 | 282 x 93.5 x 40 | 5 | - | PASS |

## Marine

| id | part | calls | measured mm | holes | slider | gate |
|---|---|---|---|---|---|---|
| MR1 | transom spacer plate | 10/10 | 280 x 200 x 10 | 4 | thickness | PASS |
| MR2 | sacrificial anode block | 4/4 | 110 x 45 x 14 | 2 | - | PASS |
| MR3 | propeller thrust washer | 10/10 | 62 x 62 x 11 | - | - | PASS |
| MR4 | cooling hose barb fitting | 2/2 | 16.16 x 16.16 x 50 | - | - | PASS |
| MR5 | water pump impeller | 15/15 | 54 x 48.02 x 22 | 1 | - | PASS |

## Robotics and factory automation

| id | part | calls | measured mm | holes | slider | gate |
|---|---|---|---|---|---|---|
| RB1 | linear axis mechanical stopper | 7/7 | 40 x 30 x 20 | 3 | height | PASS |
| RB2 | vacuum pad holder bracket | 6/6 | 40 x 30 x 50 | 1 | - | PASS |
| RB3 | single-axis robot motor adapter | 13/13 | 60 x 60 x 10 | 10 | - | PASS |
| RB5 | ball screw fixed-side support block | 9/9 | 60 x 25 x 43 | 4 | height | PASS |
| RB7 | cable carrier link | 7/7 | 29.52 x 60 x 20 | 1 | - | PASS |

## E-bike, mobility, golf car

| id | part | calls | measured mm | holes | slider | gate |
|---|---|---|---|---|---|---|
| EB1 | handlebar display clamp | 14/14 | 15 x 42 x 53 | 4 | - | PASS |
| EB2 | golf car seat hinge bracket | 5/5 | 80 x 40 x 45 | 3 | - | PASS |
| EB3 | battery rail mount extrusion | 6/6 | 300 x 40 x 22 | 3 | length | PASS |
| EB4 | drive unit mounting bracket | 7/7 | 84.58 x 72.17 x 8 | 4 | - | PASS |
| EB6 | wheelchair caster fork | 7/7 | 40 x 30 x 74.44 | 2 | - | PASS |
| EB7 | steering wheel hub adapter | 10/10 | 70 x 70 x 45 | 6 | - | PASS |

## Off-road, power products, UAV

| id | part | calls | measured mm | holes | slider | gate |
|---|---|---|---|---|---|---|
| OR1 | generator anti-vibration mount | 2/2 | 50 x 50 x 31 | - | - | PASS |
| OR4 | roll-cage tube clamp | 6/6 | 90 x 40 x 32 | 3 | height | PASS |
| OR5 | drone arm folding hinge block | 8/8 | 52.64 x 40 x 32 | 3 | - | PASS |
| OR7 | cargo bed tie-down anchor | 7/7 | 60 x 40 x 17.03 | 3 | - | PASS |

## Manufacturing jigs and fixtures

| id | part | calls | measured mm | holes | slider | gate |
|---|---|---|---|---|---|---|
| MF1 | diamond locating pin | 5/5 | 16 x 16 x 26 | - | - | PASS |
| MF2 | toggle clamp riser block | 10/10 | 60 x 40 x 30 | 6 | height | PASS |
| MF3 | welding fixture V-block | 12/12 | 100 x 80 x 50 | 4 | - | PASS |
| MF4 | drill jig plate | 13/13 | 220 x 180 x 12 | 9 | - | PASS |
| MF5 | go/no-go plug gauge | 2/2 | 22 x 22 x 107 | - | - | PASS |
| MF7 | inspection pallet nest | 17/17 | 300 x 250 x 20 | 10 | - | PASS |

## EV parts library

| id | part | calls | measured mm | holes | slider | gate |
|---|---|---|---|---|---|---|
| EV1 | flat copper busbar with offset | 4/4 | 130 x 30 x 13 | 2 | - | PASS |
| EV2 | cylindrical cell holder grid | 46/46 | 123.3 x 100.8 x 10 | 44 | - | PASS |
| EV5 | insulated HV standoff | 8/9 | 24 x 27.71 x 40 | 2 | - | PASS ⚠ |
| EV7 | arc-segment rotor magnet | 3/3 | 7.37 x 15.82 x 40 | - | - | PASS |
| EV9 | battery module end plate | 11/11 | 150 x 100 x 10 | 6 | thickness | PASS |
| EV10 | HV cable grommet | 2/2 | 32 x 32 x 10.6 | - | - | PASS |
| EV11 | pin-fin heat sink | 137/137 | 120 x 80 x 31 | 4 | - | PASS |

## The two that did not finish clean

Both still build a correct part and pass the gate; both refused the last
call, and said why.

- **TL6** pedestal - a 0.5 chamfer on *every* edge includes the 2 mm saw
  slot, where it does not fit. The prompt asks for it on the outer edges;
  the tool takes all, top or bottom, and has no notion of "outer".
- **EV5** standoff - same, a 1 mm chamfer round three 2 mm creepage
  grooves.

## Known gaps, and the prompts that hit them

| missing | prompts |
|---|---|
| tangent arcs between non-adjacent sides | TL2 |
| engraved text | TL1, MR2, MF4 (the rest of each part builds) |
| modelled thread helix | MC3, MR4, MF6 - `drill(thread=...)` cuts the tapping drill and carries the callout, which is what a drawing asks for |
| loft between sections | EV4 |
| helical / pitch-driven surfaces | MR7 |
| involute tooth forms | MC6, EB5 - the catalogue has `spur_gear` and `timing_pulley`, so RB6 is covered |
| sketch on a face that is not XY, XZ or YZ | OR3 (30 deg bend), MC7's hull web (built as a straight-sided approximation) |
| sheet-metal bend relief and unfolding | OR3 |
| spherical dome with a shelled wall | OR6 |
| enclosed internal channel | EV12 |

## Two behaviours worth knowing before a demo

**A slider stops at a change that would break the part.** The tree is live
now, so dragging a declared parameter recomputes the whole chain. Where a
value cannot rebuild - growing a block past a blind hole turns the hole
into a sealed void no chamfer can follow - the change is rolled back and
refused with its reason. The panel and the part never disagree.

**Breaking the edges costs the hole callouts on the drawing.** After a
chamfer or fillet on every edge, the projector sees the break rings rather
than the holes, so a leader reads `17x R1` instead of `4x M6`. The hole
schedule in the notes and in the Properties card is still right, because
it comes from what was drilled rather than from what the projection
recognises.
