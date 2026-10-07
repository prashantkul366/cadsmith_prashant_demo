# Running both branches on your own machine

Two branches, two roads to a part, and they are meant to be run side by
side so the difference is visible:

| branch | what it does | needs |
|---|---|---|
| `claude/handlebar-case-study` | the model writes a CadQuery script, the kernel runs it | a model endpoint |
| `claude/freecad-mcp` | the model calls FreeCAD tools, one feature at a time | a model endpoint **and** FreeCAD running with the MCP addon |

Use **two separate working copies**, one per branch, so both can be up at
once on different ports. Switching branches in one copy means stopping the
server, and the two have different dependencies checked out.

---

## 1. Once per working copy

```bash
git clone <this repo> cadsmith-script   && cd cadsmith-script
git checkout claude/handlebar-case-study

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -r app/requirements-app.txt
```

```powershell
# Windows PowerShell
git clone <this repo> cadsmith-script ; cd cadsmith-script
git checkout claude/handlebar-case-study

python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip setuptools wheel
.venv\Scripts\python -m pip install -r app\requirements-app.txt
```

Then the same again in a second folder, `cadsmith-freecad`, with
`git checkout claude/freecad-mcp`.

On headless Linux also `sudo apt-get install libosmesa6`, or the vision
Judge has no GL backend to render into. macOS and Windows need nothing.

**The standard-part catalogue (`app/requirements-catalog.txt`) is
optional.** Install it or do not - either is safe now. It used to answer
six of the sixty-one prompts with the wrong piece of hardware; it no
longer answers any of them.

## 2. The endpoint, in `.env` at the repository root

`.env` is git-ignored, so nothing here reaches the repository. One file per
working copy, the same three lines in both:

```
CADSMITH_LLM_BASE_URL=https://<your-tunnel>/v1
CADSMITH_LLM_API_KEY=<the endpoint's key>
CADSMITH_LLM_MODEL=Qwen/Qwen3-VL-8B-Instruct
```

In the app, pick **Custom (OpenAI-compatible)** as the provider. The model
dropdown fills itself from the endpoint's own `/v1/models`.

A quick tunnel's hostname changes every time it restarts, so this is the
one line to check before a demo.

## 3. Check it before anybody is watching

```bash
.venv/bin/python -m app.tools.doctor        # is the endpoint reachable, what is it serving
.venv/bin/python -m app.tools.check_stream  # one real call, streamed
```

`doctor` answering **530** means the tunnel is up but the vLLM behind it is
not. **524** means the model is slower than the tunnel's 100-second
patience - the app retries that three times now, but it is worth knowing
before the meeting.

## 4. Start the script road

```bash
./app/run_app.sh                 # http://127.0.0.1:8000
```
```powershell
.\app\run_app.ps1                # http://127.0.0.1:8000
```

Open the page. The health chip at the top should say CadQuery, offscreen
rendering and the model backend are all ready.

## 5. Start the tool road

FreeCAD has to be running, with the addon started, before the app can use
it:

1. Open FreeCAD (1.0 or newer).
2. Install the [FreeCAD MCP addon](https://github.com/neka-nat/freecad-mcp)
   if it is not there: **Tools → Addon Manager**, search *MCP*.
3. Switch to the **MCP Addon** workbench and click **Start RPC Server**.

Then, in the `cadsmith-freecad` copy:

```bash
PORT=8001 ./app/run_app.sh
.venv/bin/python -m app.tools.freecad_check     # proves the round trip
```
```powershell
.\app\run_app.ps1 -Port 8001
.venv\Scripts\python -m app.tools.freecad_check
```

`freecad_check` builds a plate with four holes and a pocket **inside
FreeCAD**, brings the solid back, measures it and draws it. If that passes,
the road works; if it says FreeCAD is offline, the addon's RPC server is not
started.

The app's health chip names it too: *"connected at 127.0.0.1:9875"*. If
FreeCAD is on another machine, set `CADSMITH_FREECAD_HOST` and
`CADSMITH_FREECAD_PORT`.

**A FreeCAD that is not running is not an error.** The job says so and falls
through to the script road, which is why the tool-road copy still works with
FreeCAD shut.

## 6. Running the prompts

Paste a prompt, press Generate. Worth knowing:

* **Leave the catalogue and the dimension grounding on.** Grounding hands
  the Planner the published numbers for any standard thread or fastener the
  request names, which it otherwise has to remember.
* **Iterations** is how many times the Refiner may try again after the
  Judge objects. Three is the default; one is faster for a demo, and a
  weak model rarely recovers on the third.
* **Vision** shows the Judge a render. Keep it on - the endpoint is serving
  a VL model, and it is the check that catches a part that measures right
  and looks wrong.
* The same model doing generation and judging grades its own work; the app
  says so in the run log. With one endpoint there is no alternative, and it
  is worth saying out loud rather than hiding.

Every run records itself under `app/runs/<id>/`: the events, the design
plan, the script or the tool calls, the STEP, the STL, the drawing, and
the kernel's own measurements. Nothing needs to be re-run to show it again
- **History** reopens any of them.

## 7. When something goes wrong

| what you see | what it is | what to do |
|---|---|---|
| `530` from `doctor` | tunnel up, vLLM down | restart the vLLM |
| `524`, repeatedly | model slower than the tunnel | raise `CADSMITH_GATEWAY_ATTEMPTS`, or serve a faster model |
| *"the model backend is not configured"* | `.env` not read | check it is at the repository root, not in `app/` |
| *"FreeCAD is not answering"* | addon's RPC server not started | MCP Addon workbench → Start RPC Server |
| *"Could not import CadQuery and VTK"* | wrong interpreter | `PYTHON=/path/to/python ./app/run_app.sh` |
| a part builds but the gate shows a red row | the part really does not match the request | that is the gate working; read the row, it names the measurement |

## 8. The one thing that decides the output

On the script road the geometry is whatever the model writes; on the tool
road the model picks the steps and each one comes back measured. Either
way an 8B is small for mechanical parts - it produced a 25 mm cube with
one hole where four tapped holes were asked for, and the app correctly
reported that as not converged rather than passing it off.

If a bigger model can be served, serve it. Nothing in the app needs to
change: it is the same three lines in `.env`.
