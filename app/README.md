# CADSmith — web application

A working front end for the CADSmith pipeline. Describe a part in English, watch
five agents plan it, write CadQuery, build it in the OpenCASCADE kernel and
judge the result, then inspect the solid, its source, its drawing and every
attempt along the way.

Everything on screen comes from the pipeline. The mesh in the viewer is the STL
the kernel exported, the dimensions are the kernel's own measurements, the code
is what the Coder agent wrote, and the verdict is the Judge's. Nothing is
simulated and no progress bar runs on a timer.

## Nothing in the research code changed

`autofab/`, `scripts/`, `data/`, `run.py` and `requirements.txt` are untouched.
The published pipeline and its benchmark numbers stay reproducible; this app is
a layer around them.

Observability without edits works in three ways: `Pipeline` builds its executor
and validator as instance attributes, so instrumented subclasses are swapped in
after construction; the agents are reached through the module object, so
wrapping its function attributes intercepts every LLM call; and a `ContextVar`
scopes both to the current job. With no context set, the wrappers are
pass-throughs — importing the app changes nothing for `run.py` or the benchmark
scripts.

## Setup

macOS and Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r app/requirements-app.txt
```

Windows PowerShell — note `python`, not `python3`, and `Scripts\` rather than
`bin/`:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r app\requirements-app.txt
```

CadQuery 2.8 and VTK install as ordinary pip wheels, so the conda environment
the main README describes is no longer required. Tested on Python 3.11.

**On Windows, keep the checkout out of OneDrive.** `.venv` runs to several
hundred megabytes, and syncing it is slow and can lock files mid-install.
Something like `C:\dev\cadsmith_prashant_demo` avoids it.

On **headless Linux**, VTK imports fine and then fails at render time with no GL
backend, which silently costs you the vision Judge. Install a software
rasteriser:

```bash
sudo apt-get install libosmesa6
```

macOS and Windows need nothing extra. The app tells you either way — see
Diagnostics below.

Set a key for whichever provider you want (see **Model backends** below):

```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
# or
echo "OPENAI_API_KEY=sk-..." > .env
# or run a local model and set nothing at all
```

## Running

macOS and Linux:

```bash
./app/run_app.sh              # http://127.0.0.1:8000
PORT=9000 ./app/run_app.sh    # somewhere else
./app/run_app.sh --reload     # reload on source changes
```

Windows PowerShell:

```powershell
.\app\run_app.ps1
.\app\run_app.ps1 -Port 9000
.\app\run_app.ps1 -Reload
```

Both read `.env`, so the health check reports the truth before the first run
starts.

## Behind a corporate proxy

If model calls fail with:

```
[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate
```

your network is inspecting TLS and re-signing it with a company certificate
authority. The OS trusts that CA — which is why your browser works — but
Python ships its own `certifi` bundle that has never seen it.

`truststore` is in `requirements-app.txt` and the app injects it at startup,
so Python uses the OS certificate store instead. If you installed before that
was added:

```powershell
.venv\Scripts\python -m pip install truststore
```

Alternatively, point at an explicit bundle containing your company CA — the
app honours `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE` and prefers either over
everything else. `CADSMITH_TRUST_STORE=certifi` opts back out.

**Do not disable certificate verification.** On exactly the networks that
need this fix, accepting any certificate is the wrong response. Nothing here
turns verification off.

The preflight reports which trust source is in use, and the health chip shows
it too.

## Model backends

`autofab/agents.py` reaches the network through one function, and every agent
goes through it, so the whole pipeline can be pointed elsewhere without
touching the research code. Pick a provider in the app's left panel.

| Provider | Needs | Notes |
|---|---|---|
| **Anthropic** | `ANTHROPIC_API_KEY` | Default. Uses the real SDK, so this path behaves exactly as the published pipeline does. |
| **Bedrock** | AWS credentials + `AWS_REGION` | Same Claude models, billed through AWS. Needs `pip install "anthropic[bedrock]"`; see below. |
| **OpenAI** | `OPENAI_API_KEY` | |
| **Ollama** | Ollama running | Local Llama, Qwen, Mistral… `OLLAMA_BASE_URL` to move it off `localhost:11434`. |
| **LM Studio** | its local server | `LMSTUDIO_BASE_URL` to relocate. |
| **Custom** | `CADSMITH_LLM_BASE_URL` | Anything OpenAI-compatible: vLLM, llama.cpp, Together, Groq, OpenRouter. `CADSMITH_LLM_API_KEY` if it wants one. |

Everything except Anthropic and Bedrock goes through one OpenAI-compatible
adapter, so a new endpoint usually needs only a base URL.

### Claude on Amazon Bedrock

Bedrock takes no API key — it uses the ambient AWS credential chain — but it
does take two things that are easy to miss:

```bash
pip install "anthropic[bedrock]"      # the SDK reaches Bedrock through boto3
export AWS_REGION=us-east-1           # or wherever your models are enabled
```

`pip install anthropic` alone does **not** bring boto3, and the app used to
hide that: the health banner said Bedrock was ready, and the first Generate
answered `503` blaming the AWS credentials. Both halves are fixed — the
readiness shown in the picker is now the same question the job gate asks, and
a refusal names what is actually wrong, whether that is the missing
dependency, an expired session token, or a key and secret that do not belong
together.

