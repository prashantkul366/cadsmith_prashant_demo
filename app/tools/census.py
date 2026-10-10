"""Which CadQuery operations the model actually reaches for, counted.

Before deciding whether to put a feature tree under this app, it is worth
knowing how wide the vocabulary would have to be.  A declarative feature
document - ordered, named, suppressible nodes instead of a Python script -
is only cheap if the model uses twenty operations.  If it uses two hundred,
the escape hatch for everything the vocabulary cannot express stops being a
detail and becomes the design.

Nobody has to guess: hundreds of scripts the model has already written are
sitting in ``app/runs``.  This parses them with ``ast`` and counts the
Workplane methods in every fluent chain, so the vocabulary can be read off
evidence rather than chosen and then argued about.

It is also a read-only feature tree in miniature.  The chain

    cq.Workplane("XY").box(50, 30, 20).faces(">Z").workplane().hole(8)

is a history: box, then a selection, then hole.  ``--tree`` prints that for
one script, which is what a tree view in the UI would show, and is the
cheapest possible answer to "would this be useful at all".

    python -m app.tools.census
    python -m app.tools.census --top 40
    python -m app.tools.census --tree app/runs/<job>/v0/code.py
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

#: Methods that select rather than build. They are the part of a chain a
#: feature IR has to express as a *query* rather than as an operation, and
#: they are where index-based selection would bite, so they are counted
#: apart from the operations.
SELECTORS = {
    "faces", "edges", "vertices", "solids", "shells", "wires",
    "workplane", "transformed", "rotate", "translate", "center",
    "end", "first", "last", "item", "all", "vals", "val", "size",
    "toPending", "tag", "_getTagged",
}

#: Not operations either: these start a chain or close a sketch.
STRUCTURAL = {"Workplane", "Assembly", "Sketch", "close", "consolidateWires"}


def chain_of(node: ast.AST) -> list[tuple[str, int]]:
    """Every method call in one fluent chain, in the order written."""
    calls: list[tuple[str, int]] = []
    current = node
    while isinstance(current, ast.Call):
        func = current.func
        if isinstance(func, ast.Attribute):
            calls.append((func.attr, len(current.args) + len(current.keywords)))
            current = func.value
        elif isinstance(func, ast.Name):
            calls.append((func.id, len(current.args) + len(current.keywords)))
            break
        else:
            break
        while isinstance(current, ast.Attribute):
            current = current.value
    return list(reversed(calls))


def read_script(path: Path) -> list[tuple[str, int]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return []
    found: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            # Only the outermost call of a chain; walking every node would
            # count a five-link chain five times over.
            parent_is_chain = False
            for outer in ast.walk(tree):
                if isinstance(outer, ast.Call) and outer is not node:
                    if isinstance(outer.func, ast.Attribute) \
                            and outer.func.value is node:
                        parent_is_chain = True
                        break
            if not parent_is_chain:
                found.extend(chain_of(node))
    return found


def describe(calls: list[tuple[str, int]]) -> list[str]:
    """One chain as a feature list, the way a tree view would show it."""
    lines: list[str] = []
    pending: list[str] = []
    for name, arity in calls:
        if name in STRUCTURAL:
            continue
        if name in SELECTORS:
            pending.append(name)
            continue
        where = f"  [after {' -> '.join(pending)}]" if pending else ""
        lines.append(f"{name}({arity} arg{'s' if arity != 1 else ''}){where}")
        pending = []
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", default="", help="directory of runs")
    parser.add_argument("--top", type=int, default=30)
    parser.add_argument("--tree", default="", help="print one script as a tree")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    if args.tree:
        path = Path(args.tree)
        print(f"\n{path}")
        for index, line in enumerate(describe(read_script(path)), 1):
            print(f"  {index:2}. {line}")
        return 0

    runs = Path(args.runs) if args.runs else \
        Path(__file__).resolve().parents[1] / "runs"
    scripts = sorted(runs.glob("*/v*/code.py"))
    if not scripts:
        print(f"no scripts under {runs}")
        return 2

    operations: Counter = Counter()
    selectors: Counter = Counter()
    per_script: list[int] = []
    for path in scripts:
        calls = read_script(path)
        distinct = {name for name, _ in calls
                    if name not in SELECTORS and name not in STRUCTURAL}
        per_script.append(len(distinct))
        for name, _ in calls:
            if name in STRUCTURAL:
                continue
            (selectors if name in SELECTORS else operations)[name] += 1

    print(f"\n{len(scripts)} script(s) under {runs}")
    print(f"{len(operations)} distinct building operations, "
          f"{len(selectors)} distinct selectors")
    if per_script:
        print(f"median script uses {sorted(per_script)[len(per_script) // 2]} "
              f"distinct operations")

    total = sum(operations.values()) or 1
    running = 0
    print(f"\n{'operation':<24} {'uses':>6} {'share':>7} {'cumulative':>11}")
    print("-" * 52)
    for name, count in operations.most_common(args.top):
        running += count
        print(f"{name:<24} {count:>6} {count / total:>6.1%} "
              f"{running / total:>10.1%}")

    # The number that decides the design: how few operations cover almost
    # everything the model writes.
    for target in (0.90, 0.95, 0.99):
        covered, seen = 0, 0
        for _, count in operations.most_common():
            covered += count
            seen += 1
            if covered / total >= target:
                break
        print(f"\n{seen} operations cover {target:.0%} of everything written")

    print(f"\nselectors: "
          + ", ".join(f"{n} ({c})" for n, c in selectors.most_common(12)))

    if args.out:
        Path(args.out).write_text(json.dumps({
            "scripts": len(scripts),
            "operations": dict(operations),
            "selectors": dict(selectors),
        }, indent=2), encoding="utf-8")
        print(f"\nwritten to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
