# Host compatibility

## Supported integration surface

| Host | Skill output | Optional project MCP config | v0.1 scope |
|---|---|---|---|
| Codex | `.agents/skills/<name>/SKILL.md` | `.codex/config.toml` | Native CLI skill + STDIO MCP |
| Claude Code | `.claude/skills/<name>/SKILL.md` | `.mcp.json` | Native CLI skill + STDIO MCP |
| Antigravity | `.agents/skills/<name>/SKILL.md` | `.agents/mcp_config.json` | Native CLI skill + STDIO MCP |

The shared `.agents/skills` output is installed once for Codex/Antigravity. State is canonical in one project-local database, not copied into each host folder. These adapters target documented local discovery/configuration paths, not cloud or remote sessions.

Sources checked for this implementation: [Codex skills](https://learn.chatgpt.com/docs/build-skills), [Codex MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli), [Claude Code skills](https://code.claude.com/docs/en/skills), [Claude Code MCP](https://code.claude.com/docs/en/mcp), [Antigravity skills](https://www.antigravity.google/docs/ide/skills/), [Antigravity MCP](https://antigravity.google/docs/mcp).

## Setup

Run `skillstate init` in the target workspace after installing the package. Add `--mcp` only after installing the mcp extra. The installer merges a `skillstate-kit` server entry, preserves other entries, and refuses to overwrite a conflicting user-owned entry. Installed skills are checked by content hash on update/uninstall.

Local configs contain the absolute Python executable and project path used during installation. After moving the project or removing that environment, reinstall from the new environment. Do not commit machine-specific MCP config without adapting it to your team's supported path conventions. Protect `.skillstate/local/` with ignore rules.

If discovery does not refresh, reload/restart the host as its documentation requires. Respect its workspace/MCP trust policies. Use explicit skill invocation if natural language matching does not select the generator: Codex supports skill mentions; Claude Code supports `/generate-skill-state`; use the installed Antigravity skill selector/explicit invocation supported by your version.

## Verification levels

1. **Generated:** expected files/configuration exist.
2. **Validated:** managed content and configuration match.
3. **Transport tested:** actual SDK client/server initialize/list/call succeeds (`doctor --mcp`).
4. **Host discovered:** a real host lists/loads the installed skill/server.
5. **Behavior tested:** that host completes a representative task using the state protocol.

CI covers levels 1–3 and the shared state/handoff protocol. It does not impersonate the three host applications. The compatibility claim is for their documented interfaces; live results and omissions are recorded in [validation](validation.md).

## Boundaries

No hook installation is shipped in 0.1.0. Native tool interception and host transcript replacement are not promised. The generated skill asks the host to record state/operations, and compliant calls are enforced by the library. If the host skips the protocol, the library cannot reconstruct invisible effects.

Same-machine sequential handoff is supported. Different worktrees/projects use different stores by default. Cross-machine transfer, expiring leases and authenticated multi-tenant servers require additional implementation and tests.