**The model ids look wrong and are not.** The app talks to Bedrock's Messages
endpoint through `AnthropicBedrockMantle`, and its ids carry a bare
`anthropic.` prefix — `anthropic.claude-sonnet-5`, `anthropic.claude-opus-5`.
What `aws bedrock list-foundation-models` and the console show you instead are
`us.anthropic.…` and `global.anthropic.…`: those are inference profiles for
the older `InvokeModel` path, and they are a different catalogue. The two do
not overlap, so a model id that serves perfectly well will not appear in the
listing — this account offers 27 ids that way, refuses them at runtime, and
serves the two defaults, which are in no listing at all.

`bedrock_check` therefore reports which ids the app will ask for without
grading them against that list; only the probe settles whether they serve:

```powershell
.venv\Scripts\python -m app.tools.bedrock_check          # a few cents
```

Credentials come from wherever boto3 finds them:

```powershell
# short-lived portal credentials (Windows PowerShell)
$Env:AWS_ACCESS_KEY_ID     = "..."
$Env:AWS_SECRET_ACCESS_KEY = "..."
$Env:AWS_SESSION_TOKEN     = "..."
$Env:AWS_REGION            = "us-east-1"
```

```bash
# or a named profile / SSO session, which does not expire mid-run
aws sso login --profile my-profile
export AWS_PROFILE=my-profile
```

**Pick one of the two.** `AWS_PROFILE` is passed to the SDK explicitly, and
botocore then drops the environment credentials entirely — so with both set,
the profile wins and the keys you pasted are never used. If the profile does
not exist, nothing resolves at all, whatever else is set. A stale
`AWS_PROFILE=` line left in `.env` is the usual way this happens; the
preflight names it.

Portal credentials are short-lived, so the check is made live rather than
inferred from the presence of the variables: an expired token is reported
before a long run starts rather than half way through one. A variable set in
your shell wins over the same name in `.env`, so a stale token left in the
file cannot quietly replace the one you just pasted.

Check the whole path before starting anything long — it runs the same calls
the pipeline does, one at a time, with short timeouts:

```powershell
.venv\Scripts\python -m app.tools.doctor --provider bedrock
```

**Model ids.** Bedrock's are not the first-party names — they carry a region
prefix and a version suffix, and most recent Claude models can only be
invoked through a cross-region *inference profile*
(`us.anthropic.claude-sonnet-4-5-...`) rather than by the bare foundation id.
The app asks your account for both lists and offers what you can actually
invoke, so take the model box's suggestions rather than typing a name. To
see the list from a terminal:

```powershell
.venv\Scripts\python -m app.tools.bedrock_check --no-call
```

That prints the region, the identity your credentials resolve to, and every
model id this account can invoke — and bills nothing. Drop `--no-call` and it
also sends one eight-token probe to prove the model answers.

For the command-line evaluations, name one explicitly:

```bash
python -m app.tools.eval_parts --provider bedrock \
    --generation-model us.anthropic.claude-sonnet-4-5-20250929-v1:0 \
    --judge-model us.anthropic.claude-opus-4-5-20251101-v1:0 \
    --tier easy --out runs/bedrock-easy.json
```

Reasoning effort works on this path as it does on the first-party API.

**Keys** come from `.env`, or you can paste one into the app for the current
server process. A pasted key is held in memory only — never written to disk,
never logged, never sent back to the browser. Restarting clears it.

**Model lists come from the provider**, not from a hardcoded table, so a local
Ollama offers the models you have actually pulled.

**Generation and judging are configured separately**, and may be different
models or different providers — a local Llama writing CadQuery with GPT-4o
judging is a valid setup. The pipeline judges with a stronger, independent
model on purpose; point both roles at the same model and the app says so,
because that reintroduces the self-confirmation the design avoids.

Two things degrade rather than fail. A model that cannot accept images gets
retried without the render, and the Judge is labelled as having run on kernel
metrics alone. A model that wraps its JSON in prose — common with smaller
local ones — has the object extracted, since the Planner and Judge parse
strictly.

Local providers are probed for reachability, so "ready" means something is
actually listening rather than merely that no key is required.

**Reasoning effort is on the panel, next to the iteration slider.** Current
Claude models think before they answer, and how long they think is the
largest single component of the wait: a cylinder with one hole and a
planetary gearbox are not the same problem, but at the API's default effort
the model reasons about both as though they were. Low, Medium and High are
offered; Low is the one to pick for a part you could have drawn yourself, and
High — what the API applies when nothing asks — for one you could not. The
picker appears only for the Claude backends, because `output_config.effort`
is a Claude parameter; adaptive thinking and effort are generally available
on Amazon Bedrock as well as the first-party API, so both paths take it. The
level travels with the run, so the Planner, Coder and Judge all reason at the
level that was chosen, and a run already in flight keeps the level it started
with.

`CADSMITH_EFFORT` still works and now sets what the picker opens on, which is
how to reach `xhigh` and `max`: those are on the API's ladder but not in the
dropdown, since they buy depth at a cost in minutes that no one clicking
through a menu expects.

Two refusals are absorbed rather than failed. A model that reasons but has
yet to take an effort with it is retried without the effort and keeps its
streamed reasoning; an older one that rejects the thinking parameter outright
is retried without either. Both say so in the run log.

**A part is a shape plus what it is made of and how closely.** The Planner's
plan now carries a `specification` block - material, process, general
tolerance class, finish, and the fits where two parts meet - and the sheet
states it. Fits for anything the request names as a standard part come out
of `catalog/standards.py` rather than out of the model: a 6203 sits in an H7
housing bore and on a k6 shaft seat because ISO 286 says so, and an M8
clearance hole is 9mm because ISO 273 does. The case of a fit designation is
never folded, because in ISO 286 the case *is* the meaning - H7 is a hole and
h7 a shaft.

