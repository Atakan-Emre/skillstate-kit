# Research alignment and implementation contracts

Reference: [SKILL.state, arXiv:2608.26263v3](https://arxiv.org/html/2608.26263v3),
sections 3.1–3.3, Algorithm 1 and section 7. This is an independent implementation.

The paper's execution input combines immutable procedure, current structured state
and latest observation. Reasoning does not enter later prompts. A deterministic
runtime validates state transitions. Domain schemas must preserve facts needed
for later decisions; otherwise discarding history can lose relevant information.

## Implementation mapping

| Contract | Implementation | Regression evidence |
|---|---|---|
| Pinned procedure and semantic schema | Immutable `Skill` stored with each run | Store definition and compiler source-integrity tests |
| Current state and latest observation | `runtime.context` selects the current snapshot | Fresh-runtime observation-isolation test |
| History excluded from ordinary model input | Events are queried through a separate audit API | Long-run fixed-context and restart tests |
| Deterministic validation | Schema validation and bounded explicit patches | Invalid-decision tests verify zero tool effects |
| Durable transition/result handling | SQLite operation intent and transactional result commit | Crash, rollback, uncertainty and concurrency tests |
| Domain-specific state | Semantic compiler and Python `Skill` schemas | Source-bound generation and schema tests |

These are software contract tests, including scripted model callbacks. They do not
reproduce the paper's live-model benchmark results.

## Two execution modes

**Managed Python execution:** `SkillRuntime` builds each model payload from current
data. The supplied model callback must remain stateless; `JSONChatModel` sends a
new request containing only its supplied context. Fixed schema/tool/response
contracts are also included. No reasoning field is accepted in persisted decisions.

**Native host integration:** project instructions and MCP expose durable task
state to Codex, Claude and other hosts. The host controls its model requests and
conversation history. This provides execution-state coordination but does not
enforce the paper's history-free model-input boundary. Installing a plugin alone
cannot establish that boundary.

## Intentional differences

Patches use explicit `set`/`delete` operations, preserving JSON null as a value.
Successful tool results commit the proposed state; failed tools retain the prior
state, and uncertain effects require reconciliation. Ownership, revisions,
artifacts and host adapters extend the persistence/coordination contract.

The optional task profile is a progress ledger, not a universal semantic schema.
Use domain-specific fields for facts needed by later decisions. Task milestones
retain bounded summaries and references; full logs stay in artifacts/audit data.
Byte budgets reject oversized state/context rather than silently discarding facts.

## Acceptance status

- Persistence, schema validation, bounded inputs and uncertainty handling have
  automated regression coverage.
- The recorded Codex coding experiment completed across fresh sessions, but
  showed additional token/time overhead on its small task.
- The external smolagents experiment separately verified forced-process recovery
  and no replay of completed SQL queries.
- Claude Code live acceptance is not established by configuration or SDK tests.

See [validation](validation.md) and the [coding report](benchmarks/coding-agent.md)
for measured scope. State quality and application-level outcome validation remain
necessary; neither JSON validity nor a completed flag proves arbitrary task truth.
