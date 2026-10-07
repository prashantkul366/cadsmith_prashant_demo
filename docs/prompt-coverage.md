# What the app builds from the prompt library

All 61 prompts, built on real FreeCAD 26.3.0 by calling the app's own CAD
tools, measured off the exported STEP by the app's own kernel, and put
through the same gate a run goes through. The numbers are readings.

**61 of 61 built clean** - every prompt in the library - in 931 tool calls
and 390 seconds of kernel time, cutting 401 holes between them. 14 carry a
working slider.

Each part's outputs are saved together: `model.step`, `model.stl`,
`part.FCStd` (the live feature tree), `drawing.svg`, `geometry.json`,
`specification.json` and a render.

One caveat that matters: this container has no model backend, so the tool
calls were written by hand rather than chosen by a builder model. What is
proven is that the geometry, the gate and the drawing are sound for these
prompts - not that a model will choose the same calls.


## Test lab fixtures

| id | part | calls | measured mm | holes | slider | gate |
|---|---|---|---|---|---|---|
| TL1 | accelerometer mounting cube | 8/8 | 25 x 25 x 25 | 4 | side | PASS |
| TL2 | tensile test specimen, flat | 6/6 | 200 x 20 x 3 | - | thickness | PASS |
| TL3 | shaker head adapter plate | 41/41 | 300 x 300 x 25 | 37 | thickness | PASS |
| TL4 | load-cell clevis | 9/9 | 50 x 50 x 80 | 2 | - | PASS |
| TL5 | load introduction pad, spherical seat | 10/10 | 100 x 100 x 30 | 4 | - | PASS |
| TL6 | handlebar vibration fixture pedestal | 16/16 | 120 x 120 x 205 | 7 | column_height | PASS |
| TL7 | outboard transom test block | 22/22 | 600 x 300 x 533 | 4 | - | PASS |

## Motorcycle

| id | part | calls | measured mm | holes | slider | gate |
|---|---|---|---|---|---|---|
| MC1 | rear axle spacer collar | 3/3 | 32 x 32 x 28.5 | - | length | PASS |
| MC2 | footpeg mounting bracket | 8/8 | 120 x 55 x 6 | 3 | thickness | PASS |
| MC3 | oil filler cap | 16/16 | 35.65 x 35.65 x 26 | 12 | - | PASS |
| MC4 | handlebar riser top clamp | 8/8 | 60 x 62 x 20 | 5 | height | PASS |
| MC5 | front brake disc | 43/43 | 267 x 267 x 5 | 41 | - | PASS |
| MC6 | rear sprocket, 45T #520 | 60/60 | 237.09 x 237.1 x 7 | 51 | - | PASS |
| MC7 | lower triple clamp (simplified) | 14/14 | 282 x 93.5 x 40 | 5 | - | PASS |

## Marine

| id | part | calls | measured mm | holes | slider | gate |
|---|---|---|---|---|---|---|
| MR1 | transom spacer plate | 10/10 | 280 x 200 x 10 | 4 | thickness | PASS |
| MR2 | sacrificial anode block | 4/4 | 110 x 45 x 14 | 2 | - | PASS |
| MR3 | propeller thrust washer | 10/10 | 62 x 62 x 11 | - | - | PASS |
| MR4 | cooling hose barb fitting | 2/2 | 16.16 x 16.16 x 50 | - | - | PASS |
| MR5 | water pump impeller | 15/15 | 54 x 48.02 x 22 | 1 | - | PASS |
| MR6 | WaveRunner intake grate | 21/21 | 200 x 320 x 26 | 4 | - | PASS |
| MR7 | 3-blade propeller (simplified) | 5/5 | 205.8 x 102.59 x 151.42 | - | - | PASS |

## Robotics and factory automation

| id | part | calls | measured mm | holes | slider | gate |
|---|---|---|---|---|---|---|
| RB1 | linear axis mechanical stopper | 7/7 | 40 x 30 x 20 | 3 | height | PASS |
| RB2 | vacuum pad holder bracket | 6/6 | 40 x 30 x 50 | 1 | - | PASS |
| RB3 | single-axis robot motor adapter | 13/13 | 60 x 60 x 10 | 10 | - | PASS |
| RB4 | SCARA tool flange | 13/13 | 63 x 63 x 20 | 9 | - | PASS |
| RB5 | ball screw fixed-side support block | 9/9 | 60 x 25 x 43 | 4 | height | PASS |
| RB6 | HTD 5M timing pulley, 24T | 2/2 | 36.96 x 36.96 x 7 | - | - | PASS |
| RB7 | cable carrier link | 7/7 | 29.52 x 60 x 20 | 1 | - | PASS |

## E-bike, mobility, golf car

| id | part | calls | measured mm | holes | slider | gate |
|---|---|---|---|---|---|---|
| EB1 | handlebar display clamp | 14/14 | 15 x 42 x 53 | 4 | - | PASS |
| EB2 | golf car seat hinge bracket | 5/5 | 80 x 40 x 45 | 3 | - | PASS |
| EB3 | battery rail mount extrusion | 6/6 | 300 x 40 x 22 | 3 | length | PASS |
| EB4 | drive unit mounting bracket | 7/7 | 84.58 x 72.17 x 8 | 4 | - | PASS |
| EB5 | chainring, 38T BCD 104 | 44/44 | 161.4 x 161.41 x 3 | 42 | - | PASS |
| EB6 | wheelchair caster fork | 7/7 | 40 x 30 x 74.44 | 2 | - | PASS |
| EB7 | steering wheel hub adapter | 10/10 | 70 x 70 x 45 | 6 | - | PASS |

## Off-road, power products, UAV

