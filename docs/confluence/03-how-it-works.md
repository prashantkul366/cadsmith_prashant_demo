# How It Works | Architecture

Five agents and two correction loops, with a catalogue in front of them
and a kernel behind them that has the final word.

## The path a request takes

```
  prompt (EN / JP)
        │
        ▼
  ┌───────────────┐   recognised standard part?
  │   catalogue   ├──── yes ──►  built exactly from the published
  │    router     │              standard, ~2 s, zero model tokens
  └───────┬───────┘
          │ no, or ambiguous
          ▼
  ┌───────────────┐
  │    Planner    │  prompt → design spec: components, dimensions,
  └───────┬───────┘  constraints
          ▼
  ┌───────────────┐
  │     Coder     │  spec → parametric CAD source, with retrieval
  └───────┬───────┘  over the CAD API documentation
          ▼
  ┌───────────────┐  runs the code in a sandboxed subprocess,
  │   Executor    │  pulls geometry out of the CAD kernel,
  └───────┬───────┘  exports STEP / STL
          ▼
  ┌───────────────┐  1. solid valid?
  │   Validator   │  2. kernel measurements vs. what the plan claimed
  └───────┬───────┘  3. vision Judge: three rendered views + the numbers
          │
     pass │ fail ──► Refiner ──► back to the Executor
          ▼
   drawing · cost · exports · parameter sliders
```

**The inner loop** catches code that will not run: error → error refiner →
retry, up to three times.

**The outer loop** catches geometry that is wrong: validator feedback →
Refiner → re-execute, up to five iterations.

Every attempt is kept. The filmstrip in the interface shows all of them
with their verdicts, rejections included.

## The four things worth understanding

**1. The kernel has the final word.** Two independent judgements are made
on every part. The CAD kernel measures the solid — bounding box, volume,
face count, validity, hole depths read off the solid rather than off the
circle it projects to. Separately, a vision model looks at three rendered
views alongside those numbers. When they disagree, **the measurement
wins**: a plate the plan said has four holes and the solid says has one is
blocked, however confident the Judge was. This is the difference between
this and a text-to-CAD demo.

**2. The Judge is a stronger model than the Coder.** Claude Sonnet 5 plans
and writes the code; Claude Opus 5 judges it. It is not grading its own
homework.

**3. A standard part never reaches a model.** 18 families — bearings,
bolts, nuts, washers, screws, pins, o-rings, springs, pulleys, gears,
shafts, keys, bushings, rings, collars, couplings, set screws, threaded
rod — are built to the published standards and served exactly. Two
seconds, zero tokens, and no chance of a hallucinated dimension on a part
that has a published one. The router refuses anything ambiguous and hands
it to the agents rather than guessing, which is the only reason it can be
trusted.

**4. What is generated is source, not geometry.** The artefact is a
parametric script. Every dimension the plan named is still a number, so
the sliders are real editing and not a re-generation, and the kernel
rebuilds in about a second with no model call.

## What the vision Judge is shown

Three views at each iteration, alongside the kernel's measurements:

- **left** — isometric, for overall shape
- **centre** — high-angle rear, which reveals top-face features like bolt
  holes and bores
- **right** — front profile, for vertical structure

The Judge cross-references those against the prompt, the code and the
exact measurements. The views exist because numbers alone miss a part that
is structurally wrong while measuring correctly, and measurements exist
because a render alone cannot resolve a 3 mm error.

## Where the drawing and the cost sit

Both are downstream of a passing version and neither calls a model.

- The **drawing** is projected from the STEP solid through the kernel's
  hidden-line algorithm, and is built when the part is rather than when
  somebody opens the tab. See *Drawing Generation*.
- The **cost** is read off the geometry — a hole is a hole whatever the
  plan called it — with the material and the process coming from the
  Planner, because those are the two things geometry cannot tell you. See
  *Manufacturing Cost Estimate*.

## Spend and observability

- A per-run token ceiling, 250,000 by default, checked before every model
  call. The run stops and keeps what it produced.
- Per-agent token spend, on screen.
- A full event log per run, which is also what makes replay possible: a
  recorded run can be played back with real geometry and real verdicts and
  no network.

## Model backends

Claude on Amazon Bedrock is what was demonstrated. The same application
also runs against the Anthropic API directly, any OpenAI-compatible
endpoint, and a local model — a local Qwen3-VL-8B was used for the offline
evaluation. The backend is one setting; nothing above it changes.

## Not modified

The research pipeline is used unmodified. Instrumentation is attached from
outside it — instrumented subclasses swapped in after construction, module
attributes wrapped, and a context variable scoping both to the current
job. With no context set the wrappers are pass-throughs, so the published
benchmark stays reproducible. See *Attribution & Licensing*.
