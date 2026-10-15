# -*- coding: utf-8 -*-
"""Tech Expo (phases A-E) tracker, in the reference project's layout."""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

ARIAL   = "Arial"
HDR     = PatternFill("solid", fgColor="CCECFF")
TASKF   = PatternFill("solid", fgColor="FBE4D5")
WORKF   = PatternFill("solid", fgColor="EFD9F5")
PLAN    = PatternFill("solid", fgColor="F8CBAD")
ACT     = PatternFill("solid", fgColor="C6E0B4")
NAVY    = PatternFill("solid", fgColor="1F3864")
GREY    = PatternFill("solid", fgColor="E7E6E6")
YELLOW  = PatternFill("solid", fgColor="FFFF00")
thin    = Side(style="thin", color="000000")
BOX     = Border(left=thin, right=thin, top=thin, bottom=thin)

# Aug W1..W5, Sep W1..W5, Oct W1..W4
WEEKS = [("Aug", "W1", "1-7"), ("Aug", "W2", "8-14"), ("Aug", "W3", "15-21"),
         ("Aug", "W4", "22-28"), ("Aug", "W5", "29-31"),
         ("Sept", "W1", "1-7"), ("Sept", "W2", "8-14"), ("Sept", "W3", "15-21"),
         ("Sept", "W4", "22-28"), ("Sept", "W5", "29-30"),
         ("Oct", "W1", "1-7"), ("Oct", "W2", "8-14"), ("Oct", "W3", "15-21"),
         ("Oct", "W4", "22-28")]
FIRST_WEEK_COL = 6          # column F

