# Execution contract

## Components

`compiler` scans supported local sources, constructs a tracking profile or validates a host/model proposal, and writes a content-addressed bundle. `ProjectService` scopes CLI/MCP actions to one project. `SQLiteStore` owns persistent mutations. `SkillRuntime` supplies managed model/tool execution. `hosts` handles project-local installation. `ArtifactStore` retains large text separately.

## Immutable definitions, mutable state

A `Skill` includes a name, instructions, inline state schema, initial state, version and byte budgets. A run serializes its definition at creation. Regeneration creates a new content-addressed bundle and advances a pointer for future runs; it does not rewrite a running definition.

A run has an ID, owner, revision, state, latest observation, status and optional pending operation. Every advancing mutation checks ownership and, where applicable, the expected revision. A stale decision is rejected, not merged blindly.

The first release provides explicit ownership handoff, not expiring leases. An abandoned owner can be supplied by the local operator when resolving work; owner IDs are coordination metadata, not secrets. Same-run simultaneous execution is blocked by reservations and revision checks. Different runs can progress independently.

## Model context

Managed calls receive immutable instructions/schema/tool contracts, the current state and the latest observation. A rejected proposal adds a bounded validation feedback field while preserving that observation. Conversation history, audit events and reasoning traces are not re-injected.

Default limits are 64,000 state bytes, 32,000 observation bytes, 160,000 total context bytes and 64,000 decision bytes. These are UTF-8 byte budgets, not token estimates. `Limits` can configure them within supported bounds. Oversized required content raises `BudgetExceeded`; it is not silently discarded.

An application's model adapter must not append hidden session history. Native host sessions retain their own context; the library only bounds its returned context, not the host's total token consumption.

## Patches and schemas

Patches are ordered `set`/`delete` operations on JSON Pointer dictionary paths. Parents must already exist. Lists are replaced as complete values. `set` with `null` assigns null; `delete` removes a key. Candidate state is copied, patched, fully validated and checked against the byte limit before persistence.

Schemas use draft 2020-12 and an object root. This release requires inline schemas: `$ref`/`$dynamicRef`, `patternProperties` and unrestricted regex patterns are rejected. The compiler's simple identifier pattern is allowed. Use enums, named properties and application checks for richer constraints. Known JSON Schema formats are checked by jsonschema's available format validators; unknown formats are annotations, not validation guarantees.

Schema validation proves shape and declared constraints. It does not prove that a refund occurred, a test passed or a source observation is true.

## Operation protocol

1. Validate the model decision, tool name, arguments and candidate state.
2. Reserve an operation in SQLite. Persist its action and candidate; keep committed state unchanged.
3. Execute the registered tool outside the transaction. Pass its operation ID to the handler.
4. Validate the returned `ToolResult` and optional output schema.
5. In one transaction, record the outcome, advance the state if successful, store the latest observation, clear the pending operation and append an event.

If a tool reports failure, state stays unchanged. If it raises, times out or returns invalid data, the outcome is uncertain: mark it `unknown` and block further effects. If the process dies before marking uncertainty, the earlier `pending` reservation still blocks replay.

`record_result` is idempotent for an identical already-recorded result. A different result conflicts. An unknown operation requires `reconcile=True`, after the caller checks what actually happened. A local audit failure rolls back the result/state transaction together.

Agent-provided results carry `agent_reported` provenance. Managed handlers produce `runtime_observed` results: the runtime observed and validated their contract, but has not independently proved business truth. Native MCP exposes no flag to upgrade this provenance.

## Completion

A managed final decision has `done=true` and `action=null`. Applications can supply `completion_check` to enforce domain-specific completion requirements. Otherwise completion is the model's declaration plus structural validation. Native `--done` is likewise agent-reported. Successful tool execution alone does not automatically complete a run.

Managed `run` enforces `max_steps` and retains the checkpoint if the limit is reached. A completed run can be read but cannot be advanced. Native host looping is controlled by its skill/host, not a background daemon in this package.

## Persistence and artifacts

SQLite uses foreign keys, explicit transactions, WAL and full synchronous mode. Database schema version 1 is checked on open; unknown future versions are rejected. No migration is currently needed. Storage files are local-only; network-filesystem or multi-tenant deployment is outside the supported contract.

Audit events are outside model context. They can grow over time; applications must manage retention. Text artifacts are content-addressed, capped at 2 MB and read in bounded character ranges with integrity checks. Hashes detect accidental content changes, not malicious changes by someone who controls the entire local store.

## Installation and recovery

Installers preflight conflicts, atomically replace individual files and preserve unrelated MCP entries. They roll back ordinary write failures. Multi-file installation is not a filesystem transaction; after process death, rerun `init` to converge and run `doctor`. Do not edit managed files while an installer is running. Uninstall preserves modified files and all run data.

## Deliberate limits

No automatic native transcript replacement, full tool interception, arbitrary code rewriting, multi-machine run transfer, lease expiration, automatic compensation or exactly-once external effect guarantee. A sync handler can continue after an async timeout; callbacks are not sandboxed. These limits are part of the contract, not features implied by the paper.

## Host registry and optional task lifecycle (0.2)

`host_registry` implements a small HostAdapter protocol over the existing hosts
and desktop installers. It provides detect/install/uninstall/doctor/manifest
operations. No host name enters the SQLite schema or managed runtime. Core state,
operations, evidence and bounded model inputs retain their existing boundaries.

`lifecycle` defines an optional task profile and evidence/freshness validation.
`ProjectService` exposes start_task, checkpoint_task, complete_task and find_runs
in addition to the existing semantic run operations. CLI and the four additive
MCP tools call this same service. SQLite remains schema v1; old imports and all
twelve original MCP tools are preserved.

Milestone records live in the run's validated state, not a second database.
Artifact bodies and the event audit remain separate from working context. The
profile is not forced onto domain-specific schemas. See [state semantics](execution-state.md)
and [host installation](integrations.md) for boundaries and downgrade guidance.
