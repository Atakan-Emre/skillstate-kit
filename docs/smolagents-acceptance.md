# External-project acceptance: smolagents

**Result: the existing SQL agent workflow passed before integration and after
integration with skillstate-kit, including continuation in a new process after
an injected interruption.** All five report fields matched an independent
calculation. No completed SQL query was repeated after restart.

Date: 2026-09-07. [Reproduction instructions](../examples/smolagents_acceptance/README.md)
· [Machine-readable evidence](evidence/smolagents-2026-09-07.json)

## Project and environment

We used [Hugging Face smolagents](https://github.com/huggingface/smolagents), pinned
to commit `30bb1161095dbae2271e6bc3cc4c219cc3897a57`. At selection, GitHub reported
29,207 stars and 2,935 forks. The checkout had 12,774 Python source lines across
18 files under `src`. These identify a substantial external framework; they do
not increase the scope of the workflow actually tested.

The starting point was its existing `examples/text_to_sql.py`, including the
actual decorated SQL tool. We used Windows, Python 3.12.7, SQLAlchemy 2.0.52,
smolagents 1.27.0.dev0 at the pinned commit, and **skillstate-kit 0.1.2 installed
from public PyPI**, without modifying its installed runtime.

Both modes used the installed Codex CLI's default real model through an explicit
completion adapter. No scripted responses were substituted. The original
example's hosted model provider was replaced by this adapter, so this is not a
test of its original Llama provider. Model-generated SQL actually executed in
the upstream tool. The CLI itself did not execute tools or inspect the database.

## Procedure

1. Run the original four-receipt question through `CodeAgent`. The successful
   answer was **Woodrow Wilson**.
2. Populate a deterministic synthetic database with 1,000 receipts and 37
   customers. Run five specified report checks through the baseline `CodeAgent`,
   allowing one SQL query per model turn.
3. Prepare the upstream source and the explicit audit instructions. Have the real
   model propose a semantic state schema, then validate and apply that proposal
   with the compiler and source fingerprint.
4. Run the same SQL tool against the same data through `SkillRuntime`. After the
   third operation has committed, forcibly exit the process using `os._exit(75)`.
5. Start a separate process and reopen the stored run. Supply its current state
   and latest observation, without the prior conversation. Finish the remaining
   work, then independently read the canonical state, events and query evidence.

## Results

| Check | Baseline | With skillstate-kit | Independent calculation |
|---|---:|---:|---:|
| Receipt count | 1,000 | 1,000 | 1,000 |
| Gross total | 127,955.00 | 127,955.00 | 127,955.00 |
| Tip total | 15,901.78 | 15,901.78 | 15,901.78 |
| Customer with highest total purchases | customer-03 | customer-03 | customer-03 |
| Receipts with tips strictly below 10% | 467 | 467 | 467 |

The independent verifier used Python `Decimal` over the raw rows, rather than
the agent's aggregate SQL or its declaration of completion. Money comparisons
in the task explicitly used integer cents to avoid floating-point boundary
errors. Both runs preserved the receipt database's file hash.

| Execution evidence | Observed result |
|---|---|
| Baseline SQL operations / model decisions | 5 / 6 |
| Managed SQL operations / model decisions | 5 / 6, plus 1 generation call |
| Managed operations before / after process restart | 3 / 2 |
| Repeated queries after restart | 0 |
| Interrupted checkpoint | Ready, revision 6, no pending operation |
| Final checkpoint | Completed, revision 11, all five checks recorded |
| Persisted events | 12: creation, five reservation/result pairs, completion |
| Final report validation | 5 of 5 fields correct |

The fresh process consumed the persisted third observation before proceeding;
it did not need to run that query again. Tool results were recorded with
`runtime_observed` provenance. Final completion also required an application
validator to accept the actual report.

## Application context measurements

| Model call | Baseline JSON bytes | Managed JSON bytes |
|---|---:|---:|
| 1 | 10,199 | 4,569 |
| 2 | 11,103 | 3,775 |
| 3 | 12,051 | 3,797 |
| 4 — new managed process | 12,976 | 3,819 |
| 5 | 14,103 | 3,844 |
| 6 | 15,139 | 3,861 |

Semantic generation used a separate 5,982-byte application input. These are
serialized application payload measurements, not token savings or complete
provider-context measurements. The adapters include different action contracts:
baseline Python code versus managed JSON actions. This single short experiment
does not isolate the effect of history removal or reproduce the paper's benchmarks.

## Issues found and fixes applied

The upstream example initially failed with `no such table: receipts`: its
in-memory SQLite connection did not share the table with the tool execution
thread. The experiment's loader added `StaticPool` and disabled SQLite's
same-thread check for that shared connection. Both modes used the same setup;
the larger test used a durable file-backed receipt database. The upstream source
checkout remained unchanged.

Two harness issues were also corrected before the successful paired result:
serializing smolagents `ChatMessage` objects in evidence files, and reading the
prepared source hash from `inventory.source_hash`. The already-produced semantic
proposal was retained and successfully applied after the second correction.
Neither issue required a change to the published skillstate runtime.

## What this establishes

The published package can support an existing external agent's SQL workflow,
use a real-model-generated state definition, preserve correct results, and resume
from a committed checkpoint across processes. The meaningful gain shown here is
continuation from durable, explicit state while retaining the existing tool.

This remains one workflow, one synthetic dataset and one successful paired run.
It does not certify all of smolagents, production data, mutating APIs, every model,
or arbitrary crashes during external side effects. Baseline recovery mechanisms
were not evaluated, so this report does not claim the baseline cannot resume.

Integration required an explicit task specification, a tool adapter, a model
adapter and a completion validator. The package did not automatically rewrite
the entire repository. This is evidence of a working integration, not evidence
that every existing agent project becomes flawless after installation.
