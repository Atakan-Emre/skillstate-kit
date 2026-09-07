# Execution state, evidence and efficiency

Conversation is an interaction surface. The canonical run is the source of truth
for recorded execution progress. Artifacts are durable evidence; the event log is
the audit trail. None of these is a vector-memory database or distributed scheduler.

## Bounded context versus audit history

Managed runtime inputs contain instructions, current state, the latest observation
and tool contracts. Host-facing run_context adds ownership/revision, pending
operation details and relevant freshness checks. The response is byte-bounded;
full event history is accessible separately through `run events`.

State and observation limits are UTF-8 byte budgets. Oversized required content
is rejected, not silently summarized. No historical conversation or hidden
reasoning is reconstructed from the event log.

Codex and Claude may still include their own transcript, system instructions,
skills and tool definitions. Smaller application payloads do not prove smaller
provider requests. Actual token, cost and latency effects require host measurements.

## Evidence-backed completed work

The optional task profile records goal, active/completed/remaining steps, blockers,
artifact references and compact milestones. Each milestone includes its summary,
evidence IDs, completion time, explicitly declared resources and their fingerprints.
Large output remains in the artifact store.

`task_checkpoint` verifies evidence existence/integrity and fingerprints declared
files. It rejects advancing past the active step or repeating a completed step
without a revalidation reason. It does not execute tests or independently certify
that an agent's evidence is truthful. Project-specific completion checks remain
necessary for production outcomes.

`task_complete` checks that every initial plan step has milestone evidence, no
steps/blockers remain, and declared resources/evidence are current. The low-level
SQLite SDK remains a coordination primitive; a caller with direct database access
can bypass application rules. This is not an authentication/security boundary.

## Duplicate work and legitimate revalidation

The runtime does not deduplicate command strings. The same test command can be
necessary after a code change; a new SQL query can accidentally repeat a completed
business operation. Hosts should consult state, evidence, dependency freshness
and pending operation IDs before acting.

Completed milestones are not instructions to repeat the work. Revalidation is
explicit and records why it was needed. Pending/unknown operations retain their
existing reconciliation protocol; a timeout is not authorization for blind replay.
The task profile does not automatically intercept every native tool or guarantee
exactly-once external effects.

## Granular drift

Only milestones referencing changed files are flagged. Unrelated files do not
invalidate all progress. Include configuration/dependency files in a milestone's
resources when they affect its validity. Missing paths can be recorded to represent
deletions; recreation makes that evidence stale. Host-readable freshness is computed
at read/completion time and does not rewrite the original checkpoint.

Filesystem hashing and SQLite commit are not one atomic filesystem transaction.
Concurrent edits can make evidence stale immediately after a check. The next read
checks it again. Existing semantic bundles continue to use their source manifests;
this task profile does not replace semantic state generation with a universal schema.