# phase -> (label, header note, [ (activity, breakdown, [week indices]) ])
PHASES = [
("Phase A\nFirst web application\n30-31 Aug 2026\n24 commits | 3.9 h | 2 days", [
 ("Application scaffolding and job server",
  "• Event stream and zero-touch instrumentation of the research pipeline, attached without editing any of it (30 Aug)\n"
  "• Job manager and HTTP server; the app serves 127.0.0.1 only, so there is no inbound surface\n"
  "• Run history and replay, so a recorded run can be shown again with no network", [4]),
 ("Browser front end",
  "• STL viewer showing the mesh the CAD kernel itself exported (30 Aug)\n"
  "• Live pipeline panel: the five agents as they actually run\n"
  "• Design plan and verdict panels. Everything on screen comes from the pipeline — nothing is simulated and no progress bar runs on a timer", [4]),
 ("Model backends, edits and launchers",
  "• Anthropic, OpenAI, Ollama and any OpenAI-compatible endpoint supported (30 Aug)\n"
  "• Natural-language edits to an already-built part\n"
  "• PowerShell launcher and Windows setup notes\n"
  "• Carnegie Mellon's upstream work credited at the top of the README", [4]),
 ("First engineering drawing sheet",
  "• Orthographic projection from the built solid, through the CAD kernel's own hidden-line algorithm (30 Aug)\n"
  "• Present from the first night — the drawing was not bolted on later", [4]),
 ("Hardening and preflight",
  "• Preflight check that fails fast instead of hanging (31 Aug)\n"
  "• Trust the operating system's certificate store, for corporate networks that inspect TLS\n"
  "• Find a virtualenv named either .venv or venv\n"
  "• Clear the previous run's panels on a new run; stop the active stage escaping its container\n"
  "• Mock provider, so the interface can be tested with no model and no cost", [4]),
]),
("Phase B\nBedrock, Japanese,\ncatalogue, drawing\n7-15 Sep 2026\n20 commits | 7.3 h | 3 days", [
 ("AWS Bedrock backend with live reasoning",
  "• Claude on Amazon Bedrock added alongside the existing backends (7 Sep)\n"
  "• The model's real reasoning streamed to the panel as it is produced\n"
  "• Token budget sized for thinking, not only for the answer\n"
  "• A one-call check that the live SDK streams what the app expects, plus a model and config sweep", [5]),
 ("Japanese language support",
  "• Interface, run log and verdicts in Japanese, with the model kept reading English internally (7 Sep)\n"
  "• Text read and written as UTF-8 rather than the locale codec — without this, Japanese on a Windows machine is mojibake", [5]),
 ("Standard-parts catalogue and measured checks merged in",
  "• 18 standard part families served exactly from the published standard, with no model call (7 Sep)\n"
  "• Router that refuses an ambiguous request and hands it to the agents rather than guessing\n"
  "• Measured specification checks and the per-run spend ceiling brought into the same application", [5]),
 ("Engineering drawing and DXF export",
  "• The sheet became a drawing rather than four pictures: first-angle projection, one stated scale, centre lines, title block (14 Sep)\n"
  "• DXF emitted through ezdxf; the sheet lettered the way a drawing is lettered\n"
  "• Stale sheet headers fixed", [6]),
 ("Parameter controls on the code panel",
  "• A parameters view over the generated script's own parameters, so every dimension stays editable (14 Sep)\n"
  "• Right column given room to breathe\n"
  "• Catalogue made to work when nothing else is configured", [6]),
 ("Drawing built with the part; reasoning effort control",
  "• The drawing is produced when the part is, not when somebody opens the tab — projection takes real time (15 Sep)\n"
  "• Reasoning effort put on the panel and allowed to vary per run", [7]),
]),
("Phase C\nMeasured checks, grading,\nfirst real-model evaluation\n21 Sep 2026\n20 commits | 5.3 h | 1 day", [
 ("Measured specification checks sharpened",
  "• A rejected attempt explains itself by measurement, not only by the vision Judge's opinion (21 Sep)\n"
  "• Say where the holes are, not just how many there are\n"
  "• What the part is made of and how closely it must be held, as claims the plan states and the checks test\n"
  "• The request's own numbers held fixed, so a dimension the engineer gave cannot drift\n"
  "• Stop handing API keys to generated code", [7]),
 ("Grading by difficulty and by edit chain",
  "• Results graded by difficulty tier and by the edit chain an engineer actually works in (21 Sep)\n"
  "• Model calls per edit counted from the event log rather than from a counter that was never set\n"
  "• Evaluation timeout bounds the clock, not just the report", [7]),
 ("First real-model evaluation run",
  "• Qwen3-VL-8B run over the tiered prompt set and recorded (21 Sep)\n"
  "• 32 prompts in five tiers; 25 reached the model; 22 produced a valid solid; 95 of 112 dimensional checks passed\n"
  "• This is the evaluation quoted on the poster, in the deck and on the Evidence page", [7]),
 ("Bedrock made diagnosable",
  "• Say which AWS identity is actually in use, not merely that one resolved (21 Sep)\n"
  "• Show whether the variables reached the process, and where each came from — shell or file\n"
  "• Choose between a global and a regional profile on purpose, not alphabetically\n"
  "• Say why Bedrock cannot run, instead of announcing it ready and failing at the first prompt\n"
  "• Answer a bad model id in the browser, and prefer a versioned id", [7]),
]),
("Phase D\nUI refresh and expo pack\n21-24 Sep 2026\n22 commits | 6.4 h | 3 days", [
 ("Interface rebuilt around ask / watch / adjust",
  "• One view switch, with the controls floating on the model (21 Sep)\n"
  "• Left column became a conversation with one place to type; the prompt is never taken away\n"
  "• Right column became four cards that shut away, each in the part's own colour\n"
  "• Dimensions moved beside the part they change; the version strip scrolls\n"
  "• The reasoning given the centre of the rail — a 296 px rail is not a window to read five agents through", [7, 8]),
 ("Versions, undo and a movable rail",
  "• Left rail made movable, and the browser stopped serving yesterday's app (22 Sep)\n"
  "• Left rail made one panel; every version numbered; undo added\n"
  "• The gizmo turns the model", [8]),
 ("Japanese interface throughout",
  "• The whole application made readable in Japanese — interface, run log, verdicts, drawing title block and example prompts (22 Sep)", [8]),
 ("Catalogue corrections — gears",
  "• A derived gear sized above the undercut limit, while named standard gears are left alone (22 Sep)\n"
  "• A gear can be asked for by diameter, and the shaft it goes on is served with it\n"
  "• A sentence printing as NaN, and the app stating a size the kernel disputed, both fixed", [8]),
 ("Tech Expo material written",
  "• Exhibition overview workbook: exhibit summary, visitor scripts, stand setup, risks and fallbacks, every figure with its source, and the attribution (24 Sep)\n"
  "• 15-slide deck with speaker notes, plus a one-page presentation overview\n"
  "• Screenshots captured from the running application on 24 Sep\n"
  "• Viewport kept clear of the rails at every window size", [8]),
]),
("Phase E\nHandlebar case study\n24-25 Sep 2026\n12 commits | 3.2 h | 2 days", [
 ("Bend a handlebar from the numbers a bar is sold by",
  "• A handlebar generated from width, rise, pullback, sweep and clamp diameter — the five numbers a bar is actually sold by (24 Sep)\n"
  "• Ten bends drawn as a chart from their own geometry", [8]),
 ("Catalogue serves a handlebar in either language",
  "• A handlebar request answered from the catalogue in English or Japanese (24 Sep)\n"
  "• A catalogue part's own measurements shown where the agents' measurements normally go\n"
  "• Four bends offered for a bare request of 'a handlebar' instead of declining it (25 Sep)\n"
  "• Answers to the words the trade actually uses for each bend", [8]),
 ("Measure and cost a bent bar",
  "• Measure a bar once it is bent, and say what the bending cost (24 Sep)\n"
  "• The case study grounded in bars that exist, rather than invented ones", [8]),
 ("Dimension a bent tube properly",
  "• A bent tube dimensioned along its path, not around its bounding box (25 Sep)", [8]),
 ("Edit an imported solid; local endpoint recorded",
  "• Edit an imported solid that arrived with no feature tree (25 Sep) — the commit every later thread forks from\n"
  "• OpenAI-compatible calls streamed, and .env allowed to name the model\n"
  "• Recorded what the Qwen3-VL endpoint actually did with the agent path", [8]),
]),
]