Everything the Planner proposed rather than looked up is marked on the sheet
as proposed, and the sheet says so in as many words: MATERIAL, PROCESS AND
TOLERANCE CLASS ARE PROPOSED BY THE PLANNER - CONFIRM BEFORE MANUFACTURE. A
tolerance class the Planner invented - "ISO 2768-x" - becomes no class at
all and the drawing goes back to saying nothing, which is where it started
and no worse. The old refusal to print a tolerance note nobody had specified
still holds; there is simply now something true to print.

**Two questions are asked of every part about making it**, separately from
whether it matches the request: are its holes at sizes a shop stocks a drill
for, and is anything too thin to make. Both advisory - a bore may be bored on
purpose - and both measured rather than judged.

## Assemblies

A script may assign a `cq.Assembly` to `result` instead of a `cq.Workplane`,
and the pipeline carries it through: the STEP keeps the components separate
with their names and colours, a GLTF is written alongside it, and the
measured checks gain the one an assembly needs - **do any two components
share volume**. Parts touching is not a clash; parts occupying the same space
is, and it blocks, because an assembly that does not go together is not the
assembly.

Placement is explicit and arithmetic. Constraints and `solve()` are
deliberately not used: a solver that fails to converge, or converges
mirrored, fails silently and is nearly impossible to explain to a reader,
while a position computed from the parameters can be checked by measurement
like everything else here.

What is not done yet: the viewer still shows the fused STL rather than the
GLTF component tree, so an assembly appears as one colour and cannot be
exploded or isolated; and the drawing has no parts list or balloons.

## What you can do without any model backend

The agents need one; the CAD kernel does not. Without one you can still:

- **Replay a recorded run** — the events a real run produced, against the
  artifacts it exported. Real geometry, real source, real Judge text; only the
  pacing differs. Marked `REPLAY` in the UI.
- **Edit by parameter patch** — "make it 15mm thick" rewrites the assignment in
  the generated script and rebuilds it in CadQuery, about a second, no model
  call.
- **Open any past run**, compare its iterations, and export STEP/STL/`.py`.
- **Build engineering drawings** from any exported solid.

Seed two demo runs to try this immediately:

```bash
.venv/bin/python -m app.tools.seed_demo_run
```

These have real geometry and real renders, with the agent replies scripted
rather than generated. They are tagged `FIXTURE` in the UI so the distinction
is never hidden. Once you have run the pipeline for real, prefer replaying one
of those.

## Using it

**Generate.** Type a description, or pick a benchmark prompt from
`data/dataset_v2`. Two options matter:

- *Refinement iterations* — how many times the Refiner may correct the geometry
  before the run gives up. Defaults to 3; the pipeline's own default is 5.
- *Vision Judge* — whether the Judge sees the three-view render alongside the
  kernel metrics. Turning it off reproduces the paper's ablation live.

**Watch it work.** The five stages are driven by real events. Execution errors
and refinement rounds appear as they happen, which is the part worth showing:
the loop is the contribution.

**Compare attempts.** Every attempt is a card in the timeline under the viewer.
Click a rejected one to load its geometry, its source and the Judge's reasons
for rejecting it, next to the render the Judge was given.

**Edit.** Type a change in the bar at the bottom. A request naming a parameter
the script declares is patched and rebuilt by the kernel; anything structural
goes to the Refiner agent. The UI says which ran. Ambiguous requests are never
guessed — "make the thickness 12mm" against a script with both
`base_thickness` and `support_thickness` is refused rather than resolved
arbitrarily.

**Adjust it without reading the code.** The code panel flips between **Code**
and **Parameters**, and opens on Parameters: the generated source is the more
striking thing to open on, but it is not what most people came to change, and
it is one click away. Parameters puts a slider and a number field on every
dimension the script declares — read out of the source by the server, so a
control only appears for a number the patcher can actually change. Dragging
one rewrites the line in the Code view as it moves; letting go rebuilds the
part in the kernel, which is one rebuild per gesture rather than one per
frame. Values are refused on the same terms an edit is: an unknown name, a
value that is not a number, and zero or less all come back as a refusal
before anything is queued, and the part on screen is left alone.

It is not a simplified view of the part. It reads the same source the Code
view shows, patches it with the same function a natural-language edit uses,
and rebuilds with the same kernel — a version from a slider is a version like
any other, and its Validation panel says the same thing an edit's does. The
choice of view is remembered, so someone who prefers the source does not have
to ask for it again every visit. Parameter labels stay in English in either
language: they are the script's own identifiers, and the unit beside them is
a symbol in both.

A generated script's header comment names the part and the standard it
follows, and never restates a size. A comment that repeats the number on the
line below it is redundant while the script is untouched and wrong the moment
a control moves — `# M8 x 30.0 socket head cap screw` still said 30.0 after
you dragged the length to 45. The sizes live on the assignments, which are
what the kernel reads and what the drawing dimensions.

What each control is depends only on its name — a count, an angle, or a
length in mm — and that is separate from how the number is written, so a
spring's `active_coils = 8.0` is a count of coils rather than 8 mm of
something, and the patcher still keeps it a float.

