# Command-line guide

Commands return JSON on stdout. Runtime/domain errors return a structured object on stderr with exit code 2; filesystem/storage errors return 3. `doctor` returns 1 when checks fail. Argument parsing errors follow argparse conventions. Put `--project PATH` before the subcommand; default project is the current directory.

## Install and generate

```text
skillstate init --host codex --host claude-code --host antigravity --mcp
skillstate generate skills/qa/SKILL.md --name qa-state --install
skillstate validate qa-state
skillstate doctor --mcp
```

Omit `--mcp` for CLI-only host usage. Omit host flags to install all three project adapters. `init` remains project-local; no hooks are installed.

### Claude Desktop Chat connection

```text
skillstate connect claude-desktop
skillstate doctor --mcp
skillstate disconnect claude-desktop
```

`connect` explicitly merges an app-wide MCP entry for this project. It requires
the `mcp` extra and reports the config path and server name. Fully quit/reopen
Claude Desktop and use Chat; allow only the tool calls you intend to authorize.
Pass `--config PATH` when auto-detection is ambiguous or your platform uses a
custom location. `disconnect` uses the saved receipt and retains all run data.
It refuses to remove user-modified entries. `uninstall` does not perform this
separate desktop disconnection. See [compatibility](compatibility.md) for the
tested platform/surface limitations.

`generate` defaults to bounded tracking state while preserving the source instructions. For a Python project, `--profile python-tests` supplies test-oriented tracking instructions. It scans AST without importing project modules. Multiple source SKILL.md files require selecting one; it does not silently combine unrelated skills.

Supported scanning includes Markdown, Python, TOML, YAML and JSON. Root `.gitignore` and `.skillstateignore` patterns apply. Nested ignore files are not interpreted in this release. Limits: 128 files, 96 KB/file, 512 KB total. Narrow large projects rather than uploading them wholesale. Excluded files include environments, builds, known secret files and generated wrappers.

### Host-assisted semantic generation

```text
skillstate generate skills/qa/SKILL.md --prepare
```

The JSON response contains an inventory, source_hash and proposal_schema. Ask the active agent to produce a matching proposal, save it within the project as `proposal.json`, then apply:

```text
skillstate generate skills/qa/SKILL.md --proposal proposal.json --source-hash HASH_FROM_PREPARE --install
```

Each proposed step references existing source paths. Source changes invalidate the prepared hash. Successful application reports `statically_checked`; it does not claim the generated behavior has been executed.

### Configured model generation

Install `skillstate-kit[http]`, configure a JSON-compatible endpoint/model, and optionally set `SKILLSTATE_API_KEY` in your environment:

```text
skillstate generate skills/qa/SKILL.md --base-url http://localhost:11434/v1 --model YOUR_JSON_CAPABLE_MODEL --install
```

The endpoint must support chat-completions `messages`, a string content response and `response_format=json_object`. This is a protocol adapter, not a claim that every provider/model implements these features. The localhost address is an example, not an automatically installed model. `--api-key-env NAME` changes the environment variable used. Credentials are never taken from IDE sessions. HTTP generation has no implicit retries or hidden history.

## Native run lifecycle

Create `task.json` with the task observation. Then:

```text
skillstate run open qa-state --owner codex --id qa-001 --observation task.json
skillstate run context qa-001
```

Context reports the revision, owner, status, pending operation and source drift. Its nested context contains instructions/schema/current state/latest observation.

An observation-only update uses a patch file:

```json
[{"op":"set","path":"/goal","value":"Verify checkout"}]
```

```text
skillstate run update qa-001 --owner codex --revision 0 --patch patch.json
```

If you omit `--observation`, the native update sets the latest observation to null. Supply it when that observation must remain available. Refresh context after each write.

### External actions

Reserve before the native host executes the authorized action. `decision.json`:

```json
{"action":{"name":"run_tests","arguments":{}},"patch":[{"op":"set","path":"/facts","value":{"tests":"passed"}}]}
```

```text
skillstate run reserve qa-001 --owner codex --revision 1 --decision decision.json
```

The proposed state stays uncommitted. Execute the actual host tool and record its real outcome. On success, `result.json` might contain:

```json
{"success":true,"observation":{"exit_code":0,"tested_revision":"your-source-revision"}}
```

```text
skillstate run result OPERATION_ID --owner codex --result result.json
```

Native reservations do not execute the tool or supply its authorization/argument schema. The host/application remains responsible. Use the managed SDK for centrally registered tool contracts.

If the outcome is ambiguous:

```text
skillstate run unknown OPERATION_ID --owner codex --reason "Response was lost"
```

After checking the external system, record a verified observation with `run result ... --reconcile`. Do not set success merely to unblock the run. If an external action might still be in progress, wait or use its cancellation/recovery procedure.

### Finish, hand off, inspect

```text
skillstate run update qa-001 --owner codex --revision CURRENT --patch patch.json --done
skillstate run handoff OTHER_RUN --owner codex --revision CURRENT --to claude-code
skillstate status
skillstate run events qa-001 --after 0
```

Handoff requires an idle, nonterminal run without source/definition drift. `CURRENT` is the integer revision returned by the latest read. Completed runs cannot be handed off for further execution.

## Artifacts and diagnostics

```text
skillstate artifact put output.txt
skillstate artifact read ARTIFACT_HASH --offset 0 --length 4000
skillstate doctor
skillstate doctor --mcp
skillstate serve
skillstate uninstall
```

Artifact paths must be within the project. Reads allow up to 8,000 characters. `doctor --mcp` negotiates a real local STDIO connection and calls a status tool; it does not certify the IDE's skill discovery. `uninstall` removes only unmodified managed skill files/config entries and retains all state/artifacts.
