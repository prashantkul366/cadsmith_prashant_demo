"""Save the drawing of every part this app has built, and check each one.

A sheet nobody looks at is not a drawing, so this writes them all out as
files with an index page that opens in a browser, each labelled with the
request it came from and whether every number on it is a measurement of
the solid it was drawn from.

The check is the point. A missing dimension is a gap somebody notices; a
number that measures nothing is a drawing that lies, and somebody
machines to it. So each sheet's numbers are read back off the plan and
matched against lengths derived from the projection independently of the
code that chose them - the bounding box, the circles and where they sit,
the pitch between any two like holes, the pitch circle of a ring of them,
the extent of every closed loop cut into the outline, and the depth of
every bore the kernel found.

Run:  .venv/bin/python -m app.tools.sheets [runs_dir] [out_dir]
"""

from __future__ import annotations

import html
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.server import drawing  # noqa: E402

try:                                     # noqa: SIM105
    from app.server import features      # noqa: E402
except ImportError:                      # the tool-calling road has no
    features = None                      # loop finder of its own yet

#: How close a printed number must be to a real length to be that length.
TOL = 0.05

#: A number in a piece of annotation. The same reading `features` does,
#: written again here on purpose: a tool that checks a sheet with the code
#: that drew it cannot find a fault in that code.
NUMBER = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)(?![\d.])(?!×)")


def printed(sheet: dict) -> list[float]:
    """Every number the sheet puts on the page."""
    out: list[float] = []
    for view in sheet.get("views", []):
        for thing in list(view.get("dimensions") or []) \
                + list(view.get("callouts") or []):
            if thing.get("measure") is not None:
                out.append(float(thing["measure"]))
            label = thing.get("label")
            if isinstance(label, str):
                out.extend(float(n) for n in NUMBER.findall(label))
    return out


def loops(lines: list) -> list:
    """Projected edges chained back into closed loops."""
    def end(point):
        return (round(point[0], 3), round(point[1], 3))

    ends: dict = {}
    for i, line in enumerate(lines):
        ends.setdefault(end(line[0]), []).append((i, False))
        ends.setdefault(end(line[-1]), []).append((i, True))
    used, found = set(), []
    for start in range(len(lines)):
        if start in used:
            continue
        chain = list(lines[start])
        used.add(start)
        while True:
            step = next(((i, r) for i, r in ends.get(end(chain[-1]), [])
                         if i not in used), None)
            if step is None:
                break
            i, reverse = step
            used.add(i)
            piece = lines[i][::-1] if reverse else lines[i]
            chain.extend(piece[1:])
            if end(chain[-1]) == end(chain[0]):
                break
        if len(chain) > 3 and end(chain[-1]) == end(chain[0]):
            found.append(chain)
    return found


def real_lengths(views: dict) -> set:
    """Every length this part has that a sheet may legitimately print."""
    real: set = set()
    for name in ("FRONT", "TOP", "LEFT", "SECTION"):
        view = views.get(name)
        if not view:
            continue
        umin, vmin, umax, vmax = view["bbox"]
        real.add(round(umax - umin, 2))
        real.add(round(vmax - vmin, 2))
        circles = view.get("circles") or []
        for circle in circles:
            real.add(round(circle["r"], 2))
            real.add(round(circle["r"] * 2, 2))
            # Where it sits, from either datum edge.
            real.add(round(circle["u"] - umin, 2))
            real.add(round(umax - circle["u"], 2))
            real.add(round(circle["v"] - vmin, 2))
            real.add(round(vmax - circle["v"], 2))
        for bend in view.get("bends") or []:
            real.add(round(bend["r"], 2))
        for group in by_radius(circles).values():
            real |= spacings([c["u"] for c in group])
            real |= spacings([c["v"] for c in group])
            # A ring of like holes is dimensioned by its pitch circle, and
            # the PCD is a length no edge of the part carries.
            if len(group) > 1:
                cu = sum(c["u"] for c in group) / len(group)
                cv = sum(c["v"] for c in group) / len(group)
                for circle in group:
                    across = 2.0 * math.hypot(circle["u"] - cu,
                                              circle["v"] - cv)
                    real.add(round(across, 2))
                    real.add(round(across / 2.0, 2))
        if features is not None:
            cut = features.cutouts(view)
            for one in cut:
                real.add(round(one["w"], 2))
                real.add(round(one["h"], 2))
            real |= spacings([one["u"] for one in cut])
            real |= spacings([one["v"] for one in cut])
        for loop in loops(view.get("visible") or []):
            us = [p[0] for p in loop]
            vs = [p[1] for p in loop]
            real.add(round(max(us) - min(us), 2))
            real.add(round(max(vs) - min(vs), 2))
    for cylinder in views.get("__cylinders__") or []:
        real.add(round(float(cylinder["r"]), 2))
        real.add(round(float(cylinder["r"]) * 2, 2))
        real.add(round(float(cylinder["depth"]), 2))
    return real


def by_radius(circles: list) -> dict:
    groups: dict = {}
    for circle in circles:
        groups.setdefault(round(circle["r"], 2), []).append(circle)
    return groups