**Drawing.** A proper engineering drawing of the built part, on an A3 sheet,
projected from the exported STEP solid through OpenCASCADE's hidden-line
algorithm — so any part the pipeline can build gets a correct drawing rather
than a picture of one. What makes it a drawing rather than four pictures:

* **First angle**, per ISO 128-30:2001 A.2 — "the view from above is placed
  underneath", "the view from the left is placed on the right" — with the two
  pairs sharing their centre lines, and the first angle symbol in the title
  block so nobody has to guess which system it is drawn in.
* **A stated preferred scale** (ISO 5455). A sheet fitted to its frame cannot
  be measured; one drawn at 2:1 can, and `app/tests/test_drawing.py` measures
  the front view on the sheet to confirm it really is the part times the
  ratio the title block claims.
* **Dimensions** (ISO 129-1) with extension lines, arrowheads and values that
  come from the kernel, each overall length given once across the sheet
  rather than repeated on every view that happens to show it. A feature
  dimension is always drawn a step outside whatever overall length the same
  view already carries, so a hole pitch is never written over a width.
* **A hole is a diameter; a round is a radius.** Both are circular edges and
  the projection returns both, so the sweep decides: a whole turn is a hole
  or a boss and gets a centre line and `Ø`, and anything less is a fillet or
  a round and gets `R` on a leader that lies along the radius it names, with
  the arrow on the arc. Equal ones are grouped the way a drawing groups
  them — `4× R5` — and a filleted, shelled box comes out `4× R5` outside and
  `4× R3` in, which is what the corner actually is. A round earns no centre
  mark and no position dimension: a crosshair in the solid metal of a corner
  says there is a hole there, and a fillet's centre is set by the corner it
  rounds, not by the datum. Two radii are called out per view and a note says
  the rest are as modelled. Reading every circular edge as a hole was the
  older behaviour, and it called a 5mm corner `Ø10` and then dimensioned
  where its centre sat.
* **Leaders that keep out of each other's way.** Diameters leave a view
  up-right and down-right; radii leave by a corner the diameters have not
  taken, upwards first, because the overall dimensions live below and to the
  left.
* **Line types** (ISO 128-2): two widths in a 2:1 ratio, hidden detail
  dashed, centre lines long-dash-dotted. The pictorial view drops hidden
  detail, which is clutter rather than information there.
* **An ISO 7200 title block** — owner, title, drawing number, date, scale,
  units, projection, sheet — plus the size and volume the kernel measured.

A drawing outlives the code that drew it — the run directory keeps it — so
each sheet records which conventions drew it, and one written before a
convention changed is drawn again rather than served from the cache. The
cached projection carries the same kind of marker, because a projection taken
before the sweep of each circular edge was recorded cannot tell a hole from a
round.

It carries no tolerances and no material, and says so on the sheet. Nothing
in the pipeline has specified either, and a general tolerance note on a part
nobody has toleranced would be a claim rather than a fact.

