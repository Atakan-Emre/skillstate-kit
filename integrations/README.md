# Thin host distribution assets

The directories here contain host plugin manifests and lifecycle skills. They do
not contain a second execution engine, provider adapter, database, scheduler or
credential store. `scripts/build_integrations.py` builds them from the canonical
Python package instruction asset. Install the matching Python package first.

The supported minimal path is `pip install skillstate-kit` followed by
`skillstate init` inside the project. This installs discoverable project skills
without requiring a marketplace or custom Python agent.

## Claude Code local plugin

With Claude Code installed, its documented local plugin interface can load the
thin distribution for a session:

```bash
claude --plugin-dir /absolute/path/to/integrations/claude/skillstate-kit
```

Invoke `skillstate-kit:skillstate-task`, or let Claude discover it for an applicable
multi-step task. For MCP, install `skillstate-kit[mcp]` and run `skillstate connect
claude-code` in the project. The plugin does not embed a machine-specific project
path or assume that the plugin cache is the user's project.

## Codex distribution

`codex/skillstate-kit` contains a validated `.codex-plugin/plugin.json` and the same
skill. Marketplace publishers can package this folder using Codex's supported
plugin mechanism. This repository does not register or install a personal
marketplace on the user's behalf. `skillstate init --host codex` is the directly
supported installation path for this release.

Plugin manifest validation is distinct from a live installed-plugin acceptance
run. The coding acceptance exercise tests the project integration. Claude Code
must be tested in an environment with its executable/account available; do not
infer a pass from these files.

Sources: [Codex plugins](https://developers.openai.com/codex/plugins/),
[Claude Code plugin reference](https://code.claude.com/docs/en/plugins-reference).
