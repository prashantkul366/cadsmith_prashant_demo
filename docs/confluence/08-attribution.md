# Attribution & Licensing

> **Read this before putting any of this project in front of people
> outside the team.** The agent pipeline at the centre of it is published
> academic work by someone else, with local modifications. That division is already
> stated on the stand, in the deck and in the repository. This page is so
> it is also stated here, which is where somebody from another division or
> from legal will look first.

## The citation

> Barkley, J., Loghmani, R., & Barati Farimani, A. **CADSmith: Multi-Agent
> CAD Generation with Programmatic Geometric Validation.**
> arXiv:2603.26512. Carnegie Mellon University.

## Who did what

| Component | What it is | Whose work |
|---|---|---|
| The pipeline (`autofab/`) | Planner, Coder, Executor, Validator with vision Judge, Refiner; the two correction loops; retrieval over the CAD API | **Carnegie Mellon** — Barkley, Loghmani, Barati Farimani. arXiv:2603.26512. **With local modifications — see below** |
| The benchmark (`data/`) | 100 hand-written prompts in three tiers, with hand-checked reference scripts | **Carnegie Mellon**, same authors |
| Published results | Execution rate, Chamfer Distance, F1, volumetric IoU | **Carnegie Mellon**, measured on their benchmark |
| The web application (`app/`) | Browser interface, job server, live reasoning stream, iteration filmstrip, run history, exports | **This work** |
| Standard-parts catalogue | 18 families built to published standards and served exactly with no model call, plus the router that refuses ambiguous requests | **This work** |
| Measured specification checks | The built solid measured for what the plan claimed; a shortfall blocks the version whatever the vision Judge said | **This work** |
| Engineering drawings | A3 sheet, four projected views, dimensions, title block, DXF export | **This work** |
| Parametric editing | Sliders over the generated script's own parameters; kernel rebuild in about a second with no model call | **This work** |
| Manufacturing cost estimate | Stock and operations read off the geometry, with editable rates | **This work** |
| Spend ceiling and instrumentation | Per-run token budget, per-agent spend, full event log, replay | **This work** |
| English and Japanese interface | Including Japanese parameter edits and Japanese requests for standard parts, both with no model call | **This work** |
| Amazon Bedrock support | Claude on Bedrock alongside the Anthropic, OpenAI-compatible and local-model paths | **This work** |

## What we changed in the pipeline, and what we did not

**An earlier version of this page said the pipeline was unmodified. That was
wrong**, and the same wording is on the stand, in the deck and on the expo
workbook's Attribution sheet, where it still needs correcting. Three commits
changed `autofab/`:

| Commit | What it changed |
|---|---|
| `9745b29` | Read and write text as UTF-8 instead of the locale codec |
| `b7903c8` | Material and tolerance carried in the spec; a result may be an assembly |
| `c467040` | The request's own numbers held fixed; API keys no longer passed to generated code |

About 315 lines added and 56 removed, across `agents.py`, `executor.py` and
`pipeline.py`. `scripts/`, `data/`, `run.py` and `requirements.txt` **are**
untouched.

**The consequence that matters:** the published benchmark numbers can no longer
be described as reproducible against this checkout. Quote them from the paper,
naming the authors' repository as their source — which the Evidence page
already does — or re-run them here and report our own.

The design of the application layer does still hold: observability was added
without editing the pipeline, by swapping instrumented subclasses in after
construction, wrapping the agents module's function attributes, and scoping
both to the current job with a context variable. With no context set the
wrappers are pass-throughs. The three commits above sit underneath that, and
are separate from it.

## If somebody asks what is actually new here

Answer it directly, in this order. It is a fair question and the honest
answer is a strong one:

> The multi-agent pipeline is Carnegie Mellon's published work and we have
> not changed it. What we built is everything around it: the application,
> the standard-parts catalogue, the measured checks that let the kernel
> overrule the vision model, the engineering drawings, the cost estimate,
> the spend ceiling and the bilingual interface. The research proves the
> loop works; we made it something an engineer here can use, in Japanese,
> and that ends in a STEP file and a drawing.

## The licence — answered, and it is a problem

This was an open item. It has been checked, and the answer is the awkward
one: **the authors' repository, `jabarkle/CADSmith`, carries no licence
file at all.** Its README offers a citation and nothing else.

No licence means **all rights reserved** by default. We have attribution,
and attribution is not permission. For a research demonstration that
rarely matters; for anything Yamaha adopts it is the first thing an IP
review stops on — and we have modified the code, which is one of the
rights a licence would have had to grant.

**The fix is cheap and has a lead time, so start it now:** email the
authors and ask them to add a licence (MIT or Apache-2.0), or to confirm
in writing that internal evaluation use at Yamaha is permitted. Academic
authors almost always agree, and a one-line reply is enough to unblock it.

Until that reply exists, treat the project as internal-only, keep the
attribution on every artefact that leaves the team, and do not put it in
front of anyone outside Yamaha.

One more correction: this page and the repository README both named
`Ashutosh-Chauhan3025/CADSmith` as the upstream repository. That is a copy
made by our own team in August, with none of the authors' history. The
real upstream is `jabarkle/CADSmith`.

Full detail, including the Siemens licensing and AWS data-residency
findings, is in `docs/compliance.md` on the NX branch.