**Download DXF** hands back the same drawing as a DXF — which is the format a
drawing is exchanged in, and the reason the sheet is worth more than a
picture. Its dimensions are real `DIMENSION` entities carrying the geometry
they measure, so a CAD system opening the file re-measures the part rather
than reading back a string this app wrote; the line work is on the layers a
drawing office expects (`OUTLINE`, `HIDDEN`, `CENTRE`, `DIMENSIONS`,
`FRAME`), with ISO 128-24 line weights and ISO linetypes. It is written with
[ezdxf](https://ezdxf.mozman.at/), and the SVG on screen and the DXF are laid
out from one plan (`drawing.plan_sheet`) rather than from two implementations
that would drift.

**The sheet is built before anyone asks for it.** The hidden-line projection
is the expensive half of a drawing - seconds of OCCT work in a subprocess -
and it used to run when the Drawing button was clicked, so the button was
followed by a wait. It now starts the moment a version is published, in a
single background worker, and the result is cached beside the version. By the
time someone has finished turning the part around, the sheet is already on
disk: measured on a 20-tooth gear, 5.1 s of waiting became 15 ms. Nothing
waits on it — if the click somehow arrives first it builds the sheet as
before, and a prebuild that fails is silent, because the request path will
build it again and report any problem properly.

The projection is cached too (`projection.json`), so the DXF download does
not repeat the work the SVG already did — the same gear's DXF went from a
fresh projection to 0.27 s.

`app/tests/test_drawing.py` saves the DXF, reopens it with a reader that
knows nothing of how it was written, audits it, and asserts the dimensions
still measure the part. `app/tests/test_server.py` checks that the sheet
appears on disk without being requested, and that the DXF reuses the cached
projection rather than redoing it.

### Why this is written here rather than taken from a library

Asked directly, because it is a fair question for a few hundred lines of
sheet layout:

* **[ezdxf](https://ezdxf.mozman.at/)** — used, for the DXF. Mature, actively
  maintained, and the only sensible way to emit real `DIMENSION` entities,
  DXF line types and layer line weights. Writing that format by hand would be
  indefensible.
* **[build123d](https://build123d.readthedocs.io/)'s `drafting` module** —
  the closest thing to a drop-in: it has `Draft`, `DimensionLine`,
  `ExtensionLine`, `Callout` and a `TechnicalDrawing` border with a title
  block. Not used, for two reasons. It draws its annotations as CAD geometry
  in a modelling framework this app does not otherwise use — a second OCCT
  binding alongside CadQuery, for layout — and it would not do the part that
  is actually hard here: the hidden-line projection of four views, their
  first angle arrangement, and choosing what to dimension. Its title block is
  also not ISO 7200. Worth revisiting if this app ever moves to build123d.
* **FreeCAD's TechDraw workbench** — does all of this properly and is the
  right answer for a desktop tool. It means shipping FreeCAD to draw a
  rectangle.
* CadQuery's own SVG exporter — what this used to use. It fits each view to
  its own frame independently, which is the one thing a drawing may not do,
  and it gives no way to place an annotation next to the geometry without
  parsing the transform back out of the string it emitted.

So: the projection is OpenCASCADE's, the DXF is ezdxf's, and what is written
here is the sheet — which views go where, at what scale, and what gets
dimensioned. That part is drawing judgement rather than a solved library
problem.

**Choose a backend.** Provider, generation model and judge model sit under the
run options. See **Model backends** above.

**Diagnostics.** The chip in the header reports CadQuery, offscreen rendering,
the model backend and the metrics stack. Click it for detail. A demo that will
not work says so before you start.

**The right column holds four panels** — Reasoning, Design Plan, the code, and
Validation — and each keeps enough height to show something. When the window
is too short for all four, the column scrolls instead of crushing one of them
to its header, which is what it used to do: a panel reduced to its title bar
hides its content without looking like it is hiding anything. A panel with
more below the fold fades at that edge, so a truncated plan or verdict reads
as truncated rather than as finished.

**The rails are solid, and stack above the viewport.** The WebGL canvas is
transparent and it is the one element on screen whose size is set in script
rather than by the layout, so getting that wrong does not leave a gap — it
leaves the model's grid painted across whichever panel the canvas reaches,
and the clicks meant for a slider landing on the canvas instead. It reads as
the panels being see-through, which is why it is worth naming: `setSize` has
to update the canvas's CSS size as well as its drawing buffer, or on a 2×
display the element lays out at twice the stage. The rails also carry their
own stacking context, so a future mistake of the same shape stays inside the
viewport rather than over the reading.

## Standard parts, measured checks, and a spend ceiling

Four things sit between the request and the five agents.

**A standard part is served, not generated.** When a request is unambiguously
a catalogue part — "an M8x30 socket head cap screw", "a 6203 bearing", "a spur
gear 50mm diameter", "a 20mm keyed shaft" — there is nothing for five agents
to work out. The
dimensions come from the published standard, the geometry is exact, and a
model can only introduce error. `app/catalog/router.py` refuses anything
ambiguous, under-specified, or merely *mentioning* a standard part inside a
custom one ("a bearing housing for a 6203" is a housing), and it builds and
verifies every candidate before returning it. The result is badged
`CATALOGUE` everywhere it appears, carries no Judge verdict, and reports *no
model call* — a part no agent produced must never read as evidence that the
agents work. Turn it off with **Standard parts** to reproduce the published
pipeline exactly.

**The Planner is given published dimensions.** With **Standard dimensions**
on, a request naming a thread size, a bearing or a NEMA frame has the real
figures retrieved and handed to the Planner, so it is not guessing at an M8
pitch. Off reproduces the pipeline as published; the run log names what each
request was grounded in either way.

**Measurable claims are settled by the kernel, not the Judge.** The vision
Judge has been observed passing a plate carrying one hole where four were
asked for, and rejecting a part whose volume was exactly right.
`app/server/spec.py` measures the built solid for the quantities the plan
stated and lets the measurement decide: a hole-count shortfall blocks the
version whatever the Judge said. Which claims may block was decided by
measurement rather than taste — `overall_bbox` and `volume_estimate` both
flagged correct parts in testing, so they are reported and never block. A
gate that rejects correct work gets switched off, which is worse than not
having one. The Validation panel shows every measured row, and leads with the
measurement when it contradicts the Judge.

**A run cannot bill without bound.** Every turn of the loop is a paid model
call and the vision Judge sends an image each time, so on a metered backend a
loop that will not converge is not a slow run, it is a bill. Each run carries
a token ceiling (`CADSMITH_TOKEN_BUDGET`, 250,000 by default), checked before
each call; when the next call would exceed it the run stops and says so, and
the attempts it did produce are kept. The strip under the viewer shows the
spend per agent as the run goes. Tokens rather than money: tokens are what
the API reports exactly, and Bedrock is priced by AWS per region and per
model — set `CADSMITH_INPUT_PER_MTOK` and `CADSMITH_OUTPUT_PER_MTOK` from
your own pricing page if you want a cost estimate, and nothing is guessed
without them.

**A standard part needs no API key at all**, and the app no longer pretends
otherwise: Generate stays available with no provider configured, the note
under the provider picker says why, and a request the catalogue cannot serve
comes back with the key it needs named. Greying the button out denied the one
thing that was still working.

Spur gears are built here, from the ISO 53 basic rack: the flank is a true
involute, tip diameter is module × (teeth + 2) and the circular tooth
thickness at the pitch circle is π × module / 2, all measured in the kernel.
Gears are the standard part people ask for most and used to be the one family
that needed an optional git dependency, so that family now stands on its own.

**A gear can be asked for by diameter, not only by tooth count.** "A spur gear
50mm diameter" is how the request actually arrives, and it used to be refused
as under-specified — which sent it to five agents, cost five minutes, and came
back with trapezoidal teeth that do not mesh. A gear is defined by any two of
module, tooth count and diameter, so `standards.gear_teeth_for_diameter`
walks the ISO 54 preferred modules for the coarsest one landing on a whole
tooth count of at least seventeen: 50mm tip diameter is 18 teeth at module
2.5, exactly. Coarsest because for a given diameter a coarser module is a
stronger tooth, and seventeen because a 20° involute undercuts below it —
without that floor a 60mm gear comes out as ten teeth at module 5, which
measures correctly and is a worse gear than the eighteen-tooth module 3
beside it. A diameter no preferred module reaches — 31.4mm — is refused
rather than rounded, and a gear that names its own tooth count keeps the
face width and bore it always had.

**Shafts and what goes on them.** A gear needs a shaft, a shaft needs a key,
and none of those could be served either, so the same request that wanted a
gear wanted four pipeline runs. `parts.py` now builds shafts (plain, with a
DIN 6885-1 keyway cut to depth t1, and with a DIN 471 circlip groove),
parallel keys, plain bushings, retaining rings, set screws, threaded rod,
clamping shaft collars and clamping shaft couplings. The fastener families
come from published tables; collars and couplings have no published outside
geometry — every maker differs — so those carry commercial proportions, say
so in their docstring and expose them as parameters. `app/tests/
test_transmission.py` measures all of it against the tables in the kernel.

The remaining gear kinds — helical, herringbone, bevel, rack, ring — and the
wider fastener range need two optional libraries:

```bash
.venv/bin/pip install -r app/requirements-catalog.txt
```

Without them the catalogue degrades to the families it builds itself, which
`parts.BUILDERS` lists: spur gears, shafts, parallel keys, shaft collars,
shaft couplings, plain bushings, retaining rings, set screws, threaded rod,
timing pulleys, compression springs, ball bearings, o-rings, dowel pins,
washers and ISO 4762/4014/4032 screws and nuts. The health chip says which
of the rest are missing.
`app/tests/test_catalog_library.py` covers that path and reports the
library-dependent checks as skipped rather than failed, as do the browser
checks that ask for a part only those libraries can build.

## The handlebar case study

One part, carried the whole way, because a catalogue of washers and brackets
does not show what a tool is for. A motorcycle handlebar does: everyone
recognises one, the dozen named styles are the *same* part with different
numbers, and those numbers are published by the people who make them, so the
geometry can be checked against the real thing rather than against taste.

**How a bar is specified.** Five dimensions name one, and they are the five
the trade uses - width tip to tip, rise above the clamp, pullback, the
straight in the middle the risers hold, and the straight at each end the
grip, throttle and switchgear need. `docs/handlebar-research.md` is where
each number came from: four production road bends with all five published,
the reference drawing this study was given, and the ranges the custom trade
quotes for apes and trackers.

**The rest is solved, not stated.** The sweep angle is whatever leaves
exactly the control length of straight at the tip. The centreline stops half
a tube short of the stated width, because a tube cut square to a swept grip
reaches past its own centreline and width is measured across the widest
point. Ten bends come out measuring what they claim to within a tenth of a
millimetre - and they are measured, off the end faces of the built solid,
not read back from the parameters.

**A bend costs room, and running out of it is the interesting case.** Each
bend eats `R x tan(turn/2)` out of the straights either side, so two bends
sharing a straight have to fit inside it. Where they do not, the radius is
reduced to the largest that does; where even that falls below one and a half
tube diameters - the point at which a 2 mm wall folds rather than bends -
the script refuses and names the dimension to give it. Four of the ten
styles hit that on the first attempt, and every one of them was genuinely
unbuildable.

**What the kernel then says about it.** A family can attach its own measured
checks now, and a bent tube has several worth making: the width tip to tip,
the rise and pullback off the end-face centres, that the two halves mirror
to within a rounding error, the tube and its wall, and the tightest bend as
a multiple of the tube diameter - `R45 on Ø22, 2.05 x diameter, a plain
rotary-draw bend`. The last one is advisory wherever it is measured,
including on bars the agents write themselves, because a mandrel bend is a
real thing to buy rather than a mistake. Under 1.5 it is not.

**And the drawing says it in the right language.** A bend leaves a torus
whose major radius is the centreline radius a tube bender is set to, and the
sheet dimensions that rather than the projected arcs - which do not agree
with it, since a tube seen along a bend axis draws its crown at the
centreline radius and a flank half a diameter either side. Before that the
same bend came out `R45` in the front view and `R56` in the view from above.
The tube itself is called out where it is seen end-on, `Ø22` outside and
`Ø18` in, which is how the reference drawing specifies it too.

**A bent tube is dimensioned along its path, not around its box.** The
bounding box of the commuter bar is 648 x 130.25 x 148, and only the first
of those is a number anyone can work to: 148 is the rise plus a tube, and
130.25 is the pullback plus a tube seen at an angle. So the projection
records the path - where each bend starts and stops, taken off the torus
faces, and where the tube is cut, taken off the centres of its two flat
faces - and the sheet dimensions that instead: a ladder of widths out to
each bend tangent, `63.12 / 151.15 / 174.41 / 262.44`, stacked shortest
first under the overall `648`, with the rise `126` and the pullback `110`
measured to the centreline. That is the pattern of the reference drawing,
and it is what a bender is set from. A view slides up its cell far enough
for the last rung of the ladder to stay inside the frame; every other part
on the sheet is laid out exactly where it was.

Ask for a named bend - "a drag bar", "mini ape hangers", "a commuter
handlebar", ドラッグバー - and it is served from the catalogue exactly and
instantly. Ask for "a handlebar" and it is not: a bar is five dimensions
rather than a size, and guessing which of ten was meant is the silent
substitution the router exists to prevent. The things that hold a bar - a
riser, a clamp, a grip, a bar-end weight - are declined for the same reason
a bearing housing is not a bearing.

## English and Japanese

The interface has a language switch in the header, and opens in Japanese by
itself on a machine whose browser asks for it. The choice is remembered.
`?lang=ja` in the URL wins over both, and is remembered too, so a link can be
handed to someone in the language they read.

**What is translated.** Everything a person reads: the interface, the run
log's own lines, the reasoning panel's agent labels, the verdict, the kernel
facts, the server's refusals, and the benchmark prompts. A Japanese prompt
card inserts the Japanese prompt — the same benchmark entry, term for term,
with every dimension and axis carried across, so the part built from either
language is the same part.

**What is not, deliberately.** What the model reads. The five agents in
`autofab/agents.py` are steered by English prompts, and the Refiner is handed
English measurements; translating either would change what the pipeline does
rather than what it says. The reasoning that streams into the panel is the
model's own words and is shown as written. Most of the environment panel's
details are left alone for the same reason — they quote the machine (a
version string, a package name, a library's own error), and quoting is not
translating. Where a detail is not a quote but a sentence this app wrote, the
server sends a short code and the facts instead of the English, and the
browser composes the sentence: the catalogue's family count, the certificate
store in use, why a backend is missing. `app/tests/test_i18n.py` parses each
module that talks to a model and fails the build if a Japanese string appears
in one.

**Editing in Japanese works without a model call.** `server/edits.py`
recognises a parameter change by English word, so 「厚さを 5mm にする」 would
otherwise fall through to the Refiner — slow with a backend configured, and
refused outright without one. `server/japanese.py` rewrites the instruction
into the vocabulary those patterns already speak, and only when the
instruction actually contains Japanese, so English can neither reach it nor
be changed by it. The refusals are the half that matters:
「補強リブを追加する」 still comes out as a rib, so the editor hands it to the
Refiner rather than patching whichever number happened to match and reporting
a rib it never made.

**Asking for a standard part in Japanese reaches the catalogue.** Same idea,
different table: `catalog/japanese.py` reads 「20歯 モジュール2 の平歯車」
into the words `catalog/router.py` matches on, so it is served from the
catalogue with no model call rather than sent to the Planner. Counts come in
several shapes — 20歯, 20枚歯, 歯数20 — and all three land on the same
20-tooth gear. Here too the refusals are the half that matters:
「20歯の歯車を入れるギヤボックス」 is a gearbox, not a gear, and the rewriter
has to produce the English word the router already declines on, or a request
for a housing is answered with the gear that goes inside it.

**Writing a custom prompt in Japanese** is a question about the model, not
about the app: the prompt reaches the Planner exactly as typed.

## Layout

```
app/
  server/
    app.py         HTTP routes, SSE stream, artifact serving, health
    jobs.py        job queue, per-job directories, edits, replays
    events.py      append-only event log, mirrored to events.jsonl
    instrument.py  makes the stock pipeline observable, without editing it
    edits.py       parameter-patch interpretation, with the Refiner as fallback
    providers.py   Anthropic, OpenAI, Ollama and any OpenAI-compatible backend
    drawing.py     the A3 drawing sheet: first angle projections, one
                   stated scale, dimensions and an ISO 7200 title block,
                   rendered to SVG for the screen and DXF for exchange
    replay.py      re-emits a recorded run at presentation speed
    i18n.py        the messages a person reads, in English and Japanese
    spec.py        kernel-measured checks against what the plan claimed
    budget.py      the token ceiling a run may not spend past
    catalog_run.py serves a standard part instead of generating it
  catalog/
    standards.py   dimensions from ISO 4762/4014/4032/7089/273/2338, ISO 15,
                   and NEMA ICS 16 motor frames
    parts.py       the families this app builds itself, parametrically,
                   involute spur gears among them
    grounding.py   published dimensions handed to the Planner
    library.py     the other gear kinds, wider fasteners and sprockets,
                   from cq_gears/cq_warehouse
    router.py      is this request a standard part, and which one
    verify.py      build it and check it before anyone relies on it
    japanese.py    Japanese read with the English vocabulary both the router
                   and edits.py match on
  web/
    index.html  style.css  app.js  api.js  viewer.js  vendor/three.min.js
    i18n.js        the interface dictionary and the language switch
  tools/
    seed_demo_run.py   record demo runs without an API key
  tests/
  runs/         one directory per run: events.jsonl, meta.json, v0/ v1/ …
```

Each version bundle holds `code.py`, `model.stl`, `model.step`,
`geometry.json`, `validation.json`, `render.png` and, once requested,
`drawing.svg`.

three.js is vendored rather than loaded from a CDN: a live demo should not
depend on the network.

## Testing without spending quota

A local OpenAI-compatible server stands in for a real provider, so the whole
pipeline runs — CadQuery builds the geometry, VTK renders it, the loop
refines — with the model replaced by canned replies:

```bash
python -m app.tools.mock_provider              # well behaved
python -m app.tools.mock_provider --fail 429   # rate limited
python -m app.tools.mock_provider --fail badjson   # prose around the JSON
python -m app.tools.mock_provider --fail novision  # refuses images
python -m app.tools.mock_provider --fail empty     # reasoning-only reply
python -m app.tools.mock_provider --fail hang      # never answers
```

Then in the app pick **Custom (OpenAI-compatible)**, base URL
`http://127.0.0.1:8123/v1`, models `mock-coder` and `mock-judge`. The scripted
run is deliberately imperfect — the first attempt is too thick and the Judge
rejects it — so the refinement loop is exercised rather than skipped.

Better than a real key for reproducing a failure, because the misbehaviour is
deterministic.

## Tests

```bash
.venv/bin/pip install -r app/requirements-dev.txt

.venv/bin/python -m app.tests.test_instrumentation  # pipeline hooks, real kernel
.venv/bin/python -m app.tests.test_server           # HTTP, SSE, artifacts
.venv/bin/python -m app.tests.test_edits            # edit interpretation
.venv/bin/python -m app.tests.test_edit_flow        # both edit paths, real kernel
.venv/bin/python -m app.tests.test_replay           # recorded run fidelity
.venv/bin/python -m app.tests.test_providers        # non-Anthropic backend, real kernel
.venv/bin/python -m app.tests.test_i18n             # both dictionaries, and what
                                                    # must stay English
.venv/bin/python -m app.tests.test_catalog          # the catalogue, real kernel
.venv/bin/python -m app.tests.test_transmission     # gears, shafts, keys, collars
.venv/bin/python -m app.tests.test_catalog_library  # every family builds and routes
.venv/bin/python -m app.tests.test_grounding        # published dimensions retrieved
.venv/bin/python -m app.tests.test_spec             # measurement over opinion,
                                                    # clashes, and whether it
                                                    # could be made
.venv/bin/python -m app.tests.test_drawing          # the drawing sheet against
                                                    # the standards it cites
.venv/bin/python -m app.tests.test_budget           # the spend ceiling
.venv/bin/python -m app.tests.test_edit_chain       # chained edits, real kernel
.venv/bin/python -m pytest app/tests/test_encoding.py   # UTF-8 everywhere (Windows)
.venv/bin/python -m app.tests.test_layout           # panel geometry, real browser
.venv/bin/python -m app.tests.test_thinking_stream  # streamed reasoning, and the
                                                    # effort the run asked for
.venv/bin/python -m app.tests.ui_check              # real browser, needs a server
.venv/bin/python -m app.tests.ui_generate_check     # a real run in a browser,
                                                    # plus provider failures
.venv/bin/python -m app.tests.ui_catalog_check      # the catalogue in a browser
.venv/bin/python -m app.tests.ui_edit_check         # editing in a browser
.venv/bin/python -m app.tests.ui_export_check       # STEP, STL and .py downloads
.venv/bin/python -m app.tests.ui_lang_check         # the language switch
.venv/bin/python -m app.tests.ui_prompts_check      # prompts nobody planned for
.venv/bin/python -m app.tests.ui_stress_check       # clicking during a run
.venv/bin/python -m app.tests.ui_params_check       # the parameter controls
                                                    # over every part family,
                                                    # and the right column
```

`app/tools/eval_parts.py` scores the app against twenty fixed prompts on what
a kernel can settle - extents, bores, hole counts, volume, watertightness -
so a change to a prompt or a schema can be told apart from a regression.
`--catalogue-only` runs the seven standard-part cases with no model calls and
costs nothing; the rest spend real money, twenty parts at a Planner, a Coder
and a Judge each. `--baseline` diffs against a saved run and names anything
that regressed.

```bash
.venv/bin/python -m app.tools.eval_parts --catalogue-only    # free
.venv/bin/python -m app.tools.eval_parts --effort low --out eval-low.json
.venv/bin/python -m app.tools.eval_parts --baseline eval-low.json
```

`app/tools/census.py` parses every script the model has already written under
`app/runs` and counts which CadQuery operations it actually reaches for. It
exists to answer one question with evidence rather than argument: how wide
would a feature vocabulary have to be to replace these scripts with an
ordered, named, suppressible feature document? Over 367 stored scripts the
answer is **17 distinct building operations, of which 10 cover 90% and 15
cover 99%**, and seven selectors dominated by `faces` and `workplane`. A
declarative feature IR is therefore a small vocabulary with an escape hatch,
not a large one - though note those scripts come from seeded demo runs and
test runs, so a real user population may be wider.

`--tree` prints one script as the feature list a tree view would show, which
is the cheapest possible answer to whether such a view would be useful:

```bash
.venv/bin/python -m app.tools.census
.venv/bin/python -m app.tools.census --tree app/runs/<job>/v0/code.py
```

`app/tests/ui_parts_check.py` is known to fail: it expects the mock provider
to answer from `app/tools/mock_parts.py`, and `app/tools/mock_provider.py`
never consults it, so every prompt gets the same 40 x 30 x 10 placeholder.
Wiring the two together would change the canned replies every other browser
check is written against, so it is left as it is.

Only the Anthropic HTTP call is faked, by patching `agents._get_client`. The
real agent bodies run, including prompt assembly and RAG retrieval from KB1 and
KB2, and CadQuery and VTK do real work throughout.

## Two bugs left in the research code

Both are one-line fixes, deliberately not applied so `autofab/` stays as
published:

- `autofab/validator.py:174` records a **failed** Judge API call as a *passing*
  check, so a rate limit or network blip silently converges a part. The app
  detects this and reports it as a failure, but `run.py` and the benchmark
  scripts still behave as published.
- `requirements.txt` omits `scipy`, which `autofab/metrics.py:30` imports, so a
  fresh install from that file alone cannot compute CD/F1/IoU.
  `app/requirements-app.txt` adds it.
