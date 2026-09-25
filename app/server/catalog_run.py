"""Serve a standard part from the catalogue instead of generating it.

When a request is unambiguously a standard part - "an M8x30 socket head cap
screw", "a 20 tooth spur gear module 2" - there is nothing for five agents to
work out.  The dimensions come from the standard, the geometry is exact, and
a language model can only introduce error.  So the catalogue answers directly.

Two things keep this honest.

*It is never a guess.*  ``router.select`` refuses anything ambiguous,
under-specified, or merely mentioning a standard part inside a custom one,
and it builds and verifies every candidate before returning it.  Whatever
reaches here is already known to be a sound solid.

*It is never disguised as pipeline output.*  The version is stamped
``source="catalog"`` and the UI badges it, because a part that no agent
produced must not be shown as evidence that the agents work.  It carries no
Judge verdict for the same reason - there was no Judge.

The part still runs through the same Executor the pipeline uses, so the
artifacts, the geometry JSON and the exports are identical to any other run;
only the route to the code differs.
"""

from __future__ import annotations

import json
import time

from app.catalog import router
from app.server import drawing, i18n
from app.catalog.router import Routed
from app.server.events import (
    PHASE_CATALOG, PHASE_VERSION, STATUS_INFO, STATUS_OK,
)
from app.server.instrument import InstrumentedExecutor, RunContext


def find(prompt: str) -> Routed | None:
    """The standard part this prompt asks for, already built and checked."""
    return router.select(prompt)


def find_options(prompt: str) -> router.Shortlist:
    """Several parts this prompt could mean, each already built and checked.

    Empty unless the request is one with more than one right answer - today
    that is a handlebar with no bend named. See ``router.options``.
    """
    return router.options(prompt)


def serve(ctx: RunContext, routed: Routed, work_dir,
          option: dict | None = None) -> dict:
    """Build the catalogue part into this job's artifacts and publish it.

    Returns a summary for the job record. Raises if the part will not execute
    here, which should be impossible - the router built it moments ago - but
    the caller falls back to the pipeline rather than trusting that.

    ``option`` is set when this part is one of several offered for the same
    request. It only labels the version - the part itself is built, checked
    and filed exactly as a single catalogue part is, because an option the
    person picks has to be the finished article rather than a preview.
    """
    part = routed.part
    ctx.source = "catalog"
    ctx.method = routed.source
    ctx.iteration = int(option["index"]) if option else 0

    ctx.emit(
        PHASE_CATALOG, STATUS_OK,
        i18n.t("catalog.served", ctx.lang, title=part.title),
        part_id=part.id, title=part.title, standard=part.standard,
        backend=routed.source, parameters=part.parameters,
        verified=routed.report.summary(), option=option,
    )

    started = time.time()
    executor = InstrumentedExecutor(output_dir=str(work_dir))
    result = executor.execute(part.code, name=f"part_iter{ctx.iteration}")
    if not result.success:
        raise RuntimeError(
            f"the catalogue part would not build here: {result.error}")

    geometry = result.geometry_json or {}
    version_dir = ctx.version_dir()
    # A catalogue part has no Judge verdict, so validation.json records what
    # was actually checked - the kernel, and the router's own verification -
    # rather than an empty report that reads like a Judge passed it.
    try:
        (version_dir / "validation.json").write_text(json.dumps({
            "source": "catalog",
            "part_id": part.id,
            "standard": part.standard,
            "backend": routed.source,
            "all_passed": True,
            "checks": [
                {"metric": "kernel_valid", "passed": True,
                 "message": "OCCT reports a valid watertight solid."},
                {"metric": "single_solid", "passed": True,
                 "message": f"{routed.report.num_solids} solid."},
                # Whatever this family knows to measure about itself. A
                # washer adds nothing; a bent tube adds the width it came
                # out at and the radius its tightest bend would need.
                *[{"metric": row["key"], "passed": row["passed"],
                   "message": f"{row['label']}: {row['actual']}"}
                  for row in getattr(routed.report, "measured", []) or []],
                {"metric": "llm_judge", "passed": None,
                 "message": "No Judge: this part was not generated."},
            ],
            "feedback_text": "",
        }, indent=2), encoding="utf-8")
    except OSError:
        pass

    version = {
        "iteration": ctx.iteration,
        "passed": True,
        "judge_passed": None,
        "judge_feedback": "",
        "feedback_text": "",
        "geometry": geometry,
        "has_render": (version_dir / "render.png").exists(),
        "source": "catalog",
        "method": routed.source,
        "instruction": "",
        "changes": [],
        # The same measured rows the agents' runs carry, so the Validation
        # panel draws them the same way: a number read off the solid, with
        # what was asked beside it.
        "spec": ({"checks": list(routed.report.measured)}
                 if getattr(routed.report, "measured", None) else None),
        "catalog": {
            "part_id": part.id,
            "title": part.title,
            "standard": part.standard,
            "backend": routed.source,
            "parameters": part.parameters,
        },
        # One of several offered for the same request, or absent. The
        # filmstrip reads this to label the card by what the part is rather
        # than by which iteration produced it - these are not iterations,
        # nothing was refined, they are four answers standing side by side.
        "option": option,
    }
    ctx.versions.append(version)
    ctx.emit(PHASE_VERSION, STATUS_OK, **version)

    # Start the drawing now rather than when someone asks for it. A catalogue
    # part arrives in a second or two, so the projection is the longest wait
    # left in the whole interaction - and it can be spent while the person is
    # still turning the part around.
    drawing.prebuild(version_dir, ctx.prompt, ctx.job_dir.name, ctx.iteration)
    ctx.emit(PHASE_CATALOG, STATUS_INFO,
             i18n.t("catalog.built", ctx.lang,
                    ms=f"{(time.time() - started) * 1000:.0f}"))
    return version