| id | part | calls | measured mm | holes | slider | gate |
|---|---|---|---|---|---|---|
| OR1 | generator anti-vibration mount | 2/2 | 50 x 50 x 31 | - | - | PASS |
| OR2 | spray nozzle mount (drone boom) | 10/10 | 20 x 26 x 37 | 2 | - | PASS |
| OR3 | ATV skid plate | 16/16 | 603.9 x 370 x 63.7 | 6 | - | PASS |
| OR4 | roll-cage tube clamp | 6/6 | 90 x 40 x 32 | 3 | height | PASS |
| OR5 | drone arm folding hinge block | 8/8 | 52.64 x 40 x 32 | 3 | - | PASS |
| OR6 | wheel center cap | 13/13 | 60 x 60 x 22 | - | - | PASS |
| OR7 | cargo bed tie-down anchor | 7/7 | 60 x 40 x 17.03 | 3 | - | PASS |

## Manufacturing jigs and fixtures

| id | part | calls | measured mm | holes | slider | gate |
|---|---|---|---|---|---|---|
| MF1 | diamond locating pin | 5/5 | 16 x 16 x 26 | - | - | PASS |
| MF2 | toggle clamp riser block | 10/10 | 60 x 40 x 30 | 6 | height | PASS |
| MF3 | welding fixture V-block | 12/12 | 100 x 80 x 50 | 4 | - | PASS |
| MF4 | drill jig plate | 13/13 | 220 x 180 x 12 | 9 | - | PASS |
| MF5 | go/no-go plug gauge | 2/2 | 22 x 22 x 107 | - | - | PASS |
| MF6 | hex flange bolt, M8x1.25 x 30 | 2/2 | 15.01 x 13 x 35.3 | - | - | PASS |
| MF7 | inspection pallet nest | 17/17 | 300 x 250 x 20 | 10 | - | PASS |

## EV parts library

| id | part | calls | measured mm | holes | slider | gate |
|---|---|---|---|---|---|---|
| EV1 | flat copper busbar with offset | 4/4 | 130 x 30 x 13 | 2 | - | PASS |
| EV2 | cylindrical cell holder grid | 46/46 | 123.3 x 100.8 x 10 | 44 | - | PASS |
| EV3 | cell interconnect strip | 14/14 | 102 x 12 x 0.15 | - | - | PASS |
| EV4 | HV ring-terminal cable lug | 9/9 | 54 x 18 x 12.5 | 3 | - | PASS |
| EV5 | insulated HV standoff | 9/9 | 24 x 27.71 x 40 | 2 | - | PASS |
| EV6 | thermistor clip for a cylindrical cell | 10/10 | 8 x 14.7 x 26.7 | - | - | PASS |
| EV7 | arc-segment rotor magnet | 3/3 | 7.37 x 15.82 x 40 | - | - | PASS |
| EV8 | stator lamination | 43/43 | 159.97 x 159.97 x 0.35 | 4 | - | PASS |
| EV9 | battery module end plate | 11/11 | 150 x 100 x 10 | 6 | thickness | PASS |
| EV10 | HV cable grommet | 2/2 | 32 x 32 x 10.6 | - | - | PASS |
| EV11 | pin-fin heat sink | 137/137 | 120 x 80 x 31 | 4 | - | PASS |
| EV12 | liquid cold plate | 39/39 | 300 x 200 x 22 | 12 | - | PASS |

## What had to be added to get the last sixteen

- **An arc as a side of a profile.** A corner radius can only round where
  two sides meet. `[x, y, r, "next"]` makes the side to the next corner an
  arc instead, which is how a tensile specimen's tangent transition, a
  stator slot bottom and a cooling channel's U-turn are drawn. TL2's four
  R12.5 arcs come out centred on (±28.5, ±18.75), which is what the prompt
  specifies.
- **A loft.** There is no prismatic answer to a round section becoming a
  rectangular one, so EV4's barrel-to-palm transition and MR7's blade
  needed `Part::Loft` between sketched sections.
- **An edge break that keeps what it can.** "Chamfer all outer edges" is
  what a drawing says; the kernel refuses the whole set if one pocket is
  too narrow for it, and the part came back with no broken edges at all.
  A person selects them all and deselects what will not take, so that is
  what happens now - any edge that refuses is left sharp.
- **Sprocket and chainring teeth** by their ISO 606 seating radius
  (0.5025 d + 0.05) cut at each pitch position, which is the simplified
  form a drawing of a sprocket carries.

## Known limits, stated rather than discovered

- **Engraved text** (TL1, MR2, MF4) is absent. The rest of each part
  builds; only the lettering is missing.
- **A modelled thread helix** is not cut. `drill(thread="M8")` cuts the
  tapping drill and carries the M8 callout, which is what a drawing asks
  for; MC3, MR4 and MF6 are built and called out that way.
- **MR7's propeller** is a loft between four planar sections at increasing
  radius, each rotated to its local pitch angle. It is a recognisable
  blade of the right pitch and chord, not a true constant-pitch helicoid -
  which is the stretch case the library says it is.
- **A sketch on a face that is not XY, XZ or YZ.** OR3's 30 degree flange
  is drawn as a side-view profile instead, which gives the right solid;
  a feature placed on that flange would not be possible.

## Two behaviours worth knowing before a demo

**A slider stops at a change that would break the part.** The tree is live,
so dragging a declared parameter recomputes the whole chain. Where a value
cannot rebuild - growing a block past a blind hole turns the hole into a
sealed void no edge break can follow - the change is rolled back and
refused with its reason. The panel and the part never disagree.

**Breaking the edges costs the hole callouts on the drawing.** After a
chamfer or fillet on every edge, the projector sees the break rings rather
than the holes, so a leader reads `17x R1` instead of `4x M6`. The hole
schedule in the notes and in the Properties card is still right, because
it comes from what was drilled rather than from what the projection
recognises.
