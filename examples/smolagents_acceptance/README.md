# smolagents SQL agent: before and after skillstate-kit

This is a real-model integration experiment using the existing
[Hugging Face smolagents SQL example](https://github.com/huggingface/smolagents/blob/30bb1161095dbae2271e6bc3cc4c219cc3897a57/examples/text_to_sql.py).
It runs the original question, a larger baseline task, semantic state generation,
and a managed run interrupted between operations and resumed in a new process.

See the [measured results](../../docs/smolagents-acceptance.md) and
[machine-readable evidence](../../docs/evidence/smolagents-2026-09-07.json).
No model answers are scripted. The receipt data is synthetic.

## What is integrated

- The upstream `CodeAgent` executes the baseline with its actual `sql_engine` tool.
- The managed run calls the same upstream tool through a `skillstate.Tool` handler.
- `generation_prepare`'s Python equivalent prepares the original source and task
  specification. A real model proposes the state schema; the compiler validates
  it against the source fingerprint before writing the bundle.
- `SkillRuntime` replaces the baseline execution loop. A file-backed SQLite
  store retains the state, latest observation and operation journal.
- Both modes use the same explicitly configured Codex CLI completion adapter.
  This adapter is test support, not an automatically installed model provider in
  skillstate-kit. It uses normal existing CLI authentication; it does not extract
  credentials or invoke Codex tools. Each completion starts an ephemeral session.

The upstream example's in-memory database needed `StaticPool` and
`check_same_thread=False` with this checkout's tool execution. The harness applies
that compatibility adjustment while loading the example; the upstream checkout
stays unchanged. The larger task uses one durable receipt database for both modes.

## Reproduce on Windows

Prerequisites: Python 3.11+, Git, and an installed, authenticated Codex CLI.
Real model calls consume the account's normal usage. The original run used
Python 3.12.7, SQLAlchemy 2.0.52 and smolagents 1.27.0.dev0 at the pinned commit.

From the skillstate-kit checkout, prepare an isolated environment:

```powershell
git clone https://github.com/huggingface/smolagents.git .test-workspaces/smolagents-upstream
git -C .test-workspaces/smolagents-upstream checkout 30bb1161095dbae2271e6bc3cc4c219cc3897a57
python -m venv .artifacts/smolagents-env
$acceptancePython = "$PWD/.artifacts/smolagents-env/Scripts/python.exe"
& $acceptancePython -m pip install ./.test-workspaces/smolagents-upstream "sqlalchemy==2.0.52" "skillstate-kit==0.1.2"
```

Set the path to your actual Codex executable and choose a **new work directory**
for each experiment. Do not reuse a completed run's directory.

```powershell
$codexExe = "C:/path/to/codex.exe"
$work = "$PWD/.artifacts/smolagents-reproduction-01"
$acceptanceArgs = @("--upstream", "$PWD/.test-workspaces/smolagents-upstream", "--work", $work, "--codex", $codexExe)
$runner = "examples/smolagents_acceptance/run.py"

& $acceptancePython $runner @acceptanceArgs original
& $acceptancePython $runner @acceptanceArgs baseline
& $acceptancePython $runner @acceptanceArgs generate
& $acceptancePython $runner @acceptanceArgs managed-start
# Expected: forced process exit 75 after the third committed SQL operation.
& $acceptancePython $runner @acceptanceArgs managed-resume
& $acceptancePython examples/smolagents_acceptance/verify.py --work $work --output "$work/summary.json"
```

Check each command's exit status before continuing. All commands except
`managed-start` should succeed. The verifier makes no model calls; it reads the
canonical database, compares both answers with a separate Decimal calculation,
checks operation IDs and query results, and inspects the actual resume inputs.

Model choices can differ between repetitions. This verifier intentionally checks
the published experiment's strict five-query/six-decision protocol; a different
trace should be investigated, not silently classified as equivalent success.

## Local evidence

The work directory contains the generated proposal and immutable bundle,
baseline report, interrupted checkpoint, final state, actual SQL queries and
results, and per-call inputs/outputs/measurements. These are excluded from Git.
Only the reviewed summary is committed. Completion logs can include model text;
review them before sharing them outside your machine.

The adapter measures the serialized application context in UTF-8 bytes. It does
not equate those bytes with billed tokens, latency or total Codex context.

## Scope

This demonstrates a working integration with one existing agent workflow in a
large external repository. It is not a conversion of every smolagents feature or
an automatic rewrite of arbitrary agent projects. The task instructions,
tool/model adapters and completion validator are explicit integration work.
SQL is read-only, and the injected interruption occurs after a committed result;
this experiment does not establish exactly-once external writes or universal
recovery from arbitrary process failures.
