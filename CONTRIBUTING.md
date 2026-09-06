# Contributing

Keep public contracts small, explicit and testable. New behavior should include a realistic failure case as well as a successful example. Do not add compatibility or benchmark claims that have not been measured.

## Setup

```bash
python -m pip install uv
uv sync --locked --extra dev
```

Run `uv run ruff check src tests examples`, `uv run ruff format --check src tests examples`, and `uv run pytest --cov=skillstate --cov-fail-under=85`. For packaging changes, also run `uv run python -m build` and `uv run twine check dist/*`.

## Invariants

- Validate candidate state before committing it.
- Reserve external operations before execution; never retry uncertain effects automatically.
- Keep SQLite transactions outside model/tool calls.
- Preserve the original observation during rejected-decision retries.
- Keep definitions immutable for existing runs.
- Preserve user-authored source and host configuration.
- Distinguish agent-reported evidence from observed tool results and business truth.
- Keep audit records outside context and enforce explicit budgets.

Describe the concrete problem, resulting behavior and validation in changes. Document protocol/schema migrations. Examples should run without credentials unless labeled otherwise. Keep optional integrations optional.

For host integrations, distinguish file generation, configuration validation, live MCP transport, live host discovery and actual agent behavior. Passing one level does not prove the others.

Do not commit credentials, real task data, machine-specific interpreter paths or research checkouts. Report security concerns through SECURITY.md.
