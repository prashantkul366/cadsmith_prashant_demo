# How much compliance does this actually need?

Two questions were asked: what NX integration requires, and what YMC
compliance requires. Short answer first, then the evidence.

**The technical compliance burden is light.** The tool installs nothing,
needs no administrator rights, opens no port, and runs as the engineer
inside their own NX session. Most of what corporate IT normally asks
about does not apply.

**The contractual and IP burden is where the work is**, and one item is
a hard gate that is not met today: the research code this is built on
carries no licence at all.

| | Burden | Why |
|---|---|---|
| NX — technical / IT | **Low** | A Python journal. No installer, no service, no admin, no inbound port. |
| NX — Siemens licensing | **Medium** | Nothing blocks a journal from running, but Siemens' stated position is that authoring and distributing Python NX Open code needs a licence feature. Not technically enforced, which is exactly why it shows up at an audit. |
| Teamcenter | **None, for now** | The pilot deliberately touches no PLM. That single decision removes the heaviest compliance item on the list. |
| Research-code licence | **HARD GATE — unmet** | The authors' repository has no licence. Default is all rights reserved. |
| Where design data goes | **Medium** | Decidable by configuration. A local model sends nothing anywhere. |
| AI governance | **Medium** | Yamaha will have a generative-AI policy; this has to be registered under it. |
| Change control on production parts | **Medium** | It edits real CAD. Needs a preview step and a copies-only rule first. |
| Export control | **Low** | NX is the controlled item, not our journal. |
| Personal data | **Negligible** | The tool handles none. |

---

## Four things found while checking this

These came out of verifying the licensing question and are more urgent
than the compliance question itself.

### 1. A `.env` file is committed to a public GitHub repository

`Ashutosh-Chauhan3025/cadsmith` is public and `.env` is tracked at its
root, in the commit history since 27 Aug 2026. **I did not open it** —
whatever is in it should be treated as exposed.

**Do today:** rotate every credential that file has ever held — AWS keys,
any model-provider key — then remove it from the repository and from its
history, or make the repository private. Rotating is the part that
matters; deleting the file does not un-publish it.

### 2. The research code has no licence

Neither the authors' repository, `jabarkle/CADSmith`, nor the copy at
`Ashutosh-Chauhan3025/cadsmith` contains a licence file. The authors'
README offers a citation and nothing else.

No licence means **all rights reserved** by default. Citing the paper is
attribution, and attribution is not permission. For a research
demonstration this rarely matters; for a Yamaha deployment it is the
first thing an IP review will stop on.

**This is cheap to fix and should be done now, because it has a lead
time.** Email the authors and ask them to add a licence — MIT or
Apache-2.0 — or to give written permission for internal evaluation use at
Yamaha. Academic authors almost always say yes, and a one-line reply in
writing is enough to unblock the pilot. Suggested wording:

> We are evaluating CADSmith internally at Yamaha Motor and have built an
> application around your pipeline, with full attribution to your paper.
> Your repository does not carry a licence file. Would you be willing to
> add one (MIT or Apache-2.0), or to confirm in writing that internal
> evaluation use is permitted?

### 3. "The pipeline is used unmodified" is not true

This claim is in the repository README, in `app/README.md`, on the expo
workbook's Attribution sheet, in the deck, on the stand, and on the
Confluence attribution page. It is wrong, and it was wrong because of
three commits made here:

| Commit | What it changed in `autofab/` |
|---|---|
| `9745b29` | Read and write text as UTF-8 instead of the locale codec |
| `b7903c8` | Material and tolerance carried in the spec; a result may be an assembly |
| `c467040` | The request's own numbers held fixed; API keys no longer passed to generated code |

About 315 lines added and 56 removed across `agents.py`, `executor.py`
and `pipeline.py`.

Two consequences. The attribution wording has to change everywhere it
appears — "built around the CADSmith pipeline, with local modifications"
rather than "unmodified". And **the published benchmark numbers can no
longer be called reproducible against this checkout** without re-running
them; quote them from the paper, with the authors' repository named, or
re-run and report our own.

The READMEs in this repository are corrected. The expo material and the
Confluence page still need it.

### 4. The README credited the wrong repository

