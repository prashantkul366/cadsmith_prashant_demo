"""Draw every bend in the table to one scale, from its own geometry.

The custom trade sells handlebars off a chalkboard chart of silhouettes.
This is that chart, except each silhouette is projected from the solid the
kernel built, so the shape and the numbers under it cannot disagree.

    .venv/bin/python -m app.tools.handlebar_chart --out docs/handlebar
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import cadquery as cq  # noqa: E402

from app.catalog import handlebars, verify  # noqa: E402
from app.server import drawing  # noqa: E402

COLUMN, MARGIN, LABELS = 470.0, 26.0, 62.0
INK, DIM, ACCENT, PAPER = "#E8EAED", "#9AA4B2", "#FFBE44", "#12161C"


def profiles(work: Path) -> list[tuple]:
    """Each style, built and projected onto the front view."""
    found = []
    for name, bar in handlebars.BARS.items():
        solid, _ = verify.build(handlebars.code_for(**bar.dimensions()))
        step = work / f"{name}.step"
        cq.exporters.export(cq.Workplane(obj=solid), str(step))
        front = drawing._project(step)["FRONT"]  # noqa: SLF001
        radii = sorted({round(bend["r"], 1) for bend in front.get("bends", [])})
        found.append((bar, front, radii))
        print(f"  {name:16} R{radii[0] if radii else 0:g}")
    return found


def chart(found: list[tuple], columns: int = 2) -> str:
    widest = max(max(p[0] for line in front["visible"] for p in line)
                 - min(p[0] for line in front["visible"] for p in line)
                 for _, front, _ in found)
    scale = (COLUMN - 40.0) / widest

    def tall(front) -> float:
        vs = [p[1] for line in front["visible"] for p in line]
        return (max(vs) - min(vs)) * scale

    # Each band is as tall as the tallest bar in it. An ape hanger is four
    # times the height of a drag bar, and a fixed row height wrote one
    # straight over the other's label.
    bands = [max(tall(front) for _, front, _ in found[at:at + columns]) + LABELS
             for at in range(0, len(found), columns)]
    width = MARGIN * 2 + COLUMN * columns
    height = 76 + sum(bands) + MARGIN

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" '
           f'height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">',
           f'<rect width="{width:.0f}" height="{height:.0f}" fill="{PAPER}"/>',
           f'<text x="{MARGIN}" y="34" fill="#F5F5F5" '
           f'font-family="Segoe UI,Arial" font-size="19" font-weight="600">'
           f'Handlebar bends, all to one scale</text>',
           f'<text x="{MARGIN}" y="54" fill="#8A93A0" '
           f'font-family="Segoe UI,Arial" font-size="11">Each one projected '
           f'from the solid the kernel built from its published dimensions'
           f'</text>']

    top = 76.0
    for index in range(0, len(found), columns):
        band = bands[index // columns]
        for column, (bar, front, radii) in enumerate(found[index:index + columns]):
            left = MARGIN + column * COLUMN + 20
            floor = top + band - LABELS
            xs = [p[0] for line in front["visible"] for p in line]
            vs = [p[1] for line in front["visible"] for p in line]
            middle, base = (min(xs) + max(xs)) / 2.0, min(vs)
            for line in front["visible"]:
                points = " ".join(
                    f"{left + (x - middle) * scale + (COLUMN - 40) / 2:.1f},"
                    f"{floor - (v - base) * scale:.1f}" for x, v in line)
                out.append(f'<polyline points="{points}" fill="none" '
                           f'stroke="{INK}" stroke-width="1.1" '
                           f'stroke-linecap="round"/>')
            out.append(f'<text x="{left}" y="{floor + 26:.0f}" fill="{ACCENT}" '
                       f'font-family="Segoe UI,Arial" font-size="12.5" '
                       f'font-weight="600">{bar.title}</text>')
            detail = (f"{bar.width:g} wide · {bar.rise:g} rise · "
                      f"{bar.pullback:g} back · Ø{bar.tube_diameter:g}"
                      f"×{bar.wall_thickness:g}"
                      + (f" · R{radii[0]:g}" if radii else ""))
            out.append(f'<text x="{left}" y="{floor + 42:.0f}" fill="{DIM}" '
                       f'font-family="Consolas,monospace" font-size="10">'
                       f'{detail}</text>')
        top += band
    out.append("</svg>")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="docs/handlebar")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp(prefix="cadsmith_bars_"))
    svg = chart(profiles(work))
    (out / "styles.svg").write_text(svg, encoding="utf-8")
    print(f"wrote {out / 'styles.svg'}")
    try:
        import cairosvg
    except ImportError:
        print("install cairosvg for a PNG as well")
        return 0
    cairosvg.svg2png(url=str(out / "styles.svg"),
                     write_to=str(out / "styles.png"), output_width=1800)
    print(f"wrote {out / 'styles.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