wb = Workbook()
ws = wb.active
ws.title = "Tech Expo A-E"

# ---------------- header ----------------
LEFT = [("Task", 16), ("Phase", 26), ("Activity", 30),
        ("Breakdown Tasks", 86), ("Planned/\nActual", 11)]
for i, (name, width) in enumerate(LEFT, start=1):
    ws.merge_cells(start_row=1, start_column=i, end_row=3, end_column=i)
    c = ws.cell(row=1, column=i, value=name)
    c.font = Font(ARIAL, size=10, bold=True)
    c.fill = HDR
    c.alignment = Alignment("center", "center", wrap_text=True)
    ws.column_dimensions[get_column_letter(i)].width = width

col = FIRST_WEEK_COL
month_start = col
for i, (month, wk, days) in enumerate(WEEKS):
    nxt = WEEKS[i + 1][0] if i + 1 < len(WEEKS) else None
    ws.cell(row=2, column=col, value=wk).font = Font(ARIAL, size=9, bold=True)
    ws.cell(row=3, column=col, value=days).font = Font(ARIAL, size=8)
    for r in (2, 3):
        cc = ws.cell(row=r, column=col)
        cc.fill = HDR
        cc.alignment = Alignment("center", "center")
    ws.column_dimensions[get_column_letter(col)].width = 6.2
    if nxt != month:
        ws.merge_cells(start_row=1, start_column=month_start, end_row=1, end_column=col)
        m = ws.cell(row=1, column=month_start, value=month)
        m.font = Font(ARIAL, size=10, bold=True)
        m.fill = HDR
        m.alignment = Alignment("center", "center")
        month_start = col + 1
    col += 1
LAST = col - 1
ws.row_dimensions[1].height = 18
ws.row_dimensions[2].height = 15
ws.row_dimensions[3].height = 14

