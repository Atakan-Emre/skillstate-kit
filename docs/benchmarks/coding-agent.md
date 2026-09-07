# Coding-agent acceptance and measurement — 2026-09-07

**Correctness and persisted continuation passed. Efficiency did not improve in
this trial.** SkillState used 102.6% more reported tokens and 83.2% more wall time
on this small coding task. This result does not support a token-savings claim.

[Machine-readable evidence](../evidence/coding-agent-2026-09-07.json) ·
[Reproduction and manual Claude acceptance](../../examples/coding_agent/README.md)

## Observed

Codex CLI 0.153.4 ran the same duration-parser task in two fresh fixture copies:
ordinary host execution and host execution with SkillState 0.2.0 development
integration. Both were allowed normal project notes. No custom Python agent or
scripted model choices were used. The ordinary task prompt did not prescribe
SkillState tool calls; project instructions encouraged the lifecycle.

Each mode used four independent ephemeral host processes, with planned stops
after stages 2, 4 and 6. No earlier conversation was passed to the next process.
The integrated host used both CLI and MCP paths to the same store. One canonical
run survived throughout: `task-ff4b43cb3903507cae473b03`.

Completed-step counts were **2 → 4 → 6 → 8**, revisions **2 → 4 → 6 → 15**.
The final run was completed, all milestone evidence was current, and no reset
occurred. Six earlier milestones were explicitly revalidated in the final
session after expected implementation changes and newline normalization changed
their resource fingerprints. These were recorded with a reason; this experiment
does **not** demonstrate zero repeated work.

Both implementations passed the independent evaluator's 29 contract checks.
The baseline's own suite passed 103 tests and the integrated fixture's suite
passed 91. Different generated test counts are not a quality comparison; the
same independent evaluator is the common correctness gate.

## Measured

| Metric | Baseline | With SkillState |
|---|---:|---:|
| Independent checks | 29/29 | 29/29 |
| Fresh host sessions | 4 | 4 |
| Reported input tokens, including cached input | 505,477 | 1,027,038 |
| Cached input tokens, subset of input | 455,168 | 896,512 |
| Reported output tokens | 6,514 | 10,285 |
| Input + output tokens | 511,991 | 1,037,323 |
| Host session wall time | 373.001 s | 683.313 s |
| Completed tool calls | 27 | 76 |
| Exact repeated call signatures | 4 | 15 |
| Commands containing repository-search patterns | 13 | 10 |
| Commands containing file-read patterns | 12 | 18 |
| Exact repeated file-read commands | 1 | 3 |
| Initial task prompt bytes per session | 1,799 | 1,799 |

Token values come from actual Codex `turn.completed.usage`; cached input is not
added a second time. They include the host's own overhead, and are not inferred
from context bytes. Total tokens are not equivalent to billed cost.

Canonical context size at the four integrated boundaries was **4,912 / 6,603 /
8,414 / 11,122 UTF-8 bytes**. Three observed MCP `run_context` result envelopes
were **11,599 / 13,003 / 14,308 bytes**, including transport representation.
These are different measurements. CLI context reads and native host transcript
size are not represented by the MCP-response series. No baseline canonical
context exists, so those sizes do not establish a relative context reduction.

Exact call repetition includes state queries and necessary verification. Search
and read counts are regex matches on completed shell commands, not a complete
filesystem trace. They cannot automatically distinguish accidental replay from
legitimate validation.

## Inferred

The lifecycle worked without requiring the user to manually orchestrate every
state tool. On this task, checkpoint/evidence calls, repeated context reads and
source revalidation added substantial overhead. Broad resource references from
early inspection/planning milestones made later normal edits stale those records.
The logs support these as contributing mechanisms, but do not isolate their
individual token or latency cost.

A useful next optimization is to make milestone evidence dependencies more
precise and reduce unnecessary state round trips. It must preserve verification
and be evaluated on additional tasks, including long tasks with expensive
avoidable operations. This single trial cannot establish general savings or
general slowdown across workloads.

## Not measured

- Provider invoice cost: pricing was not explicitly configured.
- Individual model request count: CLI session usage did not expose that count.
- Full native transcript size or host-side transcript removal.
- Statistically significant effects: one paired trial, baseline first, no
  randomized ordering or confidence interval.
- Claude Code live acceptance or a new Codex → Claude Code live handoff:
  the Claude Code executable was unavailable. The manual procedure and read-only
  verifier are provided; SDK/MCP protocol tests are separate evidence.

Both runs shared the same Windows environment and development interpreter.
Inherited parent-repository test configuration caused failed initial test commands
that the hosts corrected. These attempts remain in the measurements. MCP startup,
cache state, host model defaults and local execution differences are potential
confounders. No model override was selected; the collected usage did not identify
the exact model. Local raw logs are retained with hashes in the published summary;
they are not published wholesale because of local paths and host metadata.

The existing [smolagents acceptance](../smolagents-acceptance.md) remains separate:
it verifies external-framework correctness, forced process restart and no repeated
completed SQL queries. It is not reinterpreted as provider token evidence.
