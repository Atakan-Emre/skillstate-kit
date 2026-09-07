# Validation and release evidence

Tests validate contracts, not an absence of all possible defects. A successful generation reports structural checks; it does not invent live execution evidence.

## Task integrity hardening (0.2.1)

The [0.2.1 release workflow](https://github.com/Atakan-Emre/skillstate-kit/actions/runs/34120659712)
passed **151 tests in each of six OS/Python jobs**, with **89.11–89.24%** coverage.
Locked-dependency auditing reported no known vulnerabilities. Fresh installation,
MCP transport, publishing and downloaded PyPI file verification passed.

New regressions reject generic task progress overwrites, empty milestone evidence,
duplicate milestones and inconsistent fingerprints/references. A fresh-runtime
test checks that earlier observations do not enter subsequent model inputs.
Existing Codex task records and smolagents state remained readable and valid;
the original smolagents evidence verifier passed without new model execution.
See [research alignment](paper-alignment.md) and [release notes](releases/0.2.1.md).

## Portable task lifecycle (0.2.0)

The [0.2.0 publication workflow](https://github.com/Atakan-Emre/skillstate-kit/actions/runs/34118611608)
passed the six OS/Python jobs, package checks and downloaded PyPI verification.
Linux/Python 3.11 passed **135 tests**, **88.93%** coverage. Local Windows/Python
3.12 passed **134 tests**, with one symlink-privilege skip and **88.63%** coverage.

The [coding-agent report](benchmarks/coding-agent.md) records four real Codex
sessions per mode, independent correctness checks and actual host-reported usage.
Persisted continuation passed; token and latency savings did not. The existing
smolagents verifier was rerun successfully. New task stores were also read with
the published 0.1.2 SDK, and the new SDK read the unchanged old smolagents store.
SQLite schema version remains 1.

Additional automated coverage checks evidence integrity, explicit revalidation,
granular source drift, ownership/revision guards, pending/unknown recovery,
instruction preservation and selective removal, and the additive sixteen-tool
MCP contract. Claude Code live execution is not marked passing; the
[manual fixture and handoff verifier](../examples/coding_agent/README.md) are provided.

## Desktop acceptance (2026-09-07)

An additional [external-project experiment](smolagents-acceptance.md) used the
existing smolagents SQL agent, a real model, 1,000 synthetic receipts and an
independent Decimal verifier. Baseline and integrated results matched on all
five checks; the managed run resumed across a forced process exit without
repeating completed queries. This is a separate application acceptance result,
not an expansion of the unit-test count or a paper benchmark reproduction.

See [host acceptance](host-acceptance.md) for a completed Codex-to-Claude Desktop Chat review/handoff workflow, including persisted recovery, with separate host coverage limitations. The original configuration-only checks below are historical and do not supersede that report.

The [0.1.2 release workflow](https://github.com/Atakan-Emre/skillstate-kit/actions/runs/34088894774) passed the six OS/Python jobs, package checks and public PyPI verification. Windows/Python 3.11 passed **114 tests**, with **86.90%** coverage. Two independent Codex model sessions also generated, executed and resumed a semantic invoice skill through completion; the public 0.1.2 package independently read and verified its persisted state and artifacts.

## Initial release checks (2026-09-06)

- Local Windows / Python 3.12.7: **99 passed, 1 skipped**, **87.12%** combined statement/branch coverage. The skipped test requires symlink privileges. CLI Unicode output was also verified through an ASCII-only pipe.
- A scripted 100-operation run retained identical model-context byte sizes while its audit grew to 202 events. This checks history isolation, not real-model task quality or token savings.
- Fresh wheel installation in a separate environment passed demo, generation, bundle validation and a real 12-tool MCP STDIO handshake (protocol `2025-11-25`). Wheel/sdist passed `twine check`.
- Both generated skill files passed Codex's skill-format validator. The installed Codex CLI discovered the generated `skillstate-kit` MCP entry and reported it enabled. This was configuration discovery, not a live model completing the workflow.
- Claude Code and Antigravity were not exercised as live applications in this initial check. This did not establish that the desktop applications were absent from the computer. Their generated configuration and shared state protocol were covered by automated tests.

The release's CI link records the exact release commit and cross-platform results; use it when checking a downloaded distribution. These observations do not certify every host version or arbitrary generated domain schema.

## Automated test matrix

| Area | Observable checks |
|---|---|
| JSON/schema | Duplicate keys, non-finite values, forged scalar types, depth/size limits, offline schema restrictions |
| Patches | Atomic rejection, preservation, null vs deletion, JSON Pointer escaping |
| Runtime | Observation-preserving retry, registered tools, argument checks, output validation, completion and step budgets |
| Storage | Durable pending intent, rollback on event failure, result idempotency, conflicting revisions/owners |
| Crash | Separate process exits after a simulated external effect; pending intent survives and blocks replay |
| Concurrency | Multiple independent SQLite connections compete on one revision; one wins |
| Compiler | Source preservation, idempotence, semantic proposal validation, freshness and integrity, AST without execution |
| Installer | Three config formats, preserve unrelated entries, refuse user edits, non-destructive uninstall |
| MCP | Real STDIO client/server initialize, tool listing, state mutation and error handling |
| HTTP adapter | Mocked protocol responses, stateless request payloads and errors without credential leakage |
| Distribution | Build metadata, installed wheel entrypoint/demo/generation/MCP diagnostics |

GitHub CI is the authoritative record for its exact commit and OS/Python matrix. Local runs do not establish other OS results. The symlink test may skip on Windows without symlink privileges; Linux/macOS runs exercise it where supported.

## Reproduce

```text
uv sync --locked --extra dev
uv run ruff check src tests examples
uv run ruff format --check src tests examples
uv run pytest --cov=skillstate --cov-fail-under=85
uv run python -m build
uv run twine check dist/*
uv run python scripts/check_wheel.py dist
```

## What is not claimed

- No reproduction of the SKILL.state paper's benchmarks or token savings.
- The offline examples use scripted models; the HTTP tests use controlled responses.
- File/config and MCP tests are not live Claude Code or Antigravity end-to-end tests.
- JSON Schema and `runtime_observed` provenance do not independently prove external business truth.
- The first release is alpha; production workflows need their own representative task and recovery tests.

Release notes should link the passing commit/CI run and state which host/provider checks were actually performed. Do not change these qualifications merely to make the release sound complete.
