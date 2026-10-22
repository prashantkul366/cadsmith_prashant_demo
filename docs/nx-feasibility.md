# NX and Teamcenter: feasibility, permission and risk

For YMSLI to take to YMRI. Written to be argued with: every claim says
where it came from, and the ones that are assumptions say so.

> **See also [`compliance.md`](compliance.md)**, which answers "how much
> compliance does this need" for NX and for YMC, and records four things
> found while checking the licensing question - including a credential
> published in a public repository and the fact that the research code
> this is built on carries no licence.

**What I can and cannot tell you.** I can tell you what the software
allows and where the technical risks are. I cannot tell you what Yamaha's
policies permit - I have not seen them, and nobody outside your IT and
export-control functions can answer that. Where the answer is "ask", the
question to ask is written out so it can be forwarded as it stands.

---

## 1. Can it be done technically

**Yes, and the shape is settled.** A plugin runs inside the engineer's NX
session, reads the feature tree through NX Open, and changes the part by
editing the expressions that drive its features. Parasolid makes the
geometry; nothing is modelled twice and no file is exchanged.

Three things are already decided by what NX allows rather than by
preference:

- **The plugin calls out; nothing calls in.** NX Open is not documented
  as thread-safe, so a listener inside the session is the wrong design.
  The engineer starts a turn from a dialog, and every NX Open call
  happens on NX's own thread inside that callback.
- **Changes go through expressions**, not through rebuilding the part.
  NX names a feature's parameters p1, p7, p9 and says what each drives -
  `p7 (Simple Hole(12) Diameter)` - so a part designed by somebody else,
  years ago, can be changed without knowing how it was built.
- **An expression driven by a formula is refused, not overwritten.**
  Writing a number over `wall/2` silently destroys a relation a designer
  put there deliberately. This matters more in a Yamaha part than in a
  test part.

**What is not yet known** is which of the NX Open property names used
are right for 2412.5000. `app/nx/selfcheck.py` answers that in one run
on a machine with NX. It opens nothing, changes nothing and saves
nothing; it writes a report of what the API offers.

---

## 2. Licensing

> **Corrected.** This section previously framed the question as signed
> versus unsigned applications, with an author licence needed per seat to
> run unsigned code. That is the rule for **compiled** NX Open
> applications and does not describe what we are shipping, which is a
> journal. The current reading is below; the full version, with the
> sources, is in [`compliance.md`](compliance.md).

From Siemens community sources, **not** from Siemens' licence terms,
which should be confirmed with your reseller:

| | |
|---|---|
| **Running** a Python journal | No technical barrier. A Gateway licence can execute one, given the module licences its operations need. |
| **Authoring and distributing** Python NX Open code | Siemens' stated position is that the legal conditions apply even though nothing enforces them: the Python Author feature (NX30115) or the Toolkits bundle (NX30106). |
| **Signing** | For compiled applications. Not applicable to a journal. |

**The shape of the risk is not cost, it is audit.** The journal will run
whether or not the authoring licence is held, so an unlicensed-authoring
finding surfaces at a Siemens licence audit rather than at install time.
Yamaha is the size of customer that gets audited.

Ask the Siemens account manager, verbatim:

> We are writing NX Open code in Python as journals, for internal use at
> Yamaha, and distributing them to a handful of our own engineers. (a)
> Does that require the Python Author feature (NX30115) or the Toolkits
> bundle (NX30106), or is a Gateway/execute licence sufficient for both
> writing and running them? (b) Does distributing journals internally
> count as distribution under our agreement? (c) Which module licences
> must a seat hold for a journal that edits expressions and suppresses
> features?

---

## 3. Where the data goes - the question YMRI actually asked

This is the one that decides whether it is allowed, and the answer is
good: **nothing has to leave the machine.**

- The **geometry never moves.** The part stays in NX. The plugin sends
  the server a feature tree - names, numbers, feature types - not a
  solid, not a file.
- The **model can be local.** The app already runs against Ollama, LM
  Studio or any vLLM endpoint. With one configured, the prompt and the
  tree go to a process on the same machine or the same network, and
  nothing goes to the internet.