It pointed at `Ashutosh-Chauhan3025/CADSmith` as "the upstream
repository". That repository is a copy made by our own team on 26 Aug
2026 — fourteen commits, all from two people here, with no history from
the authors. The real upstream, and the one this repository is actually
forked from, is `jabarkle/CADSmith`. Corrected.

---

## Part 1 — NX integration

### What IT will care about, and why it is light

Everything here was already established in `nx-plugin.md` and holds:

- A Python journal run from **File → Execute → NX Open**. No installer,
  no Windows service, no driver, no registry change.
- **No administrator rights.**
- **No inbound port.** Nothing listens on an external interface.
- Runs **as the engineer, inside their NX session** — it can do what they
  can do and no more.
- **It never saves.** The engineer saves, or does not.
- Every change is a single NX expression edit, which NX's own undo
  reverses, and an undo mark is set before each one.

The one item that usually needs a real conversation is **endpoint
protection**: a CAD application making outbound HTTP can look unusual to
an EDR agent. Raise it before the install, not after the alert.

### Siemens licensing — corrected

An earlier version of `nx-feasibility.md` framed this as signed versus
unsigned applications needing a per-seat author licence. **That framing
is wrong for what we are shipping**, because a journal is not a compiled
application.

| | What applies |
|---|---|
| **Running** a Python journal | No technical barrier. Community sources, including a Siemens employee, state that a Gateway licence can execute a Python custom program, provided the module licences its operations need are present. |
| **Authoring and distributing** Python NX Open code | Siemens' stated position is that the legal conditions still apply even though nothing enforces them technically: the Python Author feature (NX30115) or the Toolkits bundle (NX30106). |
| **Signing** | Relevant to compiled applications — a signed DLL runs on an execute licence, an unsigned one needs Author at runtime. **Not applicable to a journal.** |

The important shape of this: **it will run whether or not the licence is
held, and that is the risk.** An unlicensed-authoring finding surfaces at
a Siemens licence audit, not at install time, and Yamaha is exactly the
size of customer that gets audited.

Ask the Siemens account manager, verbatim:

> We are writing NX Open code in Python as journals, for internal use at
> Yamaha, and distributing them to a handful of our own engineers. (a)
> Does that require the Python Author feature (NX30115) or the Toolkits
> bundle (NX30106), or is a Gateway/execute licence sufficient for both
> writing and running them? (b) Does distributing journals internally
> count as distribution under our agreement? (c) Which module licences
> must a seat hold for a journal that edits expressions and suppresses
> features?

Treat the table above as what to check with them, not as the answer.
These are community sources, some of them old, and only Siemens and your
licence file settle it.

### Teamcenter — the reason the burden is low

Out of scope, deliberately. The plugin changes only what the engineer has
**already checked out and open**. It does not check out, does not check
in, creates no revisions; the engineer saves through Teamcenter exactly
as they do now.

That keeps every PLM rule intact because the plugin never touches PLM —
and it removes what would otherwise be the single heaviest compliance
item, since a PLM integration pulls in records retention, audit trail,
revision governance and change approval all at once.

Keep it that way until everything in the list at the end is done. When
Teamcenter integration does come, it is ITK, the SOA services or the
Active Workspace REST layer, it needs their release and their business
rules, and it is **a separate approval, not an extension of this one**.

### Export control

NX is the export-controlled item, and that control already applies to the
seat the engineer uses. A journal that drives it does not change its
classification. Our own code is a few hundred lines of ordinary Python
with no cryptography beyond an HTTPS client. Worth a line in the
submission; not worth a project.

---

## Part 2 — YMC compliance

I cannot tell you what Yamaha's policies permit. I have not seen them,
and nobody outside your IT, legal and export-control functions can answer
it. What follows is what this system actually does, so the questions can
be answered against facts.

### What leaves the machine

| | |
|---|---|
| The part geometry | **Never leaves.** The solid stays in NX. |
| The feature tree | Names, numbers and feature types — sent to whichever model is configured. |
| The prompt | Written by the engineer; will contain part names, project names and intent. |
| Anything else | Nothing. |

**With a local model — Ollama, LM Studio, vLLM — nothing leaves the
machine at all.** That is the configuration to take to a confidentiality
review, and it is already supported.

