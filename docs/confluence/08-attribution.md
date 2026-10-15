# Attribution & Licensing

> **Read this before putting any of this project in front of people
> outside the team.** The agent pipeline at the centre of it is published
> academic work by someone else, used unmodified. That division is already
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
| The pipeline (`autofab/`) | Planner, Coder, Executor, Validator with vision Judge, Refiner; the two correction loops; retrieval over the CAD API | **Carnegie Mellon** — Barkley, Loghmani, Barati Farimani. arXiv:2603.26512. **Used unmodified** |
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

## The pipeline really is unmodified

`autofab/`, `scripts/`, `data/`, `run.py` and `requirements.txt` are
untouched, so the published benchmark numbers stay reproducible against
this checkout. Observability was added without editing any of it, in three
ways: the pipeline builds its executor and validator as instance
attributes, so instrumented subclasses can be swapped in after
construction; the agents are reached through the module object, so
wrapping its function attributes intercepts every model call; and a
context variable scopes both to the current job. With no context set, the
wrappers are pass-throughs — importing the application changes nothing for
the benchmark scripts.

This is worth knowing because it is what makes the attribution above
true and checkable, rather than a courtesy.

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

## Open item — the licence

**Still to confirm:** the licence on the upstream repository, and what it
permits for internal use, modification and any external demonstration.
The code is used unmodified and is credited, which is the right starting
position, but "credited" and "licensed for this use" are different things
and only the licence text settles the second one.

Owner: *to be assigned.* Until it is confirmed, treat the project as
internal-only and keep the attribution on every artefact that leaves the
team.
