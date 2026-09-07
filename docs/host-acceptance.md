# Host acceptance — 2026-09-07

This exercise used a new local workspace and a synthetic invoice with line totals
10, 20 and 30 EUR. The baseline server was installed from public PyPI 0.1.1 into
a separate, non-editable environment. New Claude Desktop connection code was
then exercised from the development checkout. No production data was used.

| Host/surface | Observation | Verdict |
|---|---|---|
| Installed Codex CLI, actual model | Eight successful MCP calls; invoice total and artifact persisted; owner transferred to claude-desktop | First review and handoff passed |
| Two additional independent Codex CLI model sessions | Source-bound semantic generation, first review/handoff, new-session second review and completion | Generation and cross-session continuation passed |
| Claude Desktop 1.46388.4.0, Chat | After the initial permission/timeout interruption, resumed the existing run, saved second-review evidence and completed at revision 4; independently checked in the store | Codex-to-Claude continuation passed for this fixture |
| Claude Desktop Cowork/Code | App displayed a reserved internal server name warning for this local entry | Not supported by this tested connection |
| Antigravity desktop, Gemini 3.8 Flash High | Opened the project; model reported MCP tools unavailable; no skill or run was created | Requested MCP task failed |
| Separate Antigravity IDE | Login/onboarding screen, including optional migration dialog | No model task executed |
| Claude Code standalone | Not separately exercised | No live claim |

## Independently checked Codex handoff checkpoint

- Run: `desktop-acceptance-01`; revision **3**; owner `claude-desktop`.
- Status: **ready**, no pending operation; deliberately not completed.
- Invoice `INV-DEMO`; calculated total **60 EUR**.
- Evidence artifact: `3324d313470e08682bd6dd9aab6ce24cc357ae4bd5de593bdd04005a4147fd60`.
- Successful calls: `run_open`, `run_context`, `run_update`, `artifact_put`,
  `run_context`, `run_update`, `run_context`, `run_handoff`.
- A fresh process read the persisted run after the Codex process ended. The
  handoff did not depend on keeping its original conversation alive.

An initial connection attempt timed out before completion. A subsequent run-context and artifact verification established successful continuation without resetting the run. Host tool authorization remains part of normal setup.

### Successful Claude Desktop continuation

Claude Desktop completed a second review. A separate process using the public
package read the canonical run,
event history and both integrity-checked artifacts to verify that report:

- Run `desktop-acceptance-01`: **completed**, revision **4**, owner `claude-desktop`.
- `active_step=done`; all five steps completed; no blockers, pending operation
  or source drift.
- Invoice `INV-DEMO`, currency `EUR`, total `60`; second-review verdict **PASS**.
- Second-review artifact:
  `e72e02efac3580b5d88a60b7f7a42ec4f9d1c5f0b9e279740da9da0bcd8aeb3b`.
- Both artifact contents agree on `10 + 20 + 30 = 60`. The second artifact cites
  the first and identifies `claude-desktop` as reviewer.
- The run's five events show creation by Codex, two updates, ownership handoff
  to Claude Desktop, then completion. No reset or replacement run was recorded.

This validates the representative Codex-to-Claude Desktop Chat workflow,
including continuation after an interrupted attempt. Native facts remain
agent-reported; the test independently verifies persistence, arithmetic and
artifact integrity, not arbitrary external business outcomes. Antigravity and
the other Claude surfaces retain their separate limitations below.

Antigravity wrote its own final diagnostic reporting unavailable tools. Its
local tool cache contained the 12 server schemas, but that did not prove the
model received callable tools. This distinction matters: generated files,
discovery caches, actual calls and task completion are separate evidence levels.

## Fixes and reproducibility

### Additional semantic generation and independent-session completion

Codex subsequently used `generation_prepare` and `generation_apply` to generate
`invoice-semantic` from the actual SKILL.md. Its schema required a fixed invoice
ID/currency, a numeric total bounded from 0 to 60, an explicit review status and
bounded evidence references. The source fingerprint was
`ab8ffbe1c70011ab42a0c753449e1c68ca45cd962bc74930564e398db7d4ab40`.

The first session opened `codex-semantic-01`, recorded 60 EUR and an evidence
artifact, then transferred ownership to `codex-reviewer` at revision 2. A fresh,
independent model session read the stored context and artifact, checked the
arithmetic and completed the run at **revision 3**, with
`review_status=second_review_complete`. It added a second evidence artifact.

A separate verification process, using **0.1.2 installed from public PyPI**,
asserted completed status, owner, revision, total, no pending operation, both
artifact contents, and four persisted events. It also exercised the published
desktop connect/doctor/disconnect commands against an isolated app config,
confirming that unrelated preferences were preserved. This is a completed
Codex-to-Codex continuation test; it does not change the Claude/Antigravity
results above.

The exercise exposed missing Claude Desktop setup and an ambiguous `..` in the
root source directory instruction. Version 0.1.2 adds a reversible desktop
connection, config ownership/conflict checks, Windows Store path detection,
doctor checks and an unambiguous source directory. Regression tests cover
preservation, multiple projects, modified entries, config ambiguity and write
failure rollback.

The portable [sample project](../examples/desktop_acceptance/README.md) documents
both prompts and independent state/event checks. Host behavior remains subject
to its installed version, account, model and permissions. These observations do
not establish paper benchmark reproduction or universal task reliability.

Local validation before release included the complete test suite, the 85%
statement/branch coverage gate, formatting/lint, wheel/sdist metadata validation,
and a clean wheel installation with an actual 12-tool STDIO MCP handshake.
The release workflow reruns the full OS/Python matrix before publishing.
