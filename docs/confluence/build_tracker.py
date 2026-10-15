# -*- coding: utf-8 -*-
"""Tech Expo (phases A-E) tracker - plain language, one row per activity."""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

ARIAL  = "Arial"
HDR    = PatternFill("solid", fgColor="CCECFF")
TASKF  = PatternFill("solid", fgColor="FBE4D5")
WORKF  = PatternFill("solid", fgColor="EFD9F5")
DONE   = PatternFill("solid", fgColor="C6E0B4")
NAVY   = PatternFill("solid", fgColor="1F3864")
GREY   = PatternFill("solid", fgColor="E7E6E6")
thin   = Side(style="thin", color="000000")
BOX    = Border(left=thin, right=thin, top=thin, bottom=thin)

WEEKS = [("Aug", "W1", "1-7"), ("Aug", "W2", "8-14"), ("Aug", "W3", "15-21"),
         ("Aug", "W4", "22-28"), ("Aug", "W5", "29-31"),
         ("Sept", "W1", "1-7"), ("Sept", "W2", "8-14"), ("Sept", "W3", "15-21"),
         ("Sept", "W4", "22-28"), ("Sept", "W5", "29-30"),
         ("Oct", "W1", "1-7"), ("Oct", "W2", "8-14"), ("Oct", "W3", "15-21"),
         ("Oct", "W4", "22-28")]
FIRST = 5          # week columns start at column E