# ---------------- body ----------------
row = 4
body_start = row
for phase_label, acts in PHASES:
    phase_top = row
    for activity, breakdown, weeks in acts:
        ws.merge_cells(start_row=row, start_column=3, end_row=row + 1, end_column=3)
        a = ws.cell(row=row, column=3, value=activity)
        a.font = Font(ARIAL, size=9, bold=True)
        a.alignment = Alignment("left", "center", wrap_text=True)

        ws.merge_cells(start_row=row, start_column=4, end_row=row + 1, end_column=4)
        b = ws.cell(row=row, column=4, value=breakdown)
        b.font = Font(ARIAL, size=9)
        b.alignment = Alignment("left", "center", wrap_text=True)

        for off, (label, fill) in enumerate((("Planned", PLAN), ("Actual", ACT))):
            t = ws.cell(row=row + off, column=5, value=label)
            t.font = Font(ARIAL, size=9)
            t.fill = fill
            t.alignment = Alignment("center", "center")
            for w in weeks:
                ws.cell(row=row + off, column=FIRST_WEEK_COL + w).fill = fill
        lines = breakdown.count("\n") + 1
        h = max(16, (lines * 11.5) / 2 + 3)
        ws.row_dimensions[row].height = h
        ws.row_dimensions[row + 1].height = h
        row += 2

    ws.merge_cells(start_row=phase_top, start_column=2, end_row=row - 1, end_column=2)
    p = ws.cell(row=phase_top, column=2, value=phase_label)
    p.font = Font(ARIAL, size=9, bold=True)
    p.fill = WORKF
    p.alignment = Alignment("center", "center", wrap_text=True)

# the navy banner, as in the reference
banner_row = row
ws.merge_cells(start_row=banner_row, start_column=FIRST_WEEK_COL + 9,
               end_row=banner_row, end_column=LAST)
bn = ws.cell(row=banner_row, column=FIRST_WEEK_COL + 9,
             value="Phases A–E complete 25 Sep 2026 · Tech Expo 2026 material delivered "
                   "· later threads tracked separately")
bn.font = Font(ARIAL, size=9, bold=True, color="FFFFFF")
bn.fill = NAVY
bn.alignment = Alignment("center", "center", wrap_text=True)
ws.merge_cells(start_row=banner_row, start_column=3, end_row=banner_row, end_column=5)
d = ws.cell(row=banner_row, column=3,
            value="Delivered: web prototype · deck EN/JP · A1 poster, booth 15-05 "
                  "· demo video · stand pack · prompt library")
d.font = Font(ARIAL, size=9, bold=True)
d.fill = GREY
d.alignment = Alignment("left", "center", wrap_text=True)
ws.row_dimensions[banner_row].height = 30
row += 1

ws.merge_cells(start_row=body_start, start_column=1, end_row=banner_row, end_column=1)
t = ws.cell(row=body_start, column=1, value="Text to CAD\n(Tech Expo 2026)")
t.font = Font(ARIAL, size=11, bold=True)
t.fill = TASKF
t.alignment = Alignment("center", "center", wrap_text=True)

for r in range(1, banner_row + 1):
    for c in range(1, LAST + 1):
        ws.cell(row=r, column=c).border = BOX

note = ws.cell(row=banner_row + 2, column=1,
    value="Week convention, taken from the reference tracker (AI Hackathon 12–14 Aug sits in Aug W2): "
          "W1 = 1–7, W2 = 8–14, W3 = 15–21, W4 = 22–28, W5 = 29–end of month. "
          "Dates are IST (+05:30).   ■  This project was not run to a written weekly plan, so the "
          "Planned row is reconstructed from the record and shows no variance by construction; the Actual "
          "row is measured from the commit history. See the 'Method & Notes' sheet.")
note.font = Font(ARIAL, size=9, italic=True)
note.alignment = Alignment("left", "top", wrap_text=True)
ws.merge_cells(start_row=banner_row + 2, start_column=1,
               end_row=banner_row + 3, end_column=LAST)
