# Real host acceptance exercise

Copy this directory into an empty local workspace. Use synthetic data throughout.
The two host conversations must share the same workspace, not different worktrees.

```console
python -m pip install "skillstate-kit[mcp]"
skillstate init --mcp
skillstate generate SKILL.md --name invoice-audit --install
skillstate doctor --mcp
```

For Claude Desktop **Chat**, additionally run `skillstate connect claude-desktop`
and fully quit/reopen the app. This is separate from Claude Code and Cowork.
Normal host tool approvals remain necessary. Do not disable host safeguards.

Ask the first host:

> Use the skillstate-kit MCP tools to open invoice-audit as owner codex, run ID
> invoice-test-01. Read context, calculate the invoice total, record the facts and
> a text evidence artifact, then hand off to owner claude-desktop. Do not complete
> the run. Report actual tool failures instead of simulating success.

Ask Claude Desktop Chat:

> Use the local skillstate MCP tools to read invoice-test-01 and its evidence.
> Independently check the arithmetic, record the second review as owner
> claude-desktop, then complete the run if all checks pass. Report its final
> revision, owner and status. Do not reset the run or invent tool results.

Verify outside the host conversations:

```console
skillstate run context invoice-test-01
skillstate run events invoice-test-01
```

The total must be 60 EUR, the artifact must contain the arithmetic, the owner
must be claude-desktop, and the status must be completed. The event stream must
show the initial review, handoff and second review. A chat answer alone does not
prove success. If a host stops for approval, status must remain incomplete.

To test generation by a host, ask it to generate a separate `invoice-semantic`
skill from SKILL.md using `generation_prepare` and `generation_apply`, citing
the returned source hash. Inspect the resulting schema and run it separately.

Disconnect the desktop entry with `skillstate disconnect claude-desktop`.
Run data is retained for inspection. `skillstate uninstall` only removes the
project host files it owns; it does not disconnect the app-wide desktop entry.