B = "• "
PHASES = [
("Phase A\nFirst working app\n30-31 Aug 2026", [
 ("Set up the web application", [
   "Built the server and the web page the whole thing runs on",
   "Runs on the user's own laptop only - nothing is put on a network",
   "Keeps a history of past runs, so any of them can be shown again later"], [4]),
 ("Show the part on screen", [
   "3D viewer showing the part the CAD engine actually produced",
   "Live panel showing the five AI agents as they work",
   "Panels for the design plan and for the pass / fail result",
   "Everything on screen is real output - nothing is a mock-up or a timed animation"], [4]),
 ("Connect the AI models", [
   "Works with Claude, with OpenAI, and with models run on your own machine",
   "Change a part that has already been made by typing what to change",
   "One-click start-up script for Windows",
   "Credited the original research team in the project README"], [4]),
 ("First engineering drawing", [
   "Produced a proper 2D drawing from the 3D part, drawn by the CAD engine itself",
   "Included from the very first day, not added later"], [4]),
 ("Make it reliable", [
   "Checks that everything is installed before a run starts, instead of freezing",
   "Works on company networks that inspect secure traffic",
   "Added a test mode that exercises the whole interface with no AI and no cost"], [4]),
]),
("Phase B\nAWS, Japanese,\nstandard parts, drawings\n7-15 Sep 2026", [
 ("Connect to AWS Bedrock", [
   "Added Claude on Amazon Bedrock as a model option",
   "The AI's reasoning is shown live on screen as it works",
   "Added a quick test that confirms AWS is reachable before a demo"], [5]),
 ("Add Japanese", [
   "Interface, run log and results all available in Japanese",
   "Fixed the text handling that makes Japanese show as garbled characters on Windows"], [5]),
 ("Add the standard-parts library", [
   "18 families of standard parts - bearings, bolts, gears, pulleys and so on - built exactly "
   "to the published standard, instantly and with no AI call",
   "An unclear request is passed to the AI rather than guessed at",
   "Brought the dimension checking and the spending limit into the same app"], [5]),
 ("Make it a real engineering drawing", [
   "Added proper drawing conventions: first-angle views, a stated scale, centre lines and a title block",
   "Added DXF export, so the drawing opens in any CAD system"], [6]),
 ("Add the dimension sliders", [
   "Sliders for every dimension of the part that was generated",
   "Dragging one rebuilds the part in about a second, with no AI call"], [6]),
 ("Make the drawing instant", [
   "The drawing is now made at the same time as the part, so the tab opens straight away",
   "Added a control for how hard the AI thinks on each run"], [7]),
]),
("Phase C\nChecking, scoring,\nfirst full test\n21 Sep 2026", [
 ("Check the part against what was asked for", [
   "The app measures the finished part and compares it with the request",
   "Reports where the holes are, not only how many there are",
   "Records what the part is made of and how precisely it has to be made",
   "Dimensions the user gave are locked, so they cannot drift"], [7]),
 ("Score the results properly", [
   "Results scored by difficulty level, and by how well the app handles follow-up edits",
   "Counts how many AI calls each edit costs"], [7]),
 ("First full test with a real model", [
   "Ran 32 test requests end to end through an AI model hosted on our own machine",
   "22 of 25 produced a valid part; 95 of 112 dimension checks passed",
   "These are the numbers used on the poster and in the presentation"], [7]),
 ("Make AWS problems easy to diagnose", [
   "The app says why AWS will not run, instead of failing silently at the first request",
   "Shows which AWS account and region are in use, and where those settings came from"], [7]),
]),
("Phase D\nNew interface and\nexpo material\n21-24 Sep 2026", [
 ("Redesign the interface", [
   "Rebuilt around what a user actually does: ask, watch, adjust",
   "Left side is a conversation, with one box to type in",
   "Middle is the 3D part, with its controls floating over it",
   "Right side is four panels that fold away when they are not needed"], [7, 8]),
 ("Add version history and undo", [
   "Every version of the part is numbered and kept",
   "Undo added",
   "The part can be turned by dragging a handle on screen"], [8]),
 ("Japanese across the whole app", [
   "Interface, run log, results, drawing title block and example requests, all in Japanese"], [8]),
 ("Fix the gear generator", [
   "Gears sized so the teeth are not undercut",
   "A gear can be asked for by its diameter, and the shaft to fit it is supplied with it"], [8]),
 ("Write the Tech Expo material", [
   "Exhibition overview: summary, visitor scripts, stand checklist, risks and fallbacks, and the "
   "source of every figure quoted",
   "15-slide presentation with speaker notes, and a one-page summary document",
   "Screenshots taken from the running app"], [8]),
]),
("Phase E\nHandlebar example\n24-25 Sep 2026", [
 ("Generate a handlebar", [
   "A handlebar is produced from the five numbers a real one is sold by: width, rise, pullback, "
   "sweep and clamp size",
   "Ten different bends drawn as a comparison chart"], [8]),
 ("Handle handlebar requests in both languages", [
   "A handlebar can be asked for in English or in Japanese",
   "A plain request for 'a handlebar' offers four options instead of refusing",
   "Understands the names the trade actually uses for each bend"], [8]),
 ("Measure and cost a bent bar", [
   "Measures the bar after bending, and estimates what the bending costs",
   "Based on handlebars that are actually sold, not invented ones"], [8]),
 ("Dimension a bent tube correctly", [
   "A bent tube is measured along its curve, not across a box drawn around it"], [8]),
 ("Edit a part that came from outside", [
   "A CAD file brought in from elsewhere can now be edited, even though it has no build history",
   "This is the piece all the later work builds on"], [8]),
]),
]

wb = Workbook()
ws = wb.active
ws.title = "Tech Expo A-E"

LEFT = [("Task", 16), ("Phase", 24), ("Activity", 34), ("What was done", 92)]
for i, (name, width) in enumerate(LEFT, start=1):
    ws.merge_cells(start_row=1, start_column=i, end_row=3, end_column=i)
    c = ws.cell(row=1, column=i, value=name)
    c.font = Font(ARIAL, size=10, bold=True)
    c.fill = HDR
    c.alignment = Alignment("center", "center", wrap_text=True)
    ws.column_dimensions[get_column_letter(i)].width = width

col, month_start = FIRST, FIRST
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