ws.freeze_panes = "F4"
ws.sheet_view.zoomScale = 85

# ===================== sheet 2: phase summary =====================
s2 = wb.create_sheet("Phase Summary")
cols = [("Phase", 10), ("What it delivered", 62), ("Start", 11), ("End", 11),
        ("Weeks", 18), ("Working days", 13), ("Commits", 9), ("Hours", 8),
        ("Lines added", 12), ("Lines removed", 13)]
for i, (n, w) in enumerate(cols, start=1):
    c = s2.cell(row=1, column=i, value=n)
    c.font = Font(ARIAL, size=10, bold=True)
    c.fill = HDR
    c.alignment = Alignment("center", "center", wrap_text=True)
    c.border = BOX
    s2.column_dimensions[get_column_letter(i)].width = w

SUMMARY = [
 ("A", "First web application: pipeline instrumentation, job server, STL viewer, live agent "
       "panel, plan and verdict panels, multi-provider backends, natural-language edits, replay, "
       "the first orthographic drawing sheet, and the preflight and TLS hardening around it.",
  "2026-08-30", "2026-08-31", "Aug W5", 2, 24, 3.9, 10570, 91),
 ("B", "Claude on Amazon Bedrock with live reasoning; Japanese throughout; the 18-family "
       "standard-parts catalogue, measured specification checks and the spend ceiling merged in; "
       "the sheet made a real engineering drawing with DXF export; parameter controls.",
  "2026-09-07", "2026-09-15", "Sept W1, W2, W3", 3, 20, 7.3, 14932, 1097),
 ("C", "Measurement sharpened — hole positions, material and closeness, the request's own "
       "numbers held fixed, rejections explained by measurement. Grading by difficulty and edit "
       "chain. The first real-model evaluation (Qwen3-VL-8B, 32 prompts). Bedrock made diagnosable.",
  "2026-09-21", "2026-09-21", "Sept W3", 1, 20, 5.3, 3396, 340),
 ("D", "The interface as demonstrated: conversation column, viewport with floating controls and "
       "gizmo, four collapsible cards, numbered versions, undo, movable rail, Japanese throughout. "
       "Plus the Tech Expo pack — overview workbook, deck, stand documents and screenshots.",
  "2026-09-21", "2026-09-24", "Sept W3, W4", 3, 22, 6.4, 5267, 1086),
 ("E", "Handlebar case study: a bar bent from the five numbers it is sold by, served from the "
       "catalogue in either language, measured and costed once bent, dimensioned along its path. "
       "Editing an imported solid with no feature tree — the fork point for every later thread.",
  "2026-09-24", "2026-09-25", "Sept W4", 2, 12, 3.2, 3546, 157),
]
r = 2
for row_vals in SUMMARY:
    for i, v in enumerate(row_vals, start=1):
        c = s2.cell(row=r, column=i, value=v)
        c.font = Font(ARIAL, size=9, bold=(i == 1))
        c.alignment = Alignment("left" if i == 2 else "center", "center",
                                wrap_text=(i == 2))
        c.border = BOX
    s2.row_dimensions[r].height = 54
    r += 1
tot = r
s2.cell(row=tot, column=1, value="TOTAL").font = Font(ARIAL, size=10, bold=True)
s2.cell(row=tot, column=2,
        value="Phases A–E — the Tech Expo work").font = Font(ARIAL, size=9, bold=True)
s2.cell(row=tot, column=3, value="2026-08-30").font = Font(ARIAL, size=9, bold=True)
s2.cell(row=tot, column=4, value="2026-09-25").font = Font(ARIAL, size=9, bold=True)
s2.cell(row=tot, column=5, value="27 calendar days").font = Font(ARIAL, size=9, bold=True)
for col_i in (6, 7, 8, 9, 10):
    L = get_column_letter(col_i)
    c = s2.cell(row=tot, column=col_i, value="=SUM(%s2:%s%d)" % (L, L, tot - 1))
    c.font = Font(ARIAL, size=10, bold=True)
    c.alignment = Alignment("center", "center")
