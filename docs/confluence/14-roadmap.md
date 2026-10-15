# Roadmap | Next Steps

Phase 1 is done and was demonstrated. What follows is ordered by what
would change the most for an engineer here, not by what is easiest.

## Already in progress, separately

Two threads have started and are deliberately **not** part of this
project. They have their own scope and their own evidence:

- **CAD tool-calling instead of code generation.** Rather than having a
  model write a script, the model calls modelling operations directly, so
  the result is a live feature tree an engineer can edit by hand. Measured
  separately; its figures must not be quoted as evidence for this project.
- **NX.** Whether this can work inside Siemens NX, against NX's own
  kernel and feature tree, including the Teamcenter and corporate
  permission questions. Separate assessment.

## Next, on this project

**1. Make the drawing sufficient, not just true.** Every number on a sheet
is verified to be a real measurement of the solid. Nothing yet asks
whether the sheet carries *enough* to make the part from. That is the
single biggest gap between a drawing that passes our check and a drawing a
workshop would accept.

**2. Re-measure on a hosted model.** The 32-prompt evaluation ran against
a small local model on a laptop, and seven of those prompts never reached
it because the tunnel timed out. The same sweep on Bedrock would give a
figure that is about the system rather than about that setup.

**3. Agree success criteria.** A proposal with measured baselines is on
*Project Scope | Phase 1*. Until the bar is agreed, "better" has no
definition — particularly per tier, where the spread is wide: catalogue
7/7 and easy 5/7 against medium 1/6 and hard 0/3.

**4. Tolerances.** The sheet carries none, deliberately, because nothing
has specified any. Phase 2 needs somebody to decide what a default
general tolerance should be, or to let the Planner specify one and have it
measured like every other claim.

**5. Shop rates.** The cost model's defaults are starting values in an
editable file. One pass through `rates.toml` with somebody who knows the
real numbers turns the estimate from a comparison tool into something
quotable internally.

**6. Confirm the upstream licence.** See *Attribution & Licensing*. Until
it is confirmed, internal only.

## Further out

- **Assemblies** — multiple parts with mates and a BOM. A large step: the
  measured-check approach would have to extend to relationships between
  parts, not just dimensions within one.
- **Smaller models.** Whether a 4B-class model can drive the pipeline at
  all is untested, and it is the question that decides whether this can
  run entirely on an engineer's own machine with no data leaving it.
- **Drawing or sketch input**, so an existing drawing can be the starting
  point rather than a sentence.
- **A deployed service.** Phase 1 is one laptop serving `127.0.0.1`. Any
  multi-user deployment is a different conversation about data, access and
  review.
