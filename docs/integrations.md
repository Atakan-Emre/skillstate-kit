# Host integrations

The Python engine owns state. Hosts own their model, conversation, permissions
and native tools. Installation encourages lifecycle use; it cannot force a host
model to obey instructions or remove its native transcript.

## Recommended installation

Use Python 3.11+ in the target project's virtual environment. Select the host
explicitly for predictable setup; replace `codex` with `claude-code` or
`antigravity` when appropriate:

```bash
python -m pip install -U "skillstate-kit[mcp]"
skillstate init --host codex --mcp
skillstate doctor codex
skillstate doctor --mcp
```

Reload the host's project discovery afterward. `doctor codex` checks the chosen
installation; `doctor --mcp` checks project configuration and the actual local
MCP transport. Neither substitutes for a live host task.

For multiple hosts, repeat the flags in one command:
`skillstate init --host codex --host claude-code --mcp`.
Claude Desktop Chat uses `skillstate connect claude-desktop` instead of an init
host flag. It is a separate application connection.

## CLI-only and automatic setup

```bash
python -m pip install skillstate-kit
skillstate init
skillstate doctor
```

`init` detects supported executables/project configurations and installs the
`generate-skill-state` and `skillstate-task` skills. If no project host can be
found, it installs the three existing offline project templates. Output is JSON
for compatibility with existing callers. No interactive prompt blocks automation.
Only the listed project files are managed. `init --host codex` and the other
explicit flags continue to work. Use `--no-mcp` to select CLI-only integration.

The base package works through CLI instructions. For MCP, install the optional
extra and rerun setup:

```bash
python -m pip install "skillstate-kit[mcp]"
skillstate init --mcp
skillstate hosts detect
```

Without explicit host flags, `init` enables MCP when its extra is already
installed. Explicit host flags retain the historical opt-in `--mcp` behavior.
Detection is filesystem/PATH evidence, not authentication or live-host testing.

| Command | Selection | MCP behavior |
|---|---|---|
| `init --host codex --mcp` | Codex only | Add/update its MCP entry |
| `init --host codex --no-mcp` | Codex only | Install CLI skills; add no MCP entry |
| `init` | Detected project hosts; all three templates if none detected | Add MCP if the extra is installed |
| `connect codex` | Codex only | MCP-enabled setup alias |
| `generate SOURCE --install` | Previously selected project hosts; all three if no selection exists | Install wrappers; add no MCP entry |

Setup is additive. Omitting `--mcp` or using `--no-mcp` does **not** remove an
existing MCP entry. To switch an existing host to CLI-only, run
`skillstate disconnect codex`, inspect any retained-file warnings, then run
`skillstate init --host codex --no-mcp`.

Generated wrapper installation respects recorded host selection from 0.2.2.
Do not use bare `init` when only one specific host should be configured.
Host-specific `doctor` requires a recorded installation. For a legacy 0.1.x
receipt, rerun explicit `init` to record the selected host. Detection alone is
not an installation receipt. If earlier automatic setup installed unwanted hosts,
remove them with `skillstate disconnect HOST` before continuing.

## Upgrade and remove

Upgrade the package in the same virtual environment, then rerun the same explicit
setup command to refresh the managed skills and local interpreter paths:

```bash
python -m pip install -U "skillstate-kit[mcp]"
skillstate init --host codex --mcp
skillstate doctor --mcp
```

`disconnect HOST` removes that host's owned integration content. `uninstall`
removes all project integrations; Desktop must be disconnected separately.
Both preserve task state. Modified user files are retained and listed. Empty
directories or configuration sections can remain intentionally; they do not
represent an active server. Do not delete `.skillstate/local/` to reinstall.

Plugin assets are optional. Choose either normal project skills or a plugin as
the instruction-distribution path to avoid duplicate discovery. See
[plugin distribution](../integrations/README.md).

## Codex

`skillstate init --host codex --mcp` installs the two skills under `.agents/skills/`,
merges `.codex/config.toml`, and adds a marked lifecycle block to `AGENTS.md`.
Existing instructions and unrelated MCP entries are preserved. After reloading
host discovery, a normal request such as “Implement duration parsing for this
project” can lead the host through the lifecycle without the user naming MCP tools.

The instruction block directs the host to inspect compatible runs before work,
read authoritative state, preserve completed milestones, record actual evidence
and validate completion. It does not silently choose the latest run or another
owner's run. Automatic skill selection remains host/model behavior.

`skillstate doctor codex` inspects the Codex integration. `skillstate disconnect
codex` removes its unmodified managed content while preserving the state and any
shared skills still used by Antigravity. `skillstate uninstall` removes all
project integrations, subject to conflict preservation.

Sources: [Codex skills](https://developers.openai.com/codex/skills/),
[Codex plugins](https://developers.openai.com/codex/plugins/).

## Claude Code

`skillstate init --host claude-code --mcp` writes `.claude/skills/`, merges the
project `.mcp.json`, and adds the same lifecycle policy to a marked `CLAUDE.md`
block. The runtime and database are identical to Codex's.

`skillstate connect claude-code` is an MCP-enabled setup alias;
`skillstate disconnect claude-code` reverses its managed project integration.
Use `skillstate doctor claude-code` to inspect it. Loading configuration is
separate from granting normal tool permissions and executing a real task.

A thin local plugin is also supplied; see [distribution assets](../integrations/README.md).
It contributes instructions, not a second implementation of state.

Sources: [Claude Code extensions](https://code.claude.com/docs/en/features-overview),
[plugin reference](https://code.claude.com/docs/en/plugins-reference).

## Claude Desktop Chat

Use `skillstate connect claude-desktop` for its separate app-wide MCP entry.
Auto-detection lists Desktop, but `init` does not silently modify the application's
settings. Fully quit/reopen the app and use Chat. Existing Windows Store handling,
project-specific server names and disconnect receipts remain supported.

Use the [existing Desktop acceptance exercise](../examples/desktop_acceptance/README.md).
Desktop Chat, Claude Code and Cowork are different integration surfaces; a pass
on one does not establish another.

## Handoff

Read current context, resolve pending/unknown outcomes and stale relevant evidence,
then use the existing command:

```bash
skillstate run handoff RUN_ID --owner codex --revision CURRENT_REVISION --to claude-code
```

The next host reads that same run in the same project. It does not recreate it
or need the previous transcript. Handoff does not synchronize files or databases
across machines. See the [coding-agent exercise](../examples/coding_agent/README.md)
for exact continuation prompts and independent checks.

## Compatibility and ownership

Old skill definitions and generic semantic run_update calls retain their contracts.
New evidence-backed task_* APIs are opt-in. SQLite remains at schema version 1.
No host-specific database is introduced. All sixteen MCP tools use the same service/store;
the twelve existing tool names/signatures are retained.

Instruction ownership uses marker-block hashes, not the entire user file hash.
Unrelated edits survive setup and removal. Editing the managed block itself causes
a conflict. Version 0.1.x installers do not understand the new instruction records;
use the 0.2 installer to disconnect before downgrading host integration files.
State databases and old bundles remain readable by the old core.
