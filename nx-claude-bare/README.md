# Claude on NX, bare

Claude, AWS Bedrock, and NX Open. Nothing else. No CADSmith, no FreeCAD,
no server, no web page, no library of CAD operations, no retries, no
repair, no planner. Seven files. What runs inside NX is under a thousand
lines including its comments, and the loop at the centre of it is forty.

It exists to answer one question that the rest of the work cannot answer,
because the rest of the work helps too much:

> Given a live NX session and nothing but NX's own API, how much can
> Claude actually do when it is simply asked?

Whatever happens when you run this is Claude and NX. If a part gets
modified, Claude knew how to modify it. If it fails, it failed on NX's
real API and the traceback says why. Either answer is worth having, and
neither is available from a system that has been arranged to succeed.

Copy this folder anywhere. It does not import from the repository around
it and nothing has to be installed into NX's Python — the AWS request is
signed with `hmac` and `urllib` from the standard library, because there
is no pip in NX and on a corporate machine there is not going to be.

## The files

| | |
|---|---|
| `preflight.py` | **run this first.** Will this machine run it at all? Checks NX, Python, the certificate trust store, proxy settings, whether AWS is reachable through corporate TLS inspection, credentials and disk. Changes nothing. |
| `hello.py`  | one Bedrock call, no NX. |
| `bare.py`   | the journal. Run it inside NX. |
| `nxside.py` | the only file that touches NX: five tools. |
| `bedrock.py`| builds one Bedrock request and parses the reply. |
| `sigv4.py`  | signs it, with the standard library alone. |
| `check.py`  | checks that run with no NX and no AWS account. |
| `prompt.txt`| the task. Edit this. |

## Step 1 — before NX

Credentials. Prefer the file over environment variables:

```
aws configure
```

The reason is that a journal runs inside NX's own process, and NX
inherited its environment when it started. A `set AWS_ACCESS_KEY_ID=...`
typed into a command window after NX was already open does not reach it.
`~/.aws/credentials` (on Windows, `C:\Users\you\.aws\credentials`) is
read at the moment of the call and always works. Environment variables
are read too, if they were set before NX started.

Then:

```
python hello.py
```

It prints the region, the model id and the key it found, asks Claude one
question, and prints the answer. If it fails it says which of the three
was wrong. Get this working before opening NX; diagnosing it from inside
a journal, with the Information window as the only output, is much
harder than it needs to be.

If the model id comes back 404, that is this account not being able to
call that exact id — usually the version or the prefix, not a typo. Set
`BARE_MODEL` to whichever id already works on this account.

On a locked-down machine there may be no Python installed at all and no
way to install one. That is what `preflight.py` is for: run it as an NX
journal instead, using NX's own interpreter — which is the one that has
to make the call, and whose TLS and proxy settings are the ones actually
in question.

## Step 2 — in NX

1. Open a part. **Use a copy**, not something that matters.
2. Write the task into `prompt.txt`. The one in there now asks Claude to
   read the tree and explain the part without changing anything, which is
   the right first run.
3. In NX: **File → Execute → NX Open…** and pick `bare.py`.

The conversation appears in the Information window as it happens, and
lands in `bare-transcript.txt` beside the journal. That file is the
result of the experiment — it has every tool call, every argument, every
answer NX gave and every traceback.

## What Claude is given

Five tools and one sentence. The sentence is `SYSTEM` at the top of
`bare.py`; it says there is a live NX session, that the part is the work
part, and that units are millimetres. That is the whole prompt. If you
want to know what guidance would buy, add some there and run the same
task again — that comparison is most of the value of having a bare
version.

The tools are `read_tree`, `set_expression`, `suppress_feature`,
`delete_feature`, and `nx_python`.

`nx_python` is the interesting one. It runs Python that Claude wrote,
inside the NX session, with `NXOpen` imported and `theSession`,
`workPart`, `displayPart` and `theUI` already bound — the names NX's own
journal recorder uses, which is the NX code Claude has read most of.
Nothing is wrapped and nothing is translated: if Claude wants to make a
block, it writes the `NXOpen.Features.BlockFeatureBuilder` calls itself,
and if it gets a class name wrong on 2412 it sees the traceback and tries
again. That is the experiment.

## Before you run it on anything you care about

* **An undo mark is set before every change.** A bad edit is one Ctrl+Z
  away, a bad run is a few. This is the real safety net.
* **`BARE_DRY=1` executes nothing.** Every write is refused, Claude is
  told it was refused, and the code or value it wanted is recorded in the
  transcript. One dry pass tells you exactly what it intends to do.
* **`nx_python` runs code that a language model wrote**, in your NX
  session, with your part open. It is not sandboxed and it cannot be:
  the whole point is the real API. Use a scratch part, read the
  transcript, and do not point this at a Teamcenter-managed part until
  somebody who owns that decision has said yes.
* It makes one outbound HTTPS call per round, to
  `bedrock-runtime.<region>.amazonaws.com`, carrying the prompt, the tree
  Claude read, and the code it wrote. Nothing else leaves the machine and
  nothing is stored anywhere but the transcript beside the journal.

## Settings

| | |
|---|---|
| `BARE_MODEL`    | Bedrock model id. Default `anthropic.claude-sonnet-5`. |
| `BARE_PROMPT`   | the task, instead of `prompt.txt`. |
| `BARE_DRY=1`    | perform nothing; report what would have been done. |
| `BARE_ROUNDS`   | how many model turns before giving up. Default 12. |
| `BARE_THINKING=1` | adaptive extended thinking. Try it once the plain path works. |
| `BARE_LOG`      | where to write the transcript. |
| `AWS_REGION`    | else `~/.aws/config`, else `us-east-1`. |
| `AWS_PROFILE`   | which profile to read. |
| `HTTPS_PROXY`   | honoured, if the machine goes out through one. |

## check.py

```
python check.py
```

Everything that can be verified without NX and without an AWS account:

* The **signature**, against botocore's own `SigV4Auth` — the same
  request signed both ways with the same fake key and a frozen clock,
  compared character by character, for plain and versioned and
  geography-prefixed model ids, with and without a session token. This is
  the one part of the folder that reading cannot verify: a signature is
  either byte-identical to what AWS computes or the call is a 403 that
  says nothing. (Where botocore is not installed — NX's Python, for
  instance — the check says so and is skipped. It is a check *on* this
  folder, not a dependency *of* it.)
* The **request**: model id in the path with its colon encoded the way
  boto3 encodes it, Bedrock's wire version, the tools, the system prompt,
  the thinking flag only when asked for.
* The **loop**: run against a fake NX and a scripted model, so the
  bookkeeping is checked — which `tool_result` answers which `tool_use`,
  that a refusal reaches the model marked as an error, that it gives up
  after its rounds instead of spinning.

What it cannot check is whether the NX calls in `nxside.py` are right.
Those property and class names came from the NX Open reference and were
written without a session to confirm them; some will be wrong on 2412.
That is what the first run is for, and why `read_tree` on a part you
already understand is the first thing to try.

## What this is not

It is not the pilot, it is not a plugin, it has no feature-tree UI, no
drawing generation, no part viewer, no validation, no undo stack of its
own, no memory between runs, and it will not get any of those. The
CADSmith branches are where that work is. This folder is a measurement,
and it should stay small enough to read in one sitting.
