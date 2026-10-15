# 🖥️ Run It Yourself

One laptop, Python 3.11, no GPU. Everything runs locally except the model
calls, and the application serves `127.0.0.1` only — there is no inbound
surface.

## Setup

**macOS and Linux**

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r app/requirements-app.txt
```

**Windows PowerShell** — note `python`, not `python3`, and `Scripts\`
rather than `bin/`:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r app\requirements-app.txt
```

The CAD kernel and the renderer install as ordinary pip wheels, so no
conda environment is needed. Tested on Python 3.11.

## Four things that will bite you

**On Windows, keep the checkout out of OneDrive.** The virtual environment
runs to several hundred megabytes; syncing it is slow and can lock files
mid-install. Somewhere like `C:\dev\text2cad` avoids it.

**On headless Linux, install a software rasteriser.** The renderer imports
fine and then fails at render time with no GL backend, which silently
costs you the vision Judge:

```bash
sudo apt-get install libosmesa6
```

macOS and Windows need nothing extra. The preflight reports which case
you are in.

**Behind a corporate proxy**, model calls fail with
`[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer
certificate`. That is TLS inspection re-signing traffic with a company
certificate. The application uses the operating system's certificate store
and honours `SSL_CERT_FILE` and `REQUESTS_CA_BUNDLE`. Verification is
never disabled.

**Credentials go in `.env`, never in the repository.** One line is enough:

```
ANTHROPIC_API_KEY=...
```

or the AWS variables for Bedrock, or nothing at all if you are running a
local model.

## Running

```bash
./app/run_app.sh              # http://127.0.0.1:8000
PORT=9000 ./app/run_app.sh
./app/run_app.sh --reload
```

```powershell
.\app\run_app.ps1
.\app\run_app.ps1 -Port 9000
.\app\run_app.ps1 -Reload
```

Both read `.env`, so the health check reports the truth before the first
run starts.

## Before a demo — two commands

```bash
python -m app.tools.doctor
```

Reports Python, the CAD kernel, the renderer, the model backend and the
certificate store. Run it before the first visitor, not after.

```bash
python -m app.tools.seed_demo_run
```

Writes two runs with real geometry, so a recorded run can be replayed if
the network fails. Replay shows real geometry and real verdicts — it is
not a video.

## What works with no network at all

Standard parts (18 families), parameter edits, drawings, exports and run
replays. Only the five agents need a model backend. This is the fallback
if venue Wi-Fi fails, and it is also the fastest part of the demo.

## Spend

```
CADSMITH_TOKEN_BUDGET=250000
```

The per-run ceiling, checked before every model call. The run stops at the
limit and keeps what it produced.