for col_i in range(1, 11):
    c = s2.cell(row=tot, column=col_i)
    c.fill = GREY
    c.border = BOX
s2.cell(row=tot + 2, column=1,
    value="Working days are counted per phase; 21 and 24 Sep each carried two phases, so the "
          "phase column sums to 11 against 9 distinct calendar days worked. Hours are split "
          "between phases in proportion to the commits in each sitting. Line counts cover .py, "
          ".js, .css, .html, .md, .toml, .sh and .ps1 only.").font = Font(ARIAL, size=9, italic=True)
s2.merge_cells(start_row=tot + 2, start_column=1, end_row=tot + 3, end_column=10)
s2.cell(row=tot + 2, column=1).alignment = Alignment("left", "top", wrap_text=True)

# ===================== sheet 3: day log =====================
s3 = wb.create_sheet("Day Log")
cols3 = [("Date (IST)", 12), ("Day", 7), ("Window", 14), ("Hours", 8),
         ("Commits", 9), ("Phase", 9), ("What was done", 110)]
for i, (n, w) in enumerate(cols3, start=1):
    c = s3.cell(row=1, column=i, value=n)
    c.font = Font(ARIAL, size=10, bold=True)
    c.fill = HDR
    c.alignment = Alignment("center", "center", wrap_text=True)
    c.border = BOX
    s3.column_dimensions[get_column_letter(i)].width = w

DAYS = [
 ("2026-08-30", "Sun", "22:57–00:50", 2.2, 14, "A",
  "The whole first application in one sitting: scaffolding and zero-touch pipeline instrumentation, "
  "job manager, HTTP server, the front end (STL viewer, live pipeline, plan and verdict panels), "
  "natural-language edits, replay, multi-provider backends, PowerShell launcher and Windows notes, "
  "the first orthographic drawing sheet, and the upstream credit in the README."),
 ("2026-08-31", "Mon", "10:11–11:33", 1.7, 10, "A",
  "Hardening: a preflight that fails fast instead of hanging; trust the OS certificate store for "
  "TLS-inspecting networks; find a venv named either way; clear the previous run's panels; stop the "
  "active stage escaping its container; add a mock provider."),
 ("2026-09-07", "Mon", "15:56–22:42", 3.9, 13, "B",
  "Bedrock backend streaming the model's real reasoning; the two applications merged — catalogue, "
  "grounding, measured checks and spend ceiling; Japanese added with the model kept reading English; "
  "UTF-8 instead of the locale codec; token budget sized for thinking; a live-SDK stream check and a "
  "model/config sweep. Separately, in the first repository: the Bedrock backend and IoU/analyzer fixes, "
  "merged as PR #1 at 12:55."),
 ("2026-09-14", "Mon", "09:17–15:16", 2.2, 5, "B",
  "The drawing became an engineering drawing, lettered as one, with DXF through ezdxf; a parameters "
  "view on the code panel; the catalogue made to work when nothing else is configured."),
 ("2026-09-15", "Tue", "11:17–12:10", 1.2, 2, "B",
  "The drawing built when the part is, not when someone asks for it; reasoning effort put on the panel "
  "and allowed to vary per run."),
 ("2026-09-21", "Mon", "01:48–20:00", 7.3, 27, "C + D",
  "The heaviest day, three threads at once. Measurement: rejections explained by measurement, hole "
  "positions, material and closeness, the request's numbers held fixed, no keys handed to generated "
  "code, grading by difficulty and edit chain, and the first real-model run recorded (Qwen3-VL-8B). "
  "Bedrock diagnostics: which identity, where each variable came from, global vs regional profile, why "
  "it cannot run. UI refresh begun: the shell, the conversation column, four cards, dimensions beside "
  "the part, reasoning given the centre."),
 ("2026-09-22", "Tue", "00:40–17:31", 3.5, 13, "D",
  "UI refresh continued: movable rail, then one panel with every version numbered and undo; the gizmo "
  "turns the model; the app made readable in Japanese; gear sizing above the undercut limit, askable by "
  "diameter, with the shaft served alongside; a sentence printing as NaN and a size the kernel disputed, "
  "both fixed."),
 ("2026-09-24", "Thu", "14:25–19:23", 2.0, 8, "D + E",
  "The Tech Expo pack written — exhibition overview, deck and stand documents — and the "
  "screenshots captured. Viewport kept out of the rails. Then the handlebar case study opened: bend a "
  "bar from the five numbers it is sold by, serve one from the catalogue in either language, measure it "
  "once bent and say what the bending cost."),
 ("2026-09-25", "Fri", "10:48–16:22", 2.2, 6, "E",
  "Handlebar finished: four bends offered rather than declining, the words the trade uses, a bent tube "
  "dimensioned along its path. OpenAI-compatible calls streamed. Editing an imported solid that arrived "
  "with no feature tree — the commit all three later threads fork from. The Qwen3-VL endpoint's "
  "behaviour on the agent path recorded."),
]
r = 2
for d in DAYS:
    for i, v in enumerate(d, start=1):
        c = s3.cell(row=r, column=i, value=v)
        c.font = Font(ARIAL, size=9)
        c.alignment = Alignment("left" if i == 7 else "center", "center",
                                wrap_text=(i == 7))
        c.border = BOX
    s3.row_dimensions[r].height = 62
    r += 1
