"""Where the dimensions sit, not only what they say.

The companion to `sheets`, which asks whether every number is true. This
asks whether anybody can read them. Both questions have to be answered
before a drawing goes to an engineer, and they fail independently: a
sheet where every number is a real measurement of the part can still be
unusable because two of them are written on top of each other.

Run:  .venv/bin/python -m app.tools.placement [root] [out.json] [runs]


A sheet can be numerically perfect and still unreadable: lines crossing
each other, a value sitting on an outline, a ladder with the long
dimension nearest the view.  ISO 129-1 is specific about all three, so
each one is countable.

Self-contained for the same reason the number audit is: it re-derives
every line and text box from the plan rather than asking the renderer.
"""
import collections, json, pathlib, sys
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else ".")
from app.server import drawing
from app.tools import sheets

FRAME = (20.0, 10.0, 410.0, 287.0)       # ISO 5457 frame on A3 landscape
TEXT, CHAR = 3.5, 2.1                    # ISO 3098 height, and a digit's width
EPS = 0.25


def segment(dim):
    """The dimension line itself, as the renderer draws it."""
    (x1, y1), (x2, y2) = dim["p1"], dim["p2"]
    off = dim["offset"]
    if dim["vertical"]:
        return (x1 + off, y1, x2 + off, y2)
    return (x1, y1 + off, x2, y2 + off)


def text_box(dim, label):
    ax, ay, bx, by = segment(dim)
    mx, my = (ax + bx) / 2.0, (ay + by) / 2.0
    half = max(len(label), 1) * CHAR / 2.0
    if dim["vertical"]:                  # rotated to read from the right
        return (mx - TEXT, my - half, mx + TEXT / 2.0, my + half)
    return (mx - half, my - TEXT - 1.4, mx + half, my - 1.4)


def crosses(a, b):
    """Do two axis-aligned dimension lines cross, rather than meet?"""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    a_horiz, b_horiz = abs(ay1 - ay2) < EPS, abs(by1 - by2) < EPS
    if a_horiz == b_horiz:               # parallel: only overlap matters
        if a_horiz and abs(ay1 - by1) < EPS:
            return (min(ax1, ax2) < max(bx1, bx2) - EPS
                    and min(bx1, bx2) < max(ax1, ax2) - EPS)
        if not a_horiz and abs(ax1 - bx1) < EPS:
            return (min(ay1, ay2) < max(by1, by2) - EPS
                    and min(by1, by2) < max(ay1, ay2) - EPS)
        return False
    h, v = (a, b) if a_horiz else (b, a)
    hx1, hy, hx2, _ = h[0], h[1], h[2], h[3]
    vx, vy1, _, vy2 = v[0], v[1], v[2], v[3]
    return (min(hx1, hx2) + EPS < vx < max(hx1, hx2) - EPS
            and min(vy1, vy2) + EPS < hy < max(vy1, vy2) - EPS)


def overlap(a, b):
    return (a[0] < b[2] - EPS and b[0] < a[2] - EPS
            and a[1] < b[3] - EPS and b[1] < a[3] - EPS)


def inside(box, frame=FRAME):
    return (box[0] >= frame[0] - EPS and box[1] >= frame[1] - EPS
            and box[2] <= frame[2] + EPS and box[3] <= frame[3] + EPS)


def label_of(dim):
    return dim.get("label") or f"{dim['measure']:g}"


