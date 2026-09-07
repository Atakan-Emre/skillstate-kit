# Architecture audit and implementation contract — 2026-09-07

The pre-change architecture is intentionally retained: models/schema/jsonio → store/runtime → ProjectService → CLI/MCP → hosts/desktop. Flat modules already enforce useful boundaries; moving them into packages would break imports without product benefit.

| Requested capability | Initial classification | Decision |
|---|---|---|
| Python SDK, transactional SQLite, revisions, ownership | ALREADY EXISTS | Preserve public contracts and database v1 |
| Pending/unknown operation reconciliation | ALREADY EXISTS | Keep existing reservation protocol |
| Semantic generation and immutable bundles | ALREADY EXISTS | Do not force task schemas onto old bundles |
| Artifact integrity and bounded runtime context | ALREADY EXISTS | Reuse, keep audit outside model context |
| Project installers, MCP, host-specific wrappers | PARTIAL | Add lifecycle discovery and isolated adapter registry |
| Host detection and minimal init | MISSING | Detect without reading credentials; retain explicit host flags |
| Evidence-backed task milestones and granular freshness | MISSING | Optional task profile via shared service, existing store |
| Natural task startup and compatible-run discovery | PARTIAL | Lifecycle skill + managed instruction block; no guessing task identity |
| Codex/Claude skill/plugin distribution | PARTIAL | Thin assets depending on Python CLI/MCP |
| Source drift | PARTIAL | Existing bundle drift plus milestone resource fingerprints |
| Cross-host handoff | ALREADY EXISTS | Extend acceptance, never reset state |
| smolagents correctness/restart acceptance | ALREADY EXISTS | Preserve as a correctness experiment |
| Coding-agent benchmark and real host measurements | MISSING | Deterministic feature fixture, baseline/integrated + boundaries 2/4/6 |
| Claude Code live acceptance | MISSING | Execute if available, otherwise reproducible manual procedure |
| Native transcript compression or universal token savings | SHOULD NOT IMPLEMENT | State explicit host limitations |
| Command-string deduplication, second state engine, scheduler | SHOULD NOT IMPLEMENT | Use state/evidence/operation semantics |

## Changes and compatibility

Evolve hosts.py, service.py, cli.py and mcp_server.py; introduce small lifecycle and host-registry modules; add thin plugin assets and benchmark fixtures. Preserve store tables, Skill/Tool/SkillRuntime imports, existing CLI operations, all existing MCP tools, historical bundles and acceptance evidence. New lifecycle APIs are opt-in and cannot retroactively add completion requirements to arbitrary schemas.

Risks: preserving edited AGENTS.md/CLAUDE.md sections; shared Codex/Antigravity skill paths; misleading host detection; stale evidence; interpreting repeated calls as unnecessary; assuming usage statistics equal billed cost. Address these with marked-block ownership, conflict-aware rollback, explicit detection evidence, per-resource hashes, reported repetition categories, and unavailable metrics rather than guessed numbers.

## Phases and acceptance

0. Audit and regression baseline: 113 passed / 1 Windows symlink privilege skip; 86.84% coverage.
1. Registry/detection and reversible installation; explicit host flags remain supported.
2. Codex lifecycle instructions and bounded compatible-run summaries.
3. Claude Code lifecycle and thin plugin distribution, same Python engine.
4. Evidence-backed milestones, explicit completion and cross-host continuation.
5. Real coding fixture and baseline/integrated measurements. Session boundaries after stages 2/4/6. Independent correctness, repeated calls, search/read counts, context bytes, available host usage, wall time; cost only from explicitly configured pricing.
6. Documentation, package smoke checks and full tests with >=85% coverage.

Acceptance: old APIs/stores remain readable; no blind operation replay; instructions/config preserve unrelated edits; completed work requires evidence and justified revalidation; one canonical run survives fresh sessions/handoff; MCP and CLI use the same service; smolagents evidence stays valid; unexecuted host paths are never marked passing. Benchmark reports separate observed, measured, inferred and unavailable values.
