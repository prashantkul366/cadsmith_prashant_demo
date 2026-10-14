# Running the YMRI branch on your own machine

Windows, FreeCAD, Claude on Bedrock. Every command below is run from the
repository root in PowerShell.

## 1. Get the branch

```powershell
git fetch origin
git checkout YMRI
git pull
```

## 2. The virtualenv

Only needed the first time, or when `requirements-app.txt` changes.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r app\requirements-app.txt
```

Python 3.11. CadQuery and VTK install as ordinary wheels, so no conda.

## 3. Bedrock

Nothing goes in a file if you are already signed in - the Anthropic SDK
reaches Bedrock through boto3, which resolves credentials exactly as the
AWS CLI does. Either sign in:

```powershell
aws sso login
$env:AWS_REGION = "us-east-1"      # whichever region has the models
```

or put `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`
and `AWS_REGION` in a `.env` in the repository root.

Check it before spending anything on a run:

```powershell
.venv\Scripts\python -m app.tools.bedrock_check
```

That costs one very small completion and reports each step separately, so
a failure says which one broke. `--no-call` never bills at all.

## 4. FreeCAD

Open FreeCAD, choose the **MCP Addon** workbench, click **Start RPC
Server**. The app talks to it on 127.0.0.1:9875. If yours is elsewhere:

```powershell
$env:CADSMITH_FREECAD_HOST = "127.0.0.1"
$env:CADSMITH_FREECAD_PORT = "9875"
$env:CADSMITH_FREECAD_TOKEN = ""     # only if the addon asks for one
```

## 5. Check everything before starting

```powershell
.venv\Scripts\python -m app.tools.doctor
```

Each layer reports on its own line with its fix beside it: Python,
packages, the CAD kernel, rendering, the model backend, **FreeCAD**, and
the port. It checks whichever backend is actually configured and says
which one and why; `--provider bedrock` forces it. The FreeCAD section goes all the way through - connection,
addon, a script run and read back, the documents you have open, the
feature tree, and an export - so if something is wrong it names the layer
rather than surfacing later as a run that hangs.

## 5a. A note if the repository lives in OneDrive

Two things follow from that, and neither is a fault in the app:

* **Everything it writes syncs.** `app\runs\` holds every part built,
  its STEP, its STL and its drawing. In a OneDrive folder those go to the
  cloud. For anything confidential, keep the checkout outside OneDrive -
  `C:\dev\cadsmith` or similar.
* **It is slower.** The first kernel operation took 32 seconds on a
  OneDrive path against about 2 on a local disk. The CAD kernel writes
  temporary files constantly, and every one of them is a sync event.

## 6. Start it

```powershell
.\app\run_app.ps1
```

Then open the address it prints. Pick **Bedrock** in the model chip beside
the prompt box.

---

## What to try, and what is new on this branch

**Build a part.** Type a description. With *Build in FreeCAD* on, it is
built feature by feature in the FreeCAD you have open rather than written
as a script - so the result is a document with a history, not a solid.

**Work in a document you already have open.** The *Work in* picker lists
what FreeCAD has open. Choose one and the assistant works in it.

**The feature tree** - the tree icon in the view bar. The document's own
history, with every number that can still be changed. Change one and the
part rebuilds. A value the part cannot be rebuilt with is refused, says
why, and puts the old one back. The undo in the card's header is
FreeCAD's own: it backs out a change made by asking, one made in the
panel, and one you made in FreeCAD yourself.

**Ask for a change.** "Open the mounting holes to 11", "lose the corner
fillets". It reads the same tree you are looking at, so it sees what you
changed by hand.

**Drawings** - the sheet icon, or download the DXF.

**Drawings without any of the above.** The 3D-to-2D part needs no model,
no network and no FreeCAD. Put STEP files in a folder:

```powershell
.venv\Scripts\python -m app.tools.sheets C:\parts C:\drawings
```

Each solid comes back as a `.dxf` with real DIMENSION entities, a `.svg`
to look at, and a line saying how many numbers the sheet carries and
whether every one of them is a measurement of the solid. `index.html`
lists them all.

---

## What is worth telling me

The useful thing is where it differed from what you meant:

- the prompt, and what it built instead
- what you had to fix by hand afterwards, and whether the tree let you
- anything it refused that it should have done
- anything it did that it should have refused
- the parts it was no use on at all - those are the most useful

Each run is saved under `app\runs\<id>\` with the prompt, every step, and
the resulting document. Sending me that folder sends me everything I need
to see what happened.
