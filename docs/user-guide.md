# CADSmith — User Guide

Describe a part in plain English or Japanese. Five AI agents plan it, write
CAD code, build it in a real CAD kernel, and measure what came out. You get
a 3D model, its editable source, an engineering drawing, a cost estimate and
files your own CAD system can open.

Every screen name in this guide is written exactly as it appears in the
interface, so you can follow along on screen.

---

## 1. Before you start

You need the application running on your own machine. It is not a website.

```powershell
.\app\run_app.ps1
```

Then open **http://127.0.0.1:8000** in your browser. Nothing is published:
the app listens on your own computer only.

At the top of the page a banner reports the system state. **ALL SYSTEMS
READY** means everything works. **DEGRADED** means one part is unavailable
and the rest still runs. **NOT READY** means the model backend has not been
configured yet — open **Model and run settings** and pick one.

If you want to check everything before a demo, run the preflight first:

```powershell
.venv\Scripts\python -m app.tools.doctor --provider bedrock
```

It tests the CAD kernel, the renderer, your credentials and the model, and
names whatever is wrong.

---

## 2. The screen

The window has three columns.

**Left — the conversation.** One box to type in, under **Design Input**.
Below it the **Design Plan** appears as the part is planned, then
**Reasoning** shows the agents thinking as they work. **Model and run
settings** is where you choose the model and how hard it should think.

**Centre — the part.** The 3D model, which you orbit by dragging. Four
buttons switch what you are looking at: **3D model**, **Code**,
**Parameters** and **Drawing**.

**Right — what came out.** Four panels that fold away when you do not need
them: **Properties**, **MEASURED BY THE KERNEL**, **Validation** and
**Token tracking**.

Across the top: **History**, **Undo**, **Redo**, **Fullscreen**, and the
language switch — **EN** and **日本語**.

---

## 3. Your first part

1. Type a description into **Describe part**. For example:

   > A flat plate 100mm by 60mm by 8mm thick with four 6mm holes, one 10mm
   > in from each corner.

2. Press **Generate CAD**.

3. Watch the stages go by on the left: **Planning the part** → **Writing
   CadQuery** → **Building the solid** → **Validating geometry** →
   **Ready**.

4. The part appears in the centre. Drag to turn it.

A standard part — a bearing, a bolt, a washer — is answered in about two
seconds from the built-in catalogue, with no AI call at all. Anything else
takes the agents a minute or two.

If you would rather not type, **Benchmark prompts** offers a list to click.

---

## 4. Reading the result

**Design Plan** is what the system understood you to ask for: **TARGET
DIMENSIONS** and **CONSTRAINTS**. Read this first. If the plan is wrong, the
part will be wrong, and you have saved yourself waiting for it.

**MEASURED BY THE KERNEL** is what the CAD kernel actually measured on the
finished solid — **overall size**, **hole count**, **hole diameter**,
**watertight solid**. These are measurements, not estimates. Where a figure
is marked **(advisory)** it is informative rather than something the system
will reject a part over.

**Validation** compares the two. **Accepted by the Judge** means the part
passed. **Refused on measurement** means the kernel found a real difference
from the plan, and the panel names it: *hole count measured 1, wanted 4*.

That is the point of the system. A measurement settles a dimension; an
opinion does not. A part that looks right but is 3 mm out cannot be
manufactured, and this is what catches it.

**Token tracking** shows what the run cost in tokens, per agent.

---

## 5. Changing dimensions

Switch the centre view to **Parameters**.

Every dimension the generated part is built from appears as a control. Drag
one and release: the kernel rebuilds the part in about a second, with **no
AI call and no cost**. **Reset** puts a value back.

This works because what was generated is a parametric script, not a fixed
mesh. Every number stays a number you can change.

Use **Undo** and **Redo** at the top to move between versions.

---

## 6. The drawing

Switch the centre view to **Drawing**.

You get an A3 **ENGINEERING DRAWING**: four projected views, first-angle
projection, centre lines, dimensions and a title block. It is produced by
projecting the solid itself, not by drawing a picture of it.

**Download DXF** gives you the drawing as DXF, which any CAD system opens
and can re-measure. **Export PNG** gives a picture for a document or a
slide. **Back to 3D** returns to the model.

The sheet carries no tolerances and no material. Nothing in the system has
specified either, and a tolerance note on an untoleranced drawing would be
a claim rather than a fact.

---

## 7. Manufacturing cost

The **Manufacturing cost** panel estimates what the part costs to make:

| | |
|---|---|
| **Material** | the billet, bar or sheet it is cut from, priced by weight |
| **Machining** | the operations the geometry requires, priced by the minute |
| **Setup** | per machine the part visits, divided across the batch |
| **Per part** | the total |

