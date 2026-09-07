# Real coding-agent acceptance

This fixture compares ordinary Codex execution with the installed SkillState
lifecycle on the same duration-parser task. Both may keep normal repository notes.
No scripted model decisions or mocked tools count as host acceptance.

Prerequisites: Python 3.11+, an authenticated Codex CLI supporting `exec --json`,
and this repository's development environment (`uv sync --extra dev`). Commands
below run from the repository root. Host runs consume the configured account's
usage. No model override is supplied: record your host/model version with results.

## Paired Codex run

Use a new work directory for every paired trial. The runner refuses to overwrite
existing boundary evidence. Run these eight commands in order:

```bash
uv run python examples/coding_agent/run.py --work .artifacts/coding-trial --mode baseline --boundary 2
uv run python examples/coding_agent/run.py --work .artifacts/coding-trial --mode baseline --boundary 4
uv run python examples/coding_agent/run.py --work .artifacts/coding-trial --mode baseline --boundary 6
uv run python examples/coding_agent/run.py --work .artifacts/coding-trial --mode baseline --boundary 8
uv run python examples/coding_agent/run.py --work .artifacts/coding-trial --mode skillstate --boundary 2
uv run python examples/coding_agent/run.py --work .artifacts/coding-trial --mode skillstate --boundary 4
uv run python examples/coding_agent/run.py --work .artifacts/coding-trial --mode skillstate --boundary 6
uv run python examples/coding_agent/run.py --work .artifacts/coding-trial --mode skillstate --boundary 8
uv run python examples/coding_agent/run.py --work .artifacts/coding-trial --summarize
```

Each command launches and terminates a fresh ephemeral Codex process. The original
task is supplied each time, with no previous conversation. Boundaries after stages
2/4/6 are planned stops, not abrupt mid-tool crashes. The existing smolagents
exercise separately covers forced process termination.

The integrated fixture receives project skills/instructions and an MCP server;
the ordinary task prompt does not tell the host which SkillState tools to invoke.
The host may use the CLI or MCP. Logs, per-session usage, checkpoints and
`summary.json` remain under the chosen work directory. Review raw logs before
sharing them; they can include local paths and account/model metadata.

The independent evaluator checks the feature outside the agent's test directory:

```bash
uv run python examples/coding_agent/evaluate.py .artifacts/coding-trial/skillstate
```

Search/read counts are shell-command pattern counts, not a complete filesystem
trace. Exact repeated commands can be legitimate verification. Actual
`turn.completed.usage` is reported when available; context bytes are never
converted into tokens. Costs default to unavailable. To estimate cost, supply
`--pricing pricing.json` with explicit `input_per_million`,
`cached_input_per_million`, `output_per_million` USD rates applicable to your model.

The [recorded experiment](../../docs/benchmarks/coding-agent.md) reports a single
paired trial and its limitations, including overhead rather than presumed savings.

## Claude Code: manual acceptance, not yet executed

The development machine did not have a `claude` executable. These instructions
are a reproducible procedure, **not passing live evidence**.

1. Copy only `fixture/` into a new empty directory outside existing workspaces.
   Keep [TASK.md](TASK.md) and the independent evaluator outside that directory.
2. In that project, install `skillstate-kit[mcp]` and run
   `skillstate init --host claude-code --mcp`, then `skillstate doctor --mcp`.
3. Start `claude` in the project and authorize the intended project MCP tools.
   Paste TASK.md followed by: "Complete stages through 2, then stop. Use owner
   claude-code. Follow project instructions; maintain evidence of actual results."
4. Exit Claude Code completely. Save `skillstate run find` and
   `skillstate run context RUN_ID`. Do not reset the run or reuse its ID for a new task.
5. Start fresh Claude Code processes, repeat TASK.md with "Continue from canonical
   project state through stage 4 [then 6, then 8]; no previous conversation is
   available." Save the context after each boundary.
6. Run the evaluator from this repository against that project, and run its tests
   using `python -m pytest -q -c /dev/null tests` (Windows: `-c NUL`). Require all
   independent checks and repository tests to pass. Check one run ID, increasing
   revisions, completed-step counts 2/4/6/8, valid evidence and final completed status.
7. Review host tool logs for unjustified replay; unchanged checkpoints alone do
   not prove that tools were never rerun. Report manual observation separately
   from measured calls/usage. Missing usage remains unavailable.

Optional thin plugin assets and the supported local Claude plugin command are
documented in [integrations](../../integrations/README.md).

## Codex to Claude Code handoff: manual acceptance

Use another fresh copy of the fixture and install both project adapters:

```bash
skillstate init --host codex --host claude-code --mcp
skillstate doctor --mcp
```

1. In Codex, paste TASK.md and ask: "Complete stages 1–3 only, using owner codex.
   Record evidence and stop before add-tests. Follow project instructions."
2. Exit Codex. Read `skillstate run find` and `skillstate run context RUN_ID`.
   Save that JSON outside the project as `before-handoff.json`.
3. Transfer using the actual revision just read:

   ```bash
   skillstate run handoff RUN_ID --owner codex --revision CURRENT_REVISION --to claude-code
   ```

4. Start Claude Code in the same directory. Paste TASK.md and ask: "Continue run
   RUN_ID as owner claude-code from canonical state, without the Codex transcript.
   Complete stages 4–6 and stop. Do not redo completed work without a documented
   validation reason." Exit and start a fresh Claude Code session for stages 7–8.
5. From this repository, run:

   ```bash
   uv run python examples/coding_agent/verify_handoff.py --project PATH_TO_FIXTURE --before PATH_TO_BEFORE_JSON
   ```

The read-only verifier checks the run ID, revision increase, recorded ownership
transition, absence of a reset, preserved earlier milestones, evidence freshness,
completion and independent output correctness. It conservatively fails if earlier
milestones changed; review justified revalidation separately rather than hiding it.
Also run the fixture's tests and review both hosts' tool logs for replay. A passing
SDK test of this protocol does not substitute for live Claude Code acceptance.