def judge(sheet):
    """Every placement fault on one sheet, by kind."""
    faults = collections.Counter()
    for view in sheet.get("views", []):
        dims = list(view.get("dimensions") or [])
        if not dims:
            continue
        lines = [segment(d) for d in dims]
        boxes = [text_box(d, label_of(d)) for d in dims]
        left, top, right, bottom = view["box"]
        outline = (min(left, right), min(top, bottom),
                   max(left, right), max(top, bottom))
        for i, line in enumerate(lines):
            for other in lines[i + 1:]:
                if crosses(line, other):
                    faults["line crosses line"] += 1
            # ISO 129-1: dimension lines are drawn outside the outline.
            box = (min(line[0], line[2]), min(line[1], line[3]),
                   max(line[0], line[2]), max(line[1], line[3]))
            if overlap(box, outline):
                faults["line over the view"] += 1
            if not inside(box):
                faults["line off the frame"] += 1
        for i, box in enumerate(boxes):
            for other in boxes[i + 1:]:
                if overlap(box, other):
                    faults["value over a value"] += 1
            for call in view.get("callouts") or []:
                ex, ey = call["elbow"]
                shoulder = call["shoulder"]
                text = call.get("label") or ""
                w = max(len(text), 1) * CHAR
                cbox = ((ex + shoulder, ey - TEXT - 1.6,
                         ex + shoulder + w, ey - 1.6) if shoulder > 0
                        else (ex + shoulder - w, ey - TEXT - 1.6,
                              ex + shoulder, ey - 1.6))
                if overlap(box, cbox):
                    faults["value over a leader"] += 1
            if not inside(box):
                faults["value off the frame"] += 1
        # ISO 129-1 4.3: shortest dimension nearest the view, so that the
        # extension lines of the long ones do not cross the short ones.
        # One ladder is the dimensions stacked off one baseline, so they
        # are grouped by the edge they are measured from rather than by
        # direction alone - a cut-out's width under its own corner is not
        # a rung of the overall dimension's ladder.
        ladders = collections.defaultdict(list)
        for d in dims:
            base = round(d["p1"][0] if d["vertical"] else d["p1"][1], 1)
            ladders[(d["vertical"], base)].append(d)
        for rungs in ladders.values():
            if len(rungs) < 2:
                continue
            rungs.sort(key=lambda d: abs(d["offset"]))
            sizes = [d["measure"] for d in rungs]
            if any(b < a - EPS for a, b in zip(sizes, sizes[1:])):
                faults["ladder out of order"] += 1
    return faults


def main() -> int:
    """Lay every part out and count what cannot be read."""
    rows, totals = [], collections.Counter()
    WHERE = pathlib.Path(sys.argv[3] if len(sys.argv) > 3 else "app/runs")
    # The same rule `sheets` uses for what there is to draw, imported rather
    # than written again: two tools that disagree about which files are parts
    # produce two reports nobody can line up.
    for name, step, prompt in (sheets.latest(WHERE)
                               if WHERE.is_dir() and any(WHERE.glob("*/meta.json"))
                               else sheets.solids(WHERE)):
        try:
            threads = getattr(drawing, "_threads", None)
            sheet = drawing.plan_sheet(drawing._project(step),
                                       threads(prompt) if threads else None)
        except Exception as exc:
            rows.append({"step": str(step), "built": False,
                         "why": f"{type(exc).__name__}: {exc}"})
            continue
        faults = judge(sheet)
        totals.update(faults)
        rows.append({"step": name, "built": True, "faults": dict(faults)})

    built = [r for r in rows if r.get("built")]
    clean = [r for r in built if not r["faults"]]
    print(f"{len(built)} sheets laid out, {len(clean)} with no placement fault "
          f"({100 * len(clean) // max(len(built), 1)}%)")
    print(f"{sum(totals.values())} faults in all\n")
    for kind, n in totals.most_common():
        on = sum(1 for r in built if r["faults"].get(kind))
        print(f"  {n:>5d}  {kind:24s} on {on:>3d} sheets")
    print()
    worst = sorted(built, key=lambda r: -sum(r["faults"].values()))[:6]
    for r in worst:
        if sum(r["faults"].values()):
            print(f"  {sum(r['faults'].values()):>3d}: {r['step'][:24]:24s} "
                  f"{r['faults']}")
    json.dump(rows, open(sys.argv[2] if len(sys.argv) > 2
                         else "placement.json", "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
