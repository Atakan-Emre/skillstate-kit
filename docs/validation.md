# Validation and release evidence

Tests validate contracts, not an absence of all possible defects. A successful generation reports structural checks; it does not invent live execution evidence.

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