s3.cell(row=r, column=1, value="TOTAL").font = Font(ARIAL, size=10, bold=True)
s3.cell(row=r, column=2, value="9 days").font = Font(ARIAL, size=9, bold=True)
for col_i, L in ((4, "D"), (5, "E")):
    c = s3.cell(row=r, column=col_i, value="=SUM(%s2:%s%d)" % (L, L, r - 1))
    c.font = Font(ARIAL, size=10, bold=True)
    c.alignment = Alignment("center", "center")
s3.cell(row=r, column=7,
        value="Phases A–E: 9 working days inside a 27-day span, 20 sittings.").font = \
    Font(ARIAL, size=9, bold=True)
for col_i in range(1, 8):
    c = s3.cell(row=r, column=col_i)
    c.fill = GREY
    c.border = BOX
s3.freeze_panes = "A2"

# ===================== sheet 4: method & notes =====================
s4 = wb.create_sheet("Method & Notes")
s4.column_dimensions["A"].width = 26
s4.column_dimensions["B"].width = 110
def block(r, head, body, fill=None):
    h = s4.cell(row=r, column=1, value=head)
    h.font = Font(ARIAL, size=10, bold=True)
    h.alignment = Alignment("left", "top", wrap_text=True)
    if fill:
        h.fill = fill
    b = s4.cell(row=r, column=2, value=body)
    b.font = Font(ARIAL, size=9)
    b.alignment = Alignment("left", "top", wrap_text=True)
    h.border = BOX
    b.border = BOX
    s4.row_dimensions[r].height = max(28, 12.5 * (body.count("\n") + 1 + len(body) // 150))
    return r + 1

t = s4.cell(row=1, column=1, value="Text to CAD — Tech Expo 2026 · phases A–E · method and notes")
t.font = Font(ARIAL, size=12, bold=True)
s4.merge_cells(start_row=1, start_column=1, end_row=1, end_column=2)
r = 3
r = block(r, "Week convention",
  "Taken from the reference tracker, where 'AI Hackathon Participation (12–14 Aug)' sits under Aug W2:\n"
  "W1 = 1–7   ·   W2 = 8–14   ·   W3 = 15–21   ·   W4 = 22–28   ·   W5 = 29 to end of month.\n"
  "The date range under each week label on the tracker sheet spells this out.")
r = block(r, "Time zone",
  "IST (+05:30), which is where the work was done — confirmed by the +0530 offset on the commits "
  "authored directly. Git stores timestamps in UTC; everything here is converted.")
r = block(r, "Planned vs Actual — read this",
  "This project was not run to a written weekly plan. The Actual row is measured from the commit "
  "history. The Planned row is reconstructed to match it, so it shows no variance by construction and "
  "carries no information about slippage. It is filled in only so the sheet keeps the same shape as the "
  "reference tracker. Do not present the match between the two rows as evidence of on-time delivery.",
  YELLOW)
r = block(r, "How the hours were derived",
  "Two independent methods that agree.\n"
  "1. From the commits: sort every commit; a gap of more than 90 minutes starts a new sitting; a "
  "sitting counts as last − first + 20 minutes for the work before its first commit. Conservative, "
  "because work that produced no commit is invisible to it.\n"
  "2. From a session log: one Claude session transcript survives, covering 6–15 Oct. Counting "
  "ten-minute windows containing any activity gives 24.6 hours where the commit method gives 26.8 — "
  "within 9%. That agreement is why the commit method is trusted for the earlier days, whose logs are gone.")
r = block(r, "Cross-check on the line counts",
  "This method puts the application at 22,642 lines of Python at the end of phase D. The expo "
  "workbook's independently measured figure for 24 Sep is 22,300. Same thing, measured twice.")
r = block(r, "What is NOT in these numbers",
  "• The upstream research pipeline (4,445 lines), which is Carnegie Mellon's work and is used unmodified.\n"
  "• Every hour spent outside the repositories: meetings, the poster, both decks, their review rounds, "
  "running the application on a Windows machine, capturing screenshots, and the expo itself.\n"
  "Read the hours as the build time visible in the repositories — a floor, not a ceiling.")
r = block(r, "Rounding",
  "Each phase and each day is rounded to one decimal place, so the phase total (26.1 h) and the day "
  "total (26.2 h) differ by 0.1 h. Commit counts are exact and agree at 98 in both.")
r = block(r, "Scope of this workbook",
  "Phases A–E only — 30 Aug to 25 Sep 2026, the Tech Expo work. The FreeCAD tool road, the "
  "manufacturing cost model and drawing audit, the YMRI feature tree and the NX work all came after "
  "25 Sep and are tracked separately. In particular, the '61 of 61 prompts built clean' figure belongs "
  "to the FreeCAD thread and must not be quoted as evidence for the expo.")
r = block(r, "Attribution",
  "The multi-agent pipeline and the 100-prompt benchmark are the work of Jesse Barkley, Rumi Loghmani "
  "and Amir Barati Farimani (Carnegie Mellon University), arXiv:2603.26512, used unmodified. Everything "
  "in this workbook is the application built around that pipeline.")
r = block(r, "Legend — tracker sheet", "")
for label, fill, text in (
    ("Planned", PLAN, "Reconstructed plan — see the note above."),
    ("Actual", ACT, "Measured from the commit history."),
    ("Navy banner", NAVY, "A milestone, as in the reference tracker."),
    ("Phase column", WORKF, "Phase name, dates, commits, hours and working days.")):
    c = s4.cell(row=r, column=1, value=label)
    c.fill = fill
    c.font = Font(ARIAL, size=9, bold=True,
                  color="FFFFFF" if fill is NAVY else "000000")
    c.alignment = Alignment("center", "center")
    c.border = BOX
    b = s4.cell(row=r, column=2, value=text)
    b.font = Font(ARIAL, size=9)
    b.alignment = Alignment("left", "center", wrap_text=True)
    b.border = BOX
    r += 1
block(r + 1, "Source",
  "Measured from the git history of prashantkul366/cadsmith_prashant_demo (all nine branches) and "
  "prashantkul366/CADSmith_Prashant, on 15 Oct 2026. The same figures are on the 'Timeline & Effort' "
  "Confluence page, docs/confluence/15-timeline-and-effort.md.")

# Excel recalculates both SUM rows the moment the file is opened, so the
# totals are live even though openpyxl stores no cached value for them.
wb.calculation.fullCalcOnLoad = True

OUT = "/tmp/claude-0/xl/Text2CAD-TechExpo-PhasesA-E-Tracker.xlsx"
wb.save(OUT)
print("saved", OUT)