Be straight about the other case rather than quiet: `p7 (Simple
Hole(12) Diameter) = 13` together with a prompt saying "the exhaust
bracket" **is design information**. If a hosted model is used, that is a
deliberate decision to send design data to a third party, and it should
be written down and approved, not inherited from a config file.

### If Bedrock is used, three facts and one trap

AWS states that Bedrock does not use customer inputs to train foundation
models and does not share them with model providers; Anthropic's Bedrock
terms likewise state it may not train on customer content from the
service. Content is encrypted in transit and at rest, in the Region
where Bedrock is used.

**The trap is the model id, and it is one I introduced.** I recommended a
geography-prefixed inference profile (`us.anthropic...`) as the fix when
a plain model id returns 404. AWS's own documentation is explicit that
with **cross-region inference, input prompts and output results may move
outside the source Region** — the geographic profile keeps data within a
geography, and the global profile has no geographic restriction at all.
Only **in-region inference** keeps requests inside the Region you specify,
and AWS names that as the option to use where regulations require
single-Region processing.

So: if YMC requires design data to stay in a given jurisdiction — Japan,
or India for YMSLI — **a `us.` or global inference profile breaks that
requirement**, silently, while working perfectly. Use an in-region model
id, in a Region that is approved, and record which one. This is a
one-line configuration decision with a compliance consequence, and it
belongs in the submission.

### Generative-AI governance

Any manufacturer of this size now has a policy covering what may be sent
to an AI service, which services are approved, and who signs off. This
tool has to be registered under it rather than run beside it. Three
questions to put to whoever owns that policy:

1. Is AWS Bedrock in the approved-services list, and for what data
   classification?
2. Under what classification does a CAD feature tree of a production part
   fall, and does that permit a hosted model at all?
3. If not, is a locally hosted model inside our own network acceptable —
   and does it need its own approval?

### The training question is separate, and much heavier

The YMRI meeting raised an NDA so that drawings could be used to train
the model. **That is a different and far larger compliance question than
running this tool**, and it should not be bundled with it:

- Running the tool sends a feature tree to a model that does not learn
  from it.
- Training sends a corpus of Yamaha design data somewhere and changes
  model weights with it.

The second needs its own legal review, its own data agreement, and a
clear answer on where the trained weights live and who can use them. It
is worth doing, and it should be a separate submission with a separate
approval. Mixing them risks the easy approval being held up by the hard
one.

### Change control — it edits real parts

This is the part a design-quality function will ask about, and the honest
position:

| Risk | What exists today |
|---|---|
| A wrong value breaks the part | One expression edit, reversible by NX's own undo; an undo mark before each change. |
| A value quietly breaks a design relation | An expression driven by a formula is refused with its formula quoted, never overwritten. |
| An impossible operation reaches the part | Operations are checked before they are sent. |
| Work is lost | The plugin never saves. |
| It does something nobody asked for | Every turn is started by the engineer from a dialog. |

**What does not exist yet and should, before any production part: a
preview step.** The operations for a turn are all known before any of
them runs, so they can be shown and approved rather than applied. On a
Yamaha production part that is likely the difference between allowed and
not, and it is about a day of work.

Until it exists, the rule to agree out loud: **copies, not production
parts.**

### Personal data

The tool processes none. Prompts are written by engineers about parts.
No personal data is collected, stored or transmitted. Say so in the
submission and the question closes.

---

## The order to do it in

1. **Rotate the credentials in the published `.env`.** Today, before
   anything else here. (§1)
2. **Email the authors for a licence.** It has a lead time and it gates
   everything downstream. (§2)
3. **Correct the attribution wording** on the expo material and the
   Confluence page, and stop describing the pipeline as unmodified. (§3)
4. **Ask Siemens the three licensing questions.** Also lead time. (Part 1)
5. **Decide the model and write the decision down.** Local for anything
   confidential; if Bedrock, an approved in-region id, never a `us.` or
   global profile unless cross-region processing is approved. (Part 2)
6. **Register it under the AI policy** and tell IT what it is, with the
   facts in Part 1.
7. **Build the preview step** before any real part.
8. **Run `selfcheck.py`** on the NX machine — it proves or corrects the
   API assumptions in one minute and changes nothing.
9. **Leave Teamcenter alone** until 1–8 are done.

Items 1, 2 and 3 do not depend on NX, on YMRI, or on anybody's approval.
They can be started now.