def spacings(values: list) -> set:
    """The distance between any two of these, not only neighbours.

    A row of three where the middle one differs is dimensioned across the
    outer pair, and that span is 20 on a part whose neighbours are 10
    apart.
    """
    seen = sorted({round(v, 3) for v in values})
    return {round(b - a, 2) for i, a in enumerate(seen) for b in seen[i + 1:]}


def untraceable(sheet: dict, views: dict) -> list[float]:
    """Numbers on the page that are not a length of the part."""
    real = real_lengths(views)
    return sorted({round(n, 2) for n in printed(sheet)
                   if not any(abs(n - r) <= max(TOL, abs(n) * 0.004)
                              for r in real)})


def latest(runs: Path) -> list[tuple[str, Path, str]]:
    """The last version of each run, with the request that made it."""
    out = []
    for meta_path in sorted(runs.glob("*/meta.json")):
        versions = sorted(meta_path.parent.glob("v*/model.step"))
        if not versions:
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        out.append((meta_path.parent.name, versions[-1],
                    str(meta.get("prompt") or "")))
    return out


def main() -> int:
    runs = Path(sys.argv[1] if len(sys.argv) > 1 else "app/runs")
    into = Path(sys.argv[2] if len(sys.argv) > 2 else "app/runs/_sheets")
    into.mkdir(parents=True, exist_ok=True)
    rows = []
    for run_id, step, prompt in latest(runs):
        try:
            geometry = json.loads(
                (step.parent / "geometry.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            geometry = {}
        try:
            views = drawing._project(step)            # noqa: SLF001
            # The threads a request asked for, where this branch reads
            # them: a hole drilled 6.8 for an M8 is called out as the M8.
            threads = getattr(drawing, "_threads", None)
            sheet = drawing.plan_sheet(
                views, threads(prompt) if threads else None)
            svg = drawing.build_sheet(step, geometry, prompt, run_id,
                                      int(step.parent.name.lstrip("v") or 0))
        except Exception as error:                    # noqa: BLE001
            rows.append({"id": run_id, "prompt": prompt, "file": None,
                         "why": f"{type(error).__name__}: {error}"})
            print(f"  {run_id}  NO SHEET  {rows[-1]['why'][:70]}", flush=True)
            continue
        name = f"{run_id}.svg"
        (into / name).write_text(svg, encoding="utf-8")
        odd = untraceable(sheet, views)
        rows.append({"id": run_id, "prompt": prompt, "file": name,
                     "numbers": len(printed(sheet)), "odd": odd,
                     "scale": sheet["scale"]})
        print(f"  {run_id}  {len(printed(sheet)):>3d} numbers  "
              f"{'odd=' + str(odd) if odd else 'all traceable'}", flush=True)

    (into / "sheets.json").write_text(
        json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    (into / "index.html").write_text(index(rows), encoding="utf-8")
    drawn = [r for r in rows if r.get("file")]
    clean = [r for r in drawn if not r["odd"]]
    print(f"\n{len(drawn)} sheets written to {into}")
    print(f"{len(clean)} of {len(drawn)} have every number traceable to the "
          f"solid; {sum(r['numbers'] for r in drawn)} numbers in all")
    return 0


def index(rows: list) -> str:
    """One page listing every sheet, worst first."""
    def card(row):
        title = html.escape((row["prompt"] or row["id"])[:150])
        if not row.get("file"):
            return (f'<article class="bad"><h2>{html.escape(row["id"])}</h2>'
                    f'<p>{title}</p><p class="why">no sheet: '
                    f'{html.escape(row.get("why") or "")}</p></article>')
        state = ("every number traceable" if not row["odd"]
                 else "not a length of the part: "
                      + ", ".join(f"{n:g}" for n in row["odd"]))
        return (f'<article class="{"ok" if not row["odd"] else "odd"}">'
                f'<h2>{html.escape(row["id"])}</h2><p>{title}</p>'
                f'<p class="why">{row["numbers"]} numbers, 1:'
                f'{1 / row["scale"]:g} &mdash; {html.escape(state)}</p>'
                f'<a href="{row["file"]}"><img src="{row["file"]}" '
                f'alt="sheet"></a></article>')

    order = sorted(rows, key=lambda r: (bool(r.get("file")),
                                        not r.get("odd")))
    return (
        "<!doctype html><meta charset='utf-8'>"
        "<title>Drawings</title>"
        "<style>body{font:14px/1.5 system-ui;margin:0;padding:24px;"
        "background:#f6f6f4;color:#111}h1{font-size:20px}"
        "article{background:#fff;border:1px solid #ddd;border-radius:6px;"
        "padding:12px;margin:0 0 18px}h2{font:600 13px/1.4 ui-monospace,"
        "monospace;margin:0 0 4px}p{margin:0 0 6px}"
        ".why{color:#555;font-size:12px}.odd .why{color:#a30000}"
        ".bad{border-color:#a30000}img{width:100%;border:1px solid #eee}"
        "</style><h1>Every sheet this app has drawn</h1>"
        + "".join(card(r) for r in order))


if __name__ == "__main__":
    sys.exit(main())
