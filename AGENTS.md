# Repository guidance

This repository implements skillstate-kit, an independent compiler and runtime for portable agent skill state.

- Read relevant code/tests before changing behavior.
- Use `uv sync --locked --extra dev` for development.
- Run `uv run ruff check src tests examples` and `uv run ruff format --check src tests examples`.
- Run targeted tests, then `uv run pytest --cov=skillstate --cov-fail-under=85` for release validation.
- Preserve operation uncertainty, revision checks, source integrity and user-owned configuration.
- Clearly label scripted models. Never fabricate live integration, benchmark or platform test results.
- Route CLI and MCP mutations through shared services instead of duplicating state logic.
- Planning notes in `docs/research/` are proposals. Public documentation must describe implemented behavior.
