# Changelog

## 0.1.2 — desktop connection and host acceptance

- Explicit `connect claude-desktop` / `disconnect claude-desktop` commands, with Microsoft Store and standalone Windows detection, macOS defaults and explicit config paths.
- Preserve unrelated app settings, isolate server names per project, serialize connection writes, refuse user-modified entries, and roll back configuration on receipt write failure.
- Include desktop connections in `doctor`; retain state when disconnecting.
- Disambiguate the source resource directory for root-level SKILL.md files.
- Add a reproducible synthetic invoice acceptance exercise and report actual host successes and blockers separately.
- Codex completed a real MCP review and handoff. Claude Desktop discovered the server but awaited user tool approval. Antigravity desktop reported tools unavailable; IDE login was not configured. These are not three passing end-to-end host tests.

## 0.1.1 — public distribution

- Self-contained PyPI package description with installation and SDK examples.
- GitHub OIDC publishing workflow: full test matrix, clean installation, optional TestPyPI rehearsal, PyPI and downloaded package verification.
- Verify registry file hashes against the tested artifacts before installation.
- No changes to the runtime or storage contract from 0.1.0.

## 0.1.0 — initial alpha

- Source-preserving SKILL.md conversion and Python test tracking profile.
- Source-bound semantic proposal preparation/validation and optional stateless JSON model adapter.
- Immutable skill definitions and source drift detection.
- SQLite revisions, ownership handoff, operation intents and explicit reconciliation.
- Managed async runtime with bounded context and tool argument validation.
- Project-scoped Codex, Claude Code and Antigravity skill/MCP installers.
- STDIO MCP server, protocol smoke test, CLI and text artifact store.
- Offline examples, cross-platform CI and package checks.

Not included: native transcript replacement, arbitrary code rewriting, live certification of every host version, distributed multi-tenant storage, automatic external-effect rollback or reproduced paper benchmarks.
