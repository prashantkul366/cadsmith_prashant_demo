"""The drawing sheet, checked against the conventions it claims to follow.

A sheet that looks like an engineering drawing and is not one is worse than
an obvious picture, so these check the claims rather than the appearance:
that the views are arranged in first angle, that they share one stated
preferred scale, and that the numbers on the sheet are the numbers the kernel
measured.

Runs the real kernel - it builds a part, exports it to STEP and projects it.

Run:  .venv/bin/python -m app.tests.test_drawing
"""

from __future__ import annotations

import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import cadquery as cq  # noqa: E402
import ezdxf  # noqa: E402

from app.server import drawing  # noqa: E402

SVG = "{http://www.w3.org/2000/svg}"

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}{(' - ' + detail) if detail else ''}")
    if not ok:
        failures.append(label)


# A plate with an off-centre through hole: three different overall lengths, so
# a view placed wrongly or a dimension read off the wrong axis shows up.
PLATE_X, PLATE_Y, PLATE_Z, HOLE_D = 60.0, 40.0, 12.0, 10.0


def build_step(into: Path) -> tuple[Path, dict]:
    solid = (cq.Workplane("XY")
             .box(PLATE_X, PLATE_Y, PLATE_Z, centered=(True, True, False))
             .faces(">Z").workplane().hole(HOLE_D))
    step = into / "model.step"
    cq.exporters.export(solid, str(step))
    shape = solid.val()
    box = shape.BoundingBox()
    return step, {
        "bounding_box": {"xlen": box.xlen, "ylen": box.ylen, "zlen": box.zlen},
        "volume": shape.Volume(),
        "is_valid": True,
    }


def texts(root) -> list[tuple[str, float, float]]:
    out = []
    for node in root.iter(SVG + "text"):
        body = "".join(node.itertext()).strip()
        if body:
            out.append((body, float(node.get("x", 0)), float(node.get("y", 0))))
    return out


def view_boxes(root) -> dict[str, tuple[float, float, float, float]]:
    """The drawn extent of each view, from the projected line work itself."""
    cells = {"FRONT": (0, 0), "LEFT": (1, 0), "TOP": (0, 1), "ISO": (1, 1)}
    boxes: dict[str, tuple[float, float, float, float]] = {}
    points: dict[str, list[tuple[float, float]]] = {n: [] for n in cells}
    for node in root.iter(SVG + "polyline"):
        for pair in (node.get("points") or "").split():
            x, y = (float(v) for v in pair.split(","))
            for name, (col, row) in cells.items():
                left = drawing.FRAME_L + col * drawing.CELL_W
                top = drawing.CELLS_T + row * drawing.CELL_H
                if (left <= x <= left + drawing.CELL_W
                        and top <= y <= top + drawing.CELL_H):
                    points[name].append((x, y))
                    break
    for name, found in points.items():
        if found:
            boxes[name] = (min(p[0] for p in found), min(p[1] for p in found),
                           max(p[0] for p in found), max(p[1] for p in found))
    return boxes