row = 4
body_start = row
for phase_label, acts in PHASES:
    phase_top = row
    for activity, bullets, weeks in acts:
        a = ws.cell(row=row, column=3, value=activity)
        a.font = Font(ARIAL, size=10, bold=True)
        a.alignment = Alignment("left", "center", wrap_text=True)
        text = "\n".join(B + b for b in bullets)
        t = ws.cell(row=row, column=4, value=text)
        t.font = Font(ARIAL, size=9)
        t.alignment = Alignment("left", "center", wrap_text=True)
        for w in weeks:
            ws.cell(row=row, column=FIRST + w).fill = DONE
        wrapped = sum(1 + len(b) // 105 for b in bullets)
        ws.row_dimensions[row].height = max(26, 13.2 * wrapped + 6)
        row += 1
    ws.merge_cells(start_row=phase_top, start_column=2, end_row=row - 1, end_column=2)
    p = ws.cell(row=phase_top, column=2, value=phase_label)
    p.font = Font(ARIAL, size=10, bold=True)
    p.fill = WORKF
    p.alignment = Alignment("center", "center", wrap_text=True)

banner = row
ws.merge_cells(start_row=banner, start_column=FIRST + 9, end_row=banner, end_column=LAST)
bn = ws.cell(row=banner, column=FIRST + 9,
             value="Phases A–E finished 25 Sep 2026 · later work tracked separately")
bn.font = Font(ARIAL, size=9, bold=True, color="FFFFFF")
bn.fill = NAVY
bn.alignment = Alignment("center", "center", wrap_text=True)
ws.merge_cells(start_row=banner, start_column=3, end_row=banner, end_column=4)
d = ws.cell(row=banner, column=3,
            value="Delivered: working web app · presentation in English and Japanese "
                  "· A1 poster, booth 15-05 · demo video · stand pack · sample parts")
d.font = Font(ARIAL, size=9, bold=True)
d.fill = GREY
d.alignment = Alignment("left", "center", wrap_text=True)
ws.row_dimensions[banner].height = 28

ws.merge_cells(start_row=body_start, start_column=1, end_row=banner, end_column=1)
t = ws.cell(row=body_start, column=1, value="Text to CAD\n(Tech Expo 2026)")
t.font = Font(ARIAL, size=11, bold=True)
t.fill = TASKF
t.alignment = Alignment("center", "center", wrap_text=True)

for r in range(1, banner + 1):
    for c in range(1, LAST + 1):
        ws.cell(row=r, column=c).border = BOX

note = ws.cell(row=banner + 2, column=1,
    value="A green cell marks the week the work was done. Weeks follow the reference tracker: "
          "W1 = 1–7, W2 = 8–14, W3 = 15–21, W4 = 22–28, W5 = 29 to month end; "
          "the date range is printed under each week heading. Dates are IST. "
          "Everything here is taken from the project's own record of what was done and when.")
note.font = Font(ARIAL, size=9, italic=True)
note.alignment = Alignment("left", "top", wrap_text=True)
ws.merge_cells(start_row=banner + 2, start_column=1, end_row=banner + 3, end_column=LAST)
ws.freeze_panes = "E4"
ws.sheet_view.zoomScale = 85

# ===================== sheet 2: phase summary =====================
s2 = wb.create_sheet("Phase Summary")
cols = [("Phase", 9), ("What it delivered", 66), ("Start", 11), ("End", 11),
        ("Weeks", 18), ("Days worked", 12), ("Changes made", 13), ("Hours", 8)]
for i, (n, w) in enumerate(cols, start=1):
    c = s2.cell(row=1, column=i, value=n)
    c.font = Font(ARIAL, size=10, bold=True)
    c.fill = HDR
    c.alignment = Alignment("center", "center", wrap_text=True)
    c.border = BOX
    s2.column_dimensions[get_column_letter(i)].width = w

SUMMARY = [
 ("A", "A working web app: type a part, watch the AI build it, see it in 3D with its "
       "measurements, its drawing and every attempt along the way. Runs on a laptop.",
  "2026-08-30", "2026-08-31", "Aug W5", 2, 24, 3.9),
 ("B", "Claude on AWS Bedrock, the whole app in Japanese, a library of 18 standard part "
       "families served instantly, a proper engineering drawing with DXF export, and sliders "
       "for every dimension.",
  "2026-09-07", "2026-09-15", "Sept W1, W2, W3", 3, 20, 7.3),
 ("C", "The app began checking its own work: measuring the finished part against what was "
       "asked for, scoring results by difficulty, and the first full test run - 32 requests "
       "end to end. AWS problems made easy to diagnose.",
  "2026-09-21", "2026-09-21", "Sept W3", 1, 20, 5.3),
 ("D", "The interface as it was demonstrated - ask, watch, adjust - with version history, "
       "undo and Japanese throughout. Plus all the Tech Expo material: overview, presentation, "
       "stand pack and screenshots.",
  "2026-09-21", "2026-09-24", "Sept W3, W4", 3, 22, 6.4),
 ("E", "A worked example in our own field: a motorcycle handlebar generated from the five "
       "numbers a real one is sold by, in either language, measured and costed after bending. "
       "Also made it possible to edit a CAD file brought in from elsewhere.",
  "2026-09-24", "2026-09-25", "Sept W4", 2, 12, 3.2),
]
r = 2
for vals in SUMMARY:
    for i, v in enumerate(vals, start=1):
        c = s2.cell(row=r, column=i, value=v)
        c.font = Font(ARIAL, size=9, bold=(i == 1))
        c.alignment = Alignment("left" if i == 2 else "center", "center", wrap_text=(i == 2))
        c.border = BOX
    s2.row_dimensions[r].height = 50
    r += 1
tot = r
for i, v in ((1, "TOTAL"), (2, "Phases A–E — the Tech Expo work"),
             (3, "2026-08-30"), (4, "2026-09-25"), (5, "27 calendar days")):
    c = s2.cell(row=tot, column=i, value=v)
    c.font = Font(ARIAL, size=9 if i > 1 else 10, bold=True)
    c.alignment = Alignment("left" if i == 2 else "center", "center")
for i in (6, 7, 8):
    L = get_column_letter(i)
    c = s2.cell(row=tot, column=i, value="=SUM(%s2:%s%d)" % (L, L, tot - 1))
    c.font = Font(ARIAL, size=10, bold=True)
    c.alignment = Alignment("center", "center")
for i in range(1, 9):
    s2.cell(row=tot, column=i).fill = GREY
    s2.cell(row=tot, column=i).border = BOX
n = s2.cell(row=tot + 2, column=1,
    value="Days worked are counted per phase. 21 and 24 Sep each covered two phases, so this "
          "column adds to 11 against 9 separate days actually worked. 'Changes made' counts "
          "saved changes to the project. Hours are explained on the Method & Notes sheet.")
n.font = Font(ARIAL, size=9, italic=True)
n.alignment = Alignment("left", "top", wrap_text=True)
s2.merge_cells(start_row=tot + 2, start_column=1, end_row=tot + 3, end_column=8)

# ===================== sheet 3: day log =====================
s3 = wb.create_sheet("Day Log")
cols3 = [("Date", 12), ("Day", 7), ("Worked", 14), ("Hours", 8),
         ("Changes", 9), ("Phase", 9), ("What was done that day", 104)]
for i, (n_, w) in enumerate(cols3, start=1):
    c = s3.cell(row=1, column=i, value=n_)
    c.font = Font(ARIAL, size=10, bold=True)
    c.fill = HDR
    c.alignment = Alignment("center", "center", wrap_text=True)
    c.border = BOX
    s3.column_dimensions[get_column_letter(i)].width = w

DAYS = [
 ("2026-08-30", "Sun", "22:57–00:50", 2.2, 14, "A",
  "The whole first app, in one evening: the server, the web page, the 3D viewer, the live "
  "panel showing the AI agents at work, the design plan and result panels, support for three "
  "kinds of AI model, editing a part by typing, and the first engineering drawing."),
 ("2026-08-31", "Mon", "10:11–11:33", 1.7, 10, "A",
  "Made it reliable: check everything is installed before starting rather than freezing, work "
  "on company networks that inspect secure traffic, and a test mode that runs with no AI and "
  "no cost."),
 ("2026-09-07", "Mon", "15:56–22:42", 3.9, 13, "B",
  "Connected Claude on AWS Bedrock and put the AI's reasoning on screen as it works. Added "
  "Japanese. Brought in the standard-parts library, the dimension checking and the spending "
  "limit, all into one app."),
 ("2026-09-14", "Mon", "09:17–15:16", 2.2, 5, "B",
  "Turned the drawing into a proper engineering drawing and added DXF export, so it opens in "
  "any CAD system. Added the dimension sliders."),
 ("2026-09-15", "Tue", "11:17–12:10", 1.2, 2, "B",
  "Made the drawing at the same time as the part, so the drawing tab opens instantly. Added a "
  "control for how hard the AI thinks on each run."),
 ("2026-09-21", "Mon", "01:48–20:00", 7.3, 27, "C + D",
  "The biggest day, with three things running at once. Checking: measure the finished part "
  "against the request, report where the holes are, lock the dimensions the user gave, and "
  "score results by difficulty. The first full test with a real AI model - 32 requests end to "
  "end. AWS made easy to diagnose. And the interface redesign started."),
 ("2026-09-22", "Tue", "00:40–17:31", 3.5, 13, "D",
  "Interface redesign continued: version numbers, undo, a movable panel, turning the part by "
  "dragging, and Japanese across the whole app. Fixed the gear generator so teeth are not "
  "undercut."),
 ("2026-09-24", "Thu", "14:25–19:23", 2.0, 8, "D + E",
  "Wrote the Tech Expo material - the overview, the presentation and the stand documents - and "
  "took the screenshots. Then started the handlebar example: generate a bar from the five "
  "numbers it is sold by, and estimate what bending it costs."),
 ("2026-09-25", "Fri", "10:48–16:22", 2.2, 6, "E",
  "Finished the handlebar example: four bend options offered instead of refusing a vague "
  "request, the names the trade uses understood, and a bent tube measured along its curve. "
  "Also made it possible to edit a CAD file brought in from elsewhere - the piece all the "
  "later work builds on."),
]
r = 2
for d_ in DAYS:
    for i, v in enumerate(d_, start=1):
        c = s3.cell(row=r, column=i, value=v)
        c.font = Font(ARIAL, size=9)
        c.alignment = Alignment("left" if i == 7 else "center", "center", wrap_text=(i == 7))
        c.border = BOX
    s3.row_dimensions[r].height = 58
    r += 1
s3.cell(row=r, column=1, value="TOTAL").font = Font(ARIAL, size=10, bold=True)
s3.cell(row=r, column=2, value="9 days").font = Font(ARIAL, size=9, bold=True)
for i, L in ((4, "D"), (5, "E")):
    c = s3.cell(row=r, column=i, value="=SUM(%s2:%s%d)" % (L, L, r - 1))
    c.font = Font(ARIAL, size=10, bold=True)
    c.alignment = Alignment("center", "center")
s3.cell(row=r, column=7, value="Phases A–E: 9 days of work spread over 27 calendar days.")\
    .font = Font(ARIAL, size=9, bold=True)
for i in range(1, 8):
    s3.cell(row=r, column=i).fill = GREY
    s3.cell(row=r, column=i).border = BOX
s3.freeze_panes = "A2"

# ===================== sheet 4: method & notes =====================
s4 = wb.create_sheet("Method & Notes")
s4.column_dimensions["A"].width = 24
s4.column_dimensions["B"].width = 108
def block(r, head, body, fill=None):
    h = s4.cell(row=r, column=1, value=head)
    h.font = Font(ARIAL, size=10, bold=True)
    h.alignment = Alignment("left", "top", wrap_text=True)
    if fill:
        h.fill = fill
    b_ = s4.cell(row=r, column=2, value=body)
    b_.font = Font(ARIAL, size=9)
    b_.alignment = Alignment("left", "top", wrap_text=True)
    h.border = BOX
    b_.border = BOX
    s4.row_dimensions[r].height = max(26, 12.5 * (body.count("\n") + 1 + len(body) // 140))
    return r + 1

t = s4.cell(row=1, column=1,
            value="Text to CAD — Tech Expo 2026 · phases A–E · notes")
t.font = Font(ARIAL, size=12, bold=True)
s4.merge_cells(start_row=1, start_column=1, end_row=1, end_column=2)
r = 3
r = block(r, "What the green cells mean",
  "A green cell marks the week in which that activity was done. There is no separate planned "
  "row: this sheet records what happened, taken from the project's own record of every change "
  "and the date it was made.")
r = block(r, "Weeks",
  "Same convention as the reference tracker, where the AI Hackathon of 12–14 August sits "
  "under Aug W2:\n"
  "W1 = 1–7   ·   W2 = 8–14   ·   W3 = 15–21   ·   W4 = 22–28   "
  "·   W5 = 29 to the end of the month.\n"
  "The date range is printed under every week heading on the tracker sheet.")
r = block(r, "Dates and times",
  "IST. The project record stores times in UTC; they are converted here.")
r = block(r, "Where the hours come from",
  "Each saved change carries a timestamp. A run of changes with no gap longer than 90 minutes "
  "is counted as one sitting, and a sitting is measured from 20 minutes before its first change "
  "to its last. It is a careful estimate rather than a timesheet: time spent reading, testing or "
  "thinking without saving anything does not appear in it, so the real figure is higher.")
r = block(r, "Checked twice",
  "For the days where a session log still exists, the same hours were counted a second way, from "
  "the log rather than from the saved changes. The two agree to within 9%. A separate check: this "
  "method puts the app at 22,642 lines of code at the end of phase D, and the expo workbook's own "
  "independent count for 24 September is 22,300.")
r = block(r, "What is not counted here",
  "The research team's original software, which we use unchanged. And every hour spent away from "
  "the computer that built it: meetings, the poster, the two presentations and their review "
  "rounds, running the app on a Windows machine, taking screenshots, and the expo itself.")
r = block(r, "What this sheet covers",
  "Phases A–E only — 30 August to 25 September 2026, the Tech Expo work. Everything "
  "after that date is separate work and is tracked separately.")
r = block(r, "Credit",
  "The AI pipeline at the centre of the app, and the 100-request benchmark, are the work of "
  "Jesse Barkley, Rumi Loghmani and Amir Barati Farimani at Carnegie Mellon University "
  "(arXiv:2603.26512), used unchanged. Everything in this sheet is the application built around it.")
r += 1
lg = s4.cell(row=r, column=1, value="Colours")
lg.font = Font(ARIAL, size=10, bold=True)
lg.border = BOX
s4.cell(row=r, column=2, value="").border = BOX
r += 1
for label, fill, text, white in (
    ("Green", DONE, "The week the activity was done.", False),
    ("Navy", NAVY, "A milestone.", True),
    ("Purple", WORKF, "The phase, with its dates.", False),
    ("Peach", TASKF, "The project.", False)):
    c = s4.cell(row=r, column=1, value=label)
    c.fill = fill
    c.font = Font(ARIAL, size=9, bold=True, color="FFFFFF" if white else "000000")
    c.alignment = Alignment("center", "center")
    c.border = BOX
    b_ = s4.cell(row=r, column=2, value=text)
    b_.font = Font(ARIAL, size=9)
    b_.alignment = Alignment("left", "center", wrap_text=True)
    b_.border = BOX
    r += 1
block(r + 1, "Source",
  "The project's own change history, read on 15 October 2026. The same figures appear on the "
  "'Timeline & Effort' page of the project wiki.")

wb.calculation.fullCalcOnLoad = True
OUT = "/tmp/claude-0/xl2/Text2CAD-TechExpo-PhasesA-E-Tracker.xlsx"
wb.save(OUT)
print("saved", OUT)
