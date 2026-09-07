<p align="center">
  <img src="docs/assets/logo.svg" alt="skillstate-kit — State that survives the next session." width="1040">
</p>

<p align="center">
  <a href="https://pypi.org/project/skillstate-kit/"><img src="https://img.shields.io/pypi/v/skillstate-kit?color=246b52" alt="PyPI version"></a>
  <img src="https://img.shields.io/badge/Python-3.11%2B-246b52" alt="Python 3.11 or newer">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-246b52" alt="MIT license"></a>
  <img src="https://img.shields.io/badge/Status-Alpha-b76538" alt="Alpha release">
</p>

<p align="center">
  <a href="https://pypi.org/project/skillstate-kit/">PyPI</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#python-integration">Python example</a> ·
  <a href="docs/README_TR.md">Türkçe</a> ·
  <a href="docs/host-acceptance.md">Verified integrations</a>
</p>

# skillstate-kit

**Portable execution state for AI agents.**

Keep task progress, observations, evidence and operation outcomes outside conversational history. Use the same Python engine through the SDK, CLI or MCP, with project integrations for Codex and Claude.

[PyPI](https://pypi.org/project/skillstate-kit/) · [Documentation](docs/integrations.md) · [Research alignment](docs/paper-alignment.md) · [Validation](docs/validation.md)

## Quick start

Requires Python 3.11 or newer. Run inside the project you want to integrate:

```bash
python -m pip install -U "skillstate-kit[mcp]"
skillstate init
skillstate doctor --mcp
```

Restart or reload your agent's project discovery, then give it a normal task:

> Implement duration parsing and verify it with regression tests.

Installed instructions guide the agent to find the intended run, continue from current state, record evidence and validate completion. Host support and instruction-following remain necessary. No custom Python agent is required for this integration.

The base `pip install skillstate-kit` also supports `skillstate init` using the CLI. MCP is an optional extra; `http` adds a stateless JSON model adapter.

## Choose the state model

| Requirement | Interface |
|---|---|
| Track a multi-step coding task | Built-in task profile with evidence-backed milestones |
| Represent domain facts and procedural rules | Generate a task-specific semantic skill schema |
| Control every model input and registered tool call | Python `SkillRuntime` with a stateless model callback |

The task profile records the goal, active/completed/remaining steps, blockers and artifact references. It does not replace a domain model for inventory, invoices or other business rules.

### Use an existing skill

```bash
skillstate generate skills/qa/SKILL.md --name qa-state --install
skillstate validate qa-state
```

Replace the source path with your existing file. Direct generation preserves instructions and adds tracking state. For domain-specific fields, use the installed `generate-skill-state` skill or the source-bound `--prepare` / `--proposal` workflow. Generated proposals undergo structural and source-integrity checks; generation does not execute or certify the task.

For Python test tracking without an existing skill file:

```bash
skillstate generate . --profile python-tests --name tests-state --install
```

See the [generation and CLI reference](docs/cli.md).

## Task lifecycle

```text
Find intended run → Read current state → Execute active work
                         ↑                       ↓
                    Continue ← Record verified milestone
                                      ↓
                           Validate and complete
```

- `task_start` creates an ordered plan or resumes an identical intended task.
- `task_checkpoint` records artifact-backed milestones and resource fingerprints.
- Repeating a completed milestone requires an explicit revalidation reason.
- `task_complete` checks required steps, evidence integrity, freshness and blockers.
- Generic task updates can change blockers; they cannot replace milestone progress.
- Pending or uncertain operations require reconciliation before further work.

Inspect progress with `skillstate run find` and `skillstate run context RUN_ID`.
Use `skillstate run events RUN_ID` for audit history. An intentionally new task
needs a new run ID; resuming an existing task never requires resetting it.

Evidence validates what was recorded and whether referenced resources changed.
Applications must still verify business outcomes. Native host tools are not
universally intercepted or sandboxed by this library.

## Host integrations

| Host | Project setup |
|---|---|
| Codex | `skillstate init --host codex --mcp` |
| Claude Code | `skillstate init --host claude-code --mcp` |
| Claude Desktop Chat | `skillstate connect claude-desktop` |
| Antigravity | `skillstate init --host antigravity --mcp` |

`skillstate hosts detect` reports discovery evidence. `skillstate doctor codex`
checks a selected adapter. Claude Desktop uses a separate application-level
connection and requires a full restart. Keep machine-specific MCP configuration
local. Detection or a healthy local server does not establish live host acceptance.

Installation preserves unrelated configuration and managed instruction blocks.
`skillstate disconnect HOST` removes owned integration settings while retaining
state. [Setup, thin plugins and host limitations](docs/integrations.md).

## Python integration

This runnable example uses a **scripted model and a simulated tool**. It requires
no credentials. Replace the callbacks with your application integrations:

```python
import asyncio

from skillstate import Skill, SkillRuntime, SQLiteStore, Tool, ToolResult

async def main():
    skill = Skill(
        "record-job",
        "Record the job; finish after its result is confirmed.",
        {
            "type": "object",
            "properties": {"recorded": {"type": "boolean"}},
            "required": ["recorded"],
            "additionalProperties": False,
        },
        {"recorded": False},
    )

    def model(context):
        if context["state"]["recorded"]:
            return {"patch": [], "action": None, "done": True}
        return {
            "patch": [{"op": "set", "path": "/recorded", "value": True}],
            "action": {"name": "record", "arguments": {}},
            "done": False,
        }

    def record(arguments, operation_id):
        return ToolResult(True, {"recorded": True, "operation_id": operation_id})

    tool = Tool("record", "Record a job", {"type": "object", "additionalProperties": False}, record)
    with SQLiteStore() as store:
        store.create("example", skill, "worker", {"job": "example"})
        runtime = SkillRuntime(store, model, [tool], completion_check=lambda s: s["recorded"])
        result = await runtime.run("example", "worker")
        print(result["status"], result["state"])

if __name__ == "__main__":
    asyncio.run(main())
```

Expected output:

```text
completed {'recorded': True}
```

Replace `model(context)` with your synchronous or asynchronous model callback, and `record` with a real tool that checks its result. Forward `operation_id` to the external service's idempotency facility when supported.

The example uses an in-memory store for easy reruns. Use `SQLiteStore("jobs.sqlite3")` for durable storage. Create each run once; resume by reopening that database and calling `runtime.run` with the existing run ID and owner. See the [runnable source](examples/managed_runtime.py) and [runtime contract](docs/architecture.md).

### Model decision contract

```json
{
  "patch": [{"op": "set", "path": "/recorded", "value": true}],
  "action": {"name": "record", "arguments": {}},
  "done": false
}
```

Finish with `{"patch": [], "action": null, "done": true}`. State updates use explicit `set`/`delete` operations and JSON Pointer paths. Setting `null` does not delete a key. No reasoning-trace field is accepted.


## Execution guarantees and boundaries

| Concern | Contract |
|---|---|
| Invalid decisions | Validate state patches and registered tool arguments before effects |
| Concurrent writes | Reject stale revisions and wrong owners |
| Failed or uncertain tools | Preserve the checkpoint; require explicit reconciliation when uncertain |
| Completed task progress | Use evidence-backed lifecycle calls and explicit revalidation |
| Application context | Enforce byte budgets; keep audit history outside ordinary model context |
| Persistence | Shared SQLite store, immutable skill definitions and integrity-checked artifacts |

The managed runtime supplies current instructions, state and latest observation
plus fixed tool/schema contracts. A stateless model callback is required to avoid
reintroducing history. Native Codex/Claude integrations retain the host's own
conversation behavior and do not guarantee lower provider token usage.

Owner IDs coordinate trusted local clients; they are not authentication. Python
callbacks run with application permissions. SQLite cannot atomically roll back
remote side effects. [Security boundaries](SECURITY.md) · [Execution contract](docs/execution-state.md).

## Validation and performance

The test suite covers schema rejection, persistence, concurrent revisions,
uncertain operations, artifact integrity, installer preservation and real MCP
transport. See [release validation](docs/validation.md) for exact tested versions.

Reproducible experiments are documented separately:

- [External smolagents correctness and forced-process continuation](docs/smolagents-acceptance.md).
- [Paired Codex coding experiment: correctness, repeated work, actual tokens and latency](docs/benchmarks/coding-agent.md).
- [Host acceptance and scope](docs/host-acceptance.md).

The recorded small coding trial incurred additional token and latency overhead.
Performance depends on workload and host behavior; universal savings are not claimed.

## Research

Independent implementation inspired by [SKILL.state: Scalable Long-Horizon Agent Skills](https://arxiv.org/abs/2608.26263), by Sanket Badhe, Priyanka Tiwari and Jonghyun Chung. No affiliation or endorsement is implied.

The [research alignment document](docs/paper-alignment.md) distinguishes the managed runtime from native-host integration, maps implemented contracts to tests and records intentional differences. Paper benchmark results are not claimed for this package.

## Development

```bash
python -m pip install uv
uv sync --locked --extra dev
uv run ruff check src tests examples scripts
uv run ruff format --check src tests examples scripts
uv run pytest --cov=skillstate --cov-fail-under=85
uv run python -m build
uv run twine check dist/*
```

Python/OS tests and clean-package checks run in CI. The package is alpha.
[MIT license](LICENSE) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [Security reporting](SECURITY.md).