def centre(box) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="cadsmith_drawing_test_"))
    try:
        step, geometry = build_step(work)
        sheet = drawing.build_sheet(step, geometry, "a test plate",
                                    "JOB-TEST", 0)
        root = ET.fromstring(sheet)
        found = texts(root)
        labels = {body: (x, y) for body, x, y in found}
        words = [body for body, _, _ in found]

        print("\nThe sheet itself")
        check("it is an A3 sheet in millimetres",
              root.get("viewBox") == "0 0 420.0 297.0"
              and root.get("width", "").endswith("mm"),
              f'{root.get("width")} viewBox={root.get("viewBox")}')

        print("\nFirst angle (ISO 128-30 A.2)")
        for label in ("FRONT", "VIEW FROM ABOVE", "VIEW FROM LEFT", "ISOMETRIC"):
            check(f"{label} is on the sheet", label in labels)
        drawn = view_boxes(root)
        for name in ("FRONT", "TOP", "LEFT"):
            check(f"the {name} view has line work in it",
                  name in drawn, str(sorted(drawn)))
        if {"FRONT", "TOP", "LEFT"} <= set(drawn):
            front, above, left = drawn["FRONT"], drawn["TOP"], drawn["LEFT"]
            check("the view from above is placed underneath the front view",
                  above[1] > front[3],
                  f"top {above[1]:.0f} vs front bottom {front[3]:.0f}")
            check("the view from above lines up with the front view",
                  abs(centre(above)[0] - centre(front)[0]) < 0.5
                  and abs((above[2] - above[0]) - (front[2] - front[0])) < 0.5,
                  f"centre {centre(above)[0]:.1f} vs {centre(front)[0]:.1f}")
            check("the view from the left is placed on the right",
                  left[0] > front[2],
                  f"left edge {left[0]:.0f} vs front right {front[2]:.0f}")
            check("and lines up with the front view's height",
                  abs(centre(left)[1] - centre(front)[1]) < 0.5
                  and abs((left[3] - left[1]) - (front[3] - front[1])) < 0.5,
                  f"centre {centre(left)[1]:.1f} vs {centre(front)[1]:.1f}")

        print("\nOne scale, stated, and a preferred one")
        scale = next((w for w in words if re.fullmatch(r"\d+:\d+", w)), "")
        check("a scale is stated on the sheet", bool(scale), scale or "none")
        if scale:
            a, b = (float(n) for n in scale.split(":"))
            check("and it is an ISO 5455 preferred ratio",
                  any(abs(a / b - s) < 1e-9 for s in drawing.PREFERRED_SCALES),
                  scale)

        print("\nDrawn at the scale it says it is")
        if scale and "FRONT" in drawn:
            factor = float(scale.split(":")[0]) / float(scale.split(":")[1])
            width = drawn["FRONT"][2] - drawn["FRONT"][0]
            height = drawn["FRONT"][3] - drawn["FRONT"][1]
            check("the front view measures the part times the stated scale",
                  abs(width - PLATE_X * factor) < 0.5
                  and abs(height - PLATE_Z * factor) < 0.5,
                  f"{width:.1f} x {height:.1f} mm on the sheet, "
                  f"expected {PLATE_X * factor:g} x {PLATE_Z * factor:g}")
        if scale and "TOP" in drawn:
            factor = float(scale.split(":")[0]) / float(scale.split(":")[1])
            depth = drawn["TOP"][3] - drawn["TOP"][1]
            check("and so does the view from above",
                  abs(depth - PLATE_Y * factor) < 0.5,
                  f"{depth:.1f} mm, expected {PLATE_Y * factor:g}")

        print("\nThe numbers are the kernel's")
        for axis, value in (("x", PLATE_X), ("y", PLATE_Y), ("z", PLATE_Z)):
            check(f"the {axis} length is dimensioned as {value:g}",
                  f"{value:g}" in words,
                  ", ".join(w for w in words if re.fullmatch(r"[\d.]+", w)))
        check("the hole is called out by diameter",
              f"Ø{HOLE_D:g}" in words,
              ", ".join(w for w in words if w.startswith("Ø")) or "no Ø")
        check("the title block carries the measured size",
              any(f"{PLATE_X:g} x {PLATE_Y:g} x {PLATE_Z:g}" == w for w in words),
              next((w for w in words if " x " in w), "none"))

        print("\nLine work follows ISO 128-2")
        widths = {node.get("stroke-width") for node in root.iter()
                  if node.get("stroke-width")}
        check("two line widths in a 2:1 ratio",
              {str(drawing.W_THICK), str(drawing.W_THIN)} <= widths,
              ", ".join(sorted(widths)))
        dashes = [node.get("stroke-dasharray") for node in root.iter()
                  if node.get("stroke-dasharray")]
        check("hidden detail is dashed", any(d == "2.4,1.2" for d in dashes))
        check("circular features get a long-dash-dot centre line",
              any(d and d.count(",") == 3 for d in dashes),
              ", ".join(sorted(set(d for d in dashes if d))[:3]))

        print("\nThe title block says how to read the sheet")
        for field in ("LEGAL OWNER", "TITLE", "DRAWING No.", "DATE OF ISSUE",
                      "SCALE", "UNITS", "PROJECTION", "SHEET"):
            check(f"field: {field}", field in labels)
        check("units are declared in the notes",
              any("MILLIMETRES" in w for w in words))
        check("and no tolerance is claimed that nobody specified",
              any("NO TOLERANCES" in w for w in words))

        print("\nThe projection symbol is the first angle one")
        circles = [c for c in root.iter(SVG + "circle")]
        check("it is drawn as two concentric circles beside a trapezoid",
              len(circles) == 2
              and circles[0].get("cx") == circles[1].get("cx"),
              f"{len(circles)} circle(s)")
        if len(circles) == 2:
            # First angle places the view from the left on the right, so the
            # end view (the circles) sits to the right of the side view.
            trapezoid = next(
                (p for p in root.iter(SVG + "path")
                 if (p.get("d") or "").count("L") == 3
                 and (p.get("d") or "").endswith("Z")
                 and p.get("fill") == "none"), None)
            check("with the circles on the right of it", trapezoid is not None
                  and float(circles[0].get("cx"))
                  > max(float(v) for v in re.findall(
                      r"[ML](-?[\d.]+),", trapezoid.get("d"))),
                  "trapezoid then circles" if trapezoid is not None
                  else "no trapezoid found")
        print("\nThe same drawing as DXF")
        # The SVG is a picture of the drawing; the DXF is the drawing. Its
        # dimensions carry the geometry they measure, so this asks the file
        # what it measures rather than reading back a string.
        doc = drawing.build_dxf(step, geometry, "a test plate", "JOB-TEST", 0)
        model = doc.modelspace()
        dims = [e for e in model if e.dxftype() == "DIMENSION"]
        check("it carries real DIMENSION entities, not drawn lines",
              len(dims) == 4, f"{len(dims)} dimension(s)")
        measured = sorted(round(d.get_measurement(), 4) for d in dims)
        check("and they measure the part, not the sheet",
              measured == sorted([PLATE_X, PLATE_Y, PLATE_Z, HOLE_D]),
              f"{measured} vs {sorted([PLATE_X, PLATE_Y, PLATE_Z, HOLE_D])}")

        layers = {e.dxf.layer for e in model}
        check("line work is separated onto drawing-office layers",
              {"OUTLINE", "HIDDEN", "CENTRE", "DIMENSIONS", "FRAME"} <= layers,
              ", ".join(sorted(layers)))
        check("outlines are the thick line group and hidden detail the thin",
              doc.layers.get("OUTLINE").dxf.lineweight == drawing._LW_THICK
              and doc.layers.get("HIDDEN").dxf.lineweight == drawing._LW_THIN,
              f'{doc.layers.get("OUTLINE").dxf.lineweight} / '
              f'{doc.layers.get("HIDDEN").dxf.lineweight}')
        check("hidden and centre layers carry the right line types",
              doc.layers.get("HIDDEN").dxf.linetype.upper().startswith("DASHED")
              and doc.layers.get("CENTRE").dxf.linetype.upper().startswith("CENTER"),
              f'{doc.layers.get("HIDDEN").dxf.linetype} / '
              f'{doc.layers.get("CENTRE").dxf.linetype}')

        style = doc.dimstyles.get("ISO-129")
        check("the dimension style follows ISO 129-1",
              style.dxf.dimtxt == drawing.TEXT
              and style.dxf.dimtad == 1        # value above the line
              and style.dxf.dimtih == 0        # aligned, not forced horizontal
              and style.dxf.dimblk == "",      # closed filled arrowhead
              f"text {style.dxf.dimtxt}, above={style.dxf.dimtad}, "
              f"arrow={style.dxf.dimblk!r}")

        written = work / "drawing.dxf"
        doc.saveas(written)
        reopened = ezdxf.readfile(written)
        audit = reopened.audit()
        check("and it is a file another CAD system can open",
              not audit.errors,
              f"{written.stat().st_size} bytes, "
              f"{len(audit.errors)} error(s), {len(audit.fixes)} fix(es)")
        check("whose dimensions still measure the part when re-read",
              sorted(round(e.get_measurement(), 4)
                     for e in reopened.modelspace()
                     if e.dxftype() == "DIMENSION")
              == sorted([PLATE_X, PLATE_Y, PLATE_Z, HOLE_D]),
              str(sorted(round(e.get_measurement(), 4)
                         for e in reopened.modelspace()
                         if e.dxftype() == "DIMENSION")))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print("\n" + "=" * 60)
    if failures:
        print(f"{len(failures)} CHECK(S) FAILED:")
        for name in failures:
            print(f"   - {name}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
