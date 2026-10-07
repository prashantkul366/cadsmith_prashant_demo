# What the app can build from a fully dimensioned prompt

> This branch generates a CadQuery script rather than calling CAD tools
> against FreeCAD, so the table below describes the other branch
> (`claude/freecad-mcp`). Kept here because the gate it shares with that
> branch - what a request is read to require - is the same code, and
> because the gaps are a property of the request, not of the road.


Written against the Yamaha demo prompt library (61 single-part prompts).
Those prompts are the good case for this app: they open with ORIGIN and
AXES and then place every feature at stated coordinates, which is the
shape the tool vocabulary already speaks.

Three levels of confidence here, and they are not the same thing:

- **Built** - actually built on real FreeCAD 26.3.0 and measured. The
  size, the hole count and the gate verdict below are readings, not
  expectations.
- **Expected** - every operation it needs exists and is tested, but this
  particular prompt has not been run.
- **Gap** - it needs something the vocabulary does not have. Named below
  with what is missing, so nobody finds out in front of an audience.

## Built and measured

| prompt | calls | measured | holes | gate |
|---|---|---|---|---|
| TL1 accelerometer mounting cube | 7 | 25 x 25 x 25 | 4 | PASS |
| TL3-class: MF2 toggle clamp riser | 9 | 60 x 40 x 30 | 8 | PASS |
| MR1 transom spacer plate | 9 | 280 x 200 x 10 | 4 | PASS |
| MC1 rear axle spacer collar | 2 | 32 x 32 x 28.5 | - | PASS |
| MC4 handlebar riser top clamp | 7 | 60 x 62 x 20 | 5 | PASS |
| RB1 linear axis stopper | 6 | 40 x 30 x 20 | 3 | PASS |
| OR1 generator anti-vibration mount | 2 | 50 x 50 x 31 | - | PASS |
| EV5 insulated HV standoff | 5 | 24 across flats x 40 | 2 | PASS |

Between them these exercise tapped holes into four different faces,
counterbores, through bores, corner radii, a cut-out window, two
revolves, a hex prism and a chamfer on every edge.

## Known gaps, and which prompts hit them

| missing | prompts | note |
|---|---|---|
| engraved text | TL1, MR2, MF4 | the rest of each part builds; only the lettering is absent |
| modelled thread helix | MC3, MR4, MF6 | `drill(thread="M8")` cuts the tapping drill and carries the callout, which is what a drawing asks for. A cut helix is a different thing and is not offered |
| loft between sections | EV4, MR7 | no loft in the vocabulary |
| helical / pitch-driven surfaces | MR7 | the deliberate stretch case in the library |
| involute tooth forms | MC6, EB5 | the catalogue has `spur_gear` and `timing_pulley` (so RB6 is fine); a #520 sprocket and a chainring are not in it |
| a sketch on a non-principal face | OR3 (30 deg bend), MC7 (hull web) | profiles are drawn on XY, XZ or YZ |

## Two behaviours worth knowing before a demo

**A part with a hole has no sliders.** `drill` replaces the parametric
body with a plain solid, so the feature tree - and with it the slider
panel - goes. That is reported honestly (the panel shows nothing) rather
than offering a control that does not move the part, which is what it
used to do.

**Breaking the edges costs the hole callouts on the drawing.** After a
chamfer or a fillet on every edge, the projector sees the break rings
rather than the holes, so the leaders read `17x R1` instead of `4x M6`.
The hole schedule in the notes and in the Properties card is still
right, because it comes from what was drilled rather than from what the
projection recognises.