def serve_options(ctx: RunContext, shortlist: router.Shortlist,
                  work_dir) -> list[dict]:
    """Build every part on the shortlist and publish them side by side.

    A request with one right answer is served by ``serve``. This serves one
    with several: "a handlebar" is four bends, all of them correct, and the
    person picks by looking rather than by being handed whichever the
    catalogue would have guessed.

    Each one is a full version - its own code, STEP, STL, geometry and
    drawing - because the one that gets picked has to be finished, not a
    preview that then needs building. They are numbered as iterations
    because that is how the artifacts are filed, but nothing was iterated:
    they are four answers standing side by side, and the filmstrip labels
    them that way.

    Raises only if none of them will build here, which the caller treats the
    way it treats any other catalogue failure - by falling through to the
    pipeline.
    """
    published: list[dict] = []
    failures: list[str] = []
    total = len(shortlist.offered)
    for index, routed in enumerate(shortlist.offered):
        option = {
            "index": index,
            "count": total,
            "part_id": routed.part.id,
            "title": routed.part.title,
            # The words the filmstrip puts on the card. The title carries
            # the sizes as well, which is too long for a thumbnail.
            "label": routed.part.title.split(",")[0],
        }
        try:
            published.append(serve(ctx, routed, work_dir, option=option))
        except Exception as error:
            # One bend that will not build here is not a reason to lose the
            # other three. It is recorded and the rest are offered.
            failures.append(f"{routed.part.title}: {error}")

    if not published:
        raise RuntimeError(
            "none of the catalogue's options would build here: "
            + "; ".join(failures))

    # Renumber if any dropped out, so the cards read 1 of 3 rather than
    # 1, 2 and 4 of 4.
    for at, version in enumerate(published):
        version["option"]["index"] = at
        version["option"]["count"] = len(published)

    # The thumbnails are drawn to one scale across the set, so none of them
    # can be drawn until every option has been built. The cards are already
    # on screen by then - they went up as each bar finished - so each
    # version is published a second time carrying its silhouette. The
    # filmstrip keys on the iteration, so this fills the card in rather than
    # adding another.
    if _thumbnails(ctx, published):
        for version in published:
            ctx.emit(PHASE_VERSION, STATUS_OK, **version)

    ctx.emit(
        PHASE_CATALOG, STATUS_OK,
        i18n.t("catalog.options", ctx.lang, n=len(published)),
        options=[version["option"] for version in published],
        # Why the shortlist is shorter than it looks. A road bend squeezed
        # to 700 mm has no room left between its bends, and saying so is
        # more use than quietly offering two.
        declined=[{"title": title, "why": why}
                  for title, why in shortlist.declined] + [
            {"title": failure.split(":")[0], "why": failure}
            for failure in failures],
    )
    return published


def _thumbnails(ctx: RunContext, versions: list[dict]) -> bool:
    """A front elevation of each option, all to one scale, for the picker.

    Speculative like the drawing prebuild and swallowed the same way: the
    cards fall back to their labels if this does not come off, and a
    thumbnail is not worth failing a run over. True when at least one was
    drawn, which is when the versions are worth publishing again.
    """
    try:
        steps, dirs = [], []
        for version in versions:
            version_dir = ctx.version_dir(version["iteration"])
            step = version_dir / "model.step"
            if step.exists():
                steps.append(step)
                dirs.append(version_dir)
        if not steps:
            return False
        for version_dir, svg in zip(dirs, drawing.silhouettes(steps)):
            if svg:
                (version_dir / "option.svg").write_text(svg, encoding="utf-8")
        drawn = False
        for version in versions:
            version["has_option"] = (
                ctx.version_dir(version["iteration"]) / "option.svg").exists()
            drawn = drawn or version["has_option"]
        return drawn
    except Exception:
        return False