The operations are read off the geometry — a hole is a hole whatever the
plan called it. The **material** and the **process** come from the plan,
because those are the only two things the geometry cannot tell you: the same
plate is laser-cut sheet or a milled billet depending on nothing in the
model.

**Name the material in your prompt** and the estimate becomes far more
useful. Compare the same part in aluminium and in stainless steel to see
what the model is doing.

**This is an estimate for comparing one design against another, not a
quotation.** The rates live in an editable file and should be checked
against your own shop's numbers before any figure is used seriously.

Casting, moulding, 3D printing and extrusion are deliberately not priced:
those are paid for in tooling or machine hours, not time at a spindle, and a
wrong answer given precisely is worse than no answer.

---

## 8. Getting the part out

**Export** offers five files:

| | |
|---|---|
| **STEP** | solid, for CAD |
| **STL** | mesh, for printing |
| **DXF** | the drawing, re-measurable |
| **PNG** | the drawing, as a picture |
| **.py** | the CadQuery script |

The script is worth taking. It is the part as source, and it can be edited,
version-controlled and re-run without this application.

---

## 9. History

**History** lists every run, with its result — **CONVERGED**, **NOT
CONVERGED** or **FAILED** — and how many versions it produced.

**REPLAY** plays a recorded run back with its real geometry and real
verdicts. It needs no network and no model, which makes it the reliable way
to show a result when the connection is not.

---

## 10. Settings

Open **Model and run settings** on the left.

**Provider** chooses the backend: Claude on Amazon Bedrock, the Anthropic
API, OpenAI, Ollama, LM Studio, or any OpenAI-compatible endpoint. With a
local model the panel reads **Running locally — nothing leaves this
machine**, which is the setting to use for confidential work.

**Model id** sets the model for each role — one to generate, one to judge.
The judge is deliberately a stronger model, so the system is not grading its
own homework.

> **If a model id is refused**, the id is almost certainly the problem
> rather than your credentials. The list a cloud provider publishes and the
> models its endpoint actually serves are not always the same set. Try
> another id from the list the preflight prints.

**Refinement iterations** is how many times the system may correct itself
before giving up.

**Reasoning effort** runs from **Low — fastest** to **Maximum**. **High**
is the default and is right for most parts.

---

## 11. Standard parts

Bearings, bolts, nuts, washers, screws, pins, o-rings, springs, pulleys,
gears, shafts, keys, bushings, rings, collars, couplings, set screws and
threaded rod are built directly to the published standard — about two
seconds, no AI call, no cost, and no chance of an invented dimension on a
part that has a published one.

Just ask for it by its designation: *a 6203 ball bearing*, *an M12 hex nut*,
*a GT2 timing pulley with 20 teeth and a 5mm bore*.

Anything ambiguous is passed to the agents rather than guessed at.

---

## 12. Writing a good prompt

- **Give the numbers you care about.** *100mm by 60mm by 8mm thick* beats
  *a medium plate*. Dimensions you state are held fixed.
- **Say where features are**, not only how many: *four 6mm holes, one 10mm
  in from each corner*.
- **Name the material** if you want the cost estimate to mean anything.
- **Use the words a drawing office uses** — pitch circle, counterbore,
  through bore, across flats.
- **One part at a time.** Assemblies are not supported.

Good example:

> A 6061 aluminium bracket plate 120mm by 80mm by 10mm with four M8
> clearance holes 15mm in from each corner and a 40mm central bore.

---

## 13. When something goes wrong

| What you see | What it means |
|---|---|
| **NOT READY** in the banner | No model backend configured. Open **Model and run settings**. |
| A model id refused | The id, not your credentials. Try another from the preflight's list. |
| **Refused on measurement** | Working as intended — the part did not match the plan. Read the panel, adjust the prompt, try again. |
| **NOT CONVERGED** | It ran out of iterations. Raise **Refinement iterations**, or simplify the request. |
| **Could not build the drawing** | The projection failed on this solid. The 3D model and the exports are unaffected. |
| The first part is very slow | Cold start. The kernel loads on first use; later parts are much faster. |
| Credentials rejected part-way through | A temporary cloud session expired. Sign in again and re-run. |

---

## 14. What it does not do

Worth knowing before you rely on it:

- **One part at a time.** No assemblies, no mates, no BOM.
- **No tolerances or GD&T** on the drawing.
- **The cost is an estimate**, for comparison only.
- **It does not replace an engineer.** It produces a candidate quickly. The
  measurements tell you whether it matches what was asked for; whether what
  was asked for is the right part is still your judgement.

---

## Credit

The multi-agent pipeline and its benchmark are the work of Jesse Barkley,
Rumi Loghmani and Amir Barati Farimani at Carnegie Mellon University
(arXiv:2603.26512), with local modifications. The application around it —
the interface, the standard-parts catalogue, the measured checks, the
drawings, the cost estimate and the bilingual interface — is this project's
work.
