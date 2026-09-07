# skillstate-kit

**Portable, validated execution state for agent skills.**

Convert an existing `SKILL.md` into a state-backed skill, retain durable checkpoints, and integrate the same execution engine into a Python application.

Python 3.11+ · MIT license · Initial alpha

## Install

```bash
python -m pip install "skillstate-kit[mcp,http]"
skillstate demo
```

The core package requires no model account. The demo uses an explicitly scripted model and local tools; it is not a benchmark of real-model performance.

Optional extras:

- `mcp`: a project-scoped STDIO MCP server and connection diagnostics.
- `http`: a stateless adapter for a configured JSON-compatible chat-completions endpoint.

## Use an existing skill

Run these commands in your target project. Replace `skills/qa/SKILL.md` with your existing skill file:

```bash
skillstate init --host codex --host claude-code --host antigravity --mcp
skillstate generate skills/qa/SKILL.md --name qa-state --install
skillstate validate qa-state
skillstate doctor --mcp
```

After your host discovers the installed `generate-skill-state` skill, ask it to generate state from an existing skill and install the result. Invoke the generated `qa-state` skill to run the procedure with checkpoints. Generating a definition does not execute the task.

`generate` preserves the source procedure and adds bounded progress fields. Domain-specific generation uses the active agent's proposal:

```bash
skillstate generate skills/qa/SKILL.md --prepare
skillstate generate skills/qa/SKILL.md --proposal proposal.json --source-hash HASH_FROM_PREPARE --install
```

The preparation response contains source text, its fingerprint and the proposal schema. The agent writes `proposal.json`; the library validates it and refuses stale source fingerprints. Structural validation is not proof that every business rule is correct.

You can also supply an explicitly configured endpoint with `--base-url` and `--model`. Terminal commands do not borrow your IDE's model credentials.

## Claude Desktop Chat

Version 0.1.2 adds an explicit local connection, separate from Claude Code:

```console
skillstate connect claude-desktop
skillstate doctor --mcp
```

Fully quit and reopen Claude Desktop, use **Chat**, and approve the tool calls you intend to allow. The installer preserves unrelated settings and uses a separate server name per project. Windows standalone/Microsoft Store and macOS paths are supported; `--config PATH` selects a custom location. If two Windows configs exist, choose explicitly. Disconnect with `skillstate disconnect claude-desktop`; run data remains intact.

Live acceptance evidence: Codex used eight real MCP calls to record a synthetic invoice review and hand it to Claude Desktop. Desktop discovered the server and requested tool permission; the second review was not completed at the time of this release. The tested Antigravity desktop session reported MCP tools unavailable, and its separate IDE required login. Generated configuration and transport tests do not establish successful execution in those hosts. No claim of universal desktop compatibility is made.

## Python integration

This complete example uses a scripted model. Replace `model` and `record` with your own model and service functions:

```python
import asyncio
from skillstate import Skill, SkillRuntime, SQLiteStore, Tool, ToolResult

skill = Skill(
    name="record-job",
    instructions="Record the job, then finish after its result is confirmed.",
    state_schema={
        "type": "object",
        "properties": {"recorded": {"type": "boolean"}},
        "required": ["recorded"],
        "additionalProperties": False,
    },
    initial_state={"recorded": False},
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
    # For a real API, forward operation_id to its idempotency facility when
    # supported and inspect the actual response before reporting success.
    return ToolResult(True, {"recorded": True})

async def main():
    with SQLiteStore() as store:  # Pass a local file path for durable storage.
        store.create("job-001", skill, "worker")
        tool = Tool("record", "Record a job",
                    {"type": "object", "additionalProperties": False}, record)
        runtime = SkillRuntime(store, model, [tool],
                               completion_check=lambda state: state["recorded"])
        result = await runtime.run("job-001", "worker", max_steps=10)
        print(result["status"], result["state"])

asyncio.run(main())
```

For persistent storage, pass a database path to `SQLiteStore`. Reopen the same database and run ID to resume; creating a duplicate run is rejected.

## Execution contract

- Explicit `set`/`delete` patches with JSON Pointer paths, inline JSON Schema and UTF-8 size limits.
- State and tool arguments validated before a managed tool executes.
- Persistent operation intent before tool execution; atomic state, result and event commit afterward.
- Failed tools retain the prior state. Exceptions, timeouts and ambiguous results block replay until reconciliation.
- Revision checks prevent competing clients from silently overwriting each other.
- Immutable skill definitions, source drift detection and sequential owner handoff.
- Large text artifacts kept outside the active context.

Native host skills provide state and checkpoints. They do **not** replace host conversation history or intercept every native tool. Use the managed Python runtime with a stateless model for history-free model inputs.

SQLite does not make external APIs transactional. Owner names coordinate local clients; they are not authentication. The library validates reported results but cannot independently prove external business truth. Keep local state private and test recovery behavior for your application.

## Compatibility and documentation

Adapters generate project skill files and optional MCP configuration for Codex, Claude Code and Antigravity. They target documented integration surfaces. MCP protocol tests and configuration discovery do not certify every IDE version or live task.

The source distribution includes `docs/cli.md`, `docs/architecture.md`, `docs/compatibility.md`, `docs/validation.md`, `docs/README_TR.md` and runnable examples. Download the source archive from this package's files to read them offline. The development repository currently requires collaborator access.

## Research

An independent implementation inspired by [SKILL.state: Scalable Long-Horizon Agent Skills](https://arxiv.org/abs/2608.26263). Not affiliated with the paper's authors. The compiler, host adapters and operation journal are engineering extensions; no reproduction of the paper's benchmark scores or token savings is claimed.