- The **only network traffic is to 127.0.0.1** unless somebody
  configures otherwise.

Two things to be straight about rather than quiet about:

- **The feature tree is not nothing.** `p7 (Simple Hole(12) Diameter) =
  13` plus a prompt saying "the exhaust bracket" is design information.
  On a local model it stays local; on a hosted model it would not. If
  Claude on Bedrock is used for the demo, that is a deliberate choice to
  send tree data to AWS, and it should be made deliberately and written
  down, not inherited from a config file.
- **Prompts are written by engineers** and will contain part names,
  project names and intent. Same rule applies.

---

## 4. What corporate IT will ask, and the honest answers

| Their question | The answer |
|---|---|
| Does it install software? | A Python file run as an NX journal. No installer, no service, no driver, no registry change. The server is the Python app you already run. |
| Does it need admin rights? | No. |
| Does it open a network port? | The server listens on 127.0.0.1 only. The plugin makes outbound calls to that address. Nothing listens on an external interface. |
| Does it reach the internet? | Not with a local model. With a hosted one, only to that provider's endpoint. |
| Can it change or delete design data? | Yes - that is what it is for. See the safety section. |
| Does it bypass Teamcenter? | Not if it works on parts already checked out. See section 5. |
| What runs with what privileges? | Everything runs as the engineer, inside their NX session. It can do what they can do and no more. |

The one that usually needs a real conversation is **endpoint protection**:
a CAD application making outbound HTTP to a local Python process can look
unusual to an EDR agent. Worth raising before the install, not after the
alert. `selfcheck.py` reports whether NX can reach localhost at all,
which is the cheap way to find out if something is already blocking it.

---

## 5. Teamcenter

**Deliberately out of scope for the first demo, and the reason matters.**

A part under Teamcenter management is checked out, modified, checked in -
and community sources report that checking out an NX dataset does not
necessarily check out the item revision, which is the kind of detail that
decides whether an integration is correct or quietly wrong.

For the demo the safe rule is: **the plugin changes only what the
engineer already has checked out and open.** It does not check out, does
not check in, does not create revisions. The engineer saves through
Teamcenter exactly as they do now. That keeps every PLM rule intact
because the plugin never touches PLM.

Doing more later means ITK, the SOA services or the Active Workspace REST
layer, and needs their Teamcenter release and their business rules. It is
a separate piece of work and should not be bundled into the demo's
approval.

---

## 6. Safety: it changes real parts

The honest risks, and what is already done about each.

| Risk | What stops it |
|---|---|
| A wrong value breaks the part | Every change is one NX expression edit, which NX's own undo reverses. |
| A value quietly breaks a design relation | An expression driven by a formula is refused with its formula quoted, never overwritten. |
| An operation that cannot work reaches the part | Operations are checked before they are sent - a counterbore narrower than its hole, a countersink at an angle no drill has, a feature the part does not have. |
| Work is lost | The plugin never saves. The engineer saves, or does not. |
| It does something nobody asked for | Each turn is started by the engineer from a dialog, and every operation carries the intent it was asked for. |

**What is not yet done and should be before an engineer uses it on real
work:** a preview step. The operations for a turn are known before any
of them is performed, so they can be shown and approved rather than
applied. On a Yamaha production part that is likely the difference
between allowed and not, and it is a day's work, not a redesign.

**The rule to agree out loud:** the demo runs on copies, not on
production parts, until the preview step exists and YMRI have watched it
work.

---

## 7. What to settle, in order

1. **Run `selfcheck.py`** on the colleague's NX. One minute, changes
   nothing, and it either proves the API assumptions or corrects them.
2. **Ask Siemens the three licensing questions** in section 2. The
   signing answer has a lead time and gates the pilot's cost.
3. **Decide the model**: local for anything confidential. If Bedrock is
   used for the demo, write down that tree data goes to AWS.
4. **Tell IT what it is** before the install, with section 4.
5. **Build the preview step** before real parts.
6. **Leave Teamcenter alone** until 1-5 are done.
