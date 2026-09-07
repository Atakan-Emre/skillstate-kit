"""Non-destructive, project-scoped host installation and capability diagnostics."""

from __future__ import annotations

import importlib.util
import shutil
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

import tomlkit

from .errors import ConflictError, ValidationError
from .jsonio import atomic_write, digest, dumps, loads, read_json, slug, within

HOSTS = ("codex", "claude-code", "antigravity")
BEGIN = "<!-- skillstate:begin -->"
END = "<!-- skillstate:end -->"
INSTRUCTION = (
    BEGIN
    + "\nFor multi-step tasks, use the skillstate-task skill: inspect compatible runs before starting, read canonical state, preserve completed work and evidence, and validate completion. Do not repeat completed work without a verification/drift/uncertainty/user reason. SkillState does not replace native chat history.\n"
    + END
)


def lifecycle_skill() -> str:
    from importlib.resources import files

    return files("skillstate").joinpath("assets/task-SKILL.md").read_text(encoding="utf-8-sig")


def instruction_block(text: str) -> str | None:
    if BEGIN not in text and END not in text:
        return None
    if text.count(BEGIN) != 1 or text.count(END) != 1 or text.index(END) < text.index(BEGIN):
        raise ConflictError("Ambiguous SkillState instruction markers")
    return text[text.index(BEGIN) : text.index(END) + len(END)]


BOOTSTRAP = """---
name: generate-skill-state
description: Generate skill state from an existing SKILL.md or project, validate its schema, and install portable state-backed skills. Use when asked to generate skill state, convert a skill to state, or set up skillstate-kit.
metadata:
  version: "1"
---
<!-- skillstate_generated: true -->

Use the installed `skillstate` CLI (or `python -m skillstate`) from the project root.
The user's instructions and existing authorizations take precedence over this skill.

For a state-tracking wrapper that preserves an existing procedure, run:
`skillstate generate path/to/SKILL.md --install`
This deterministic mode does not invent domain-specific business rules.

For a domain-specific state schema, run:
`skillstate generate path/to/source --prepare`
Read the returned source inventory and proposal schema. Draft a JSON proposal with
name, instructions, state_schema, initial_state, and steps. Each step must cite
existing source paths. Keep future-relevant facts, bounds, and completion checks;
do not invent tools, completed actions, or credentials. Use inline JSON Schema.
Write the proposal to a local JSON file, then run:
`skillstate generate path/to/source --proposal proposal.json --source-hash HASH --install`
Use the source_hash returned by prepare so a stale analysis cannot be applied.

Run `skillstate validate NAME` and `skillstate doctor` after installation. Resolve
reported errors; distinguish structural validation from actual execution tests.
Do not rewrite the original skill or change the user's unrelated agent settings.
The generated wrapper uses durable state; it does not remove the host's own chat history.
"""


def wrapper(name: str) -> str:
    slug(name)
    return f"""---
name: {name}
description: Execute the {name} procedure with durable, validated skill state and resumable checkpoints.
metadata:
  version: "1"
---
<!-- skillstate_generated: true -->

Use the user's current task and authorization. Run commands from the project root.
Use `skillstate` or `python -m skillstate`; do not edit state files by hand.

1. Run `skillstate validate {name}`. Resolve source drift before starting a new run.
2. List runs with `skillstate status`. Reuse only the intended run. Otherwise open
   one with `skillstate run open {name} --owner HOST --observation task.json`.
   Replace HOST with codex, claude-code, or antigravity. Output includes run_id.
3. Get `skillstate run context RUN_ID`. Follow the returned original instructions;
   resolve resource references relative to the source directory described there.
4. Before a tool with external effects, reserve its intent:
   `skillstate run reserve RUN_ID --owner HOST --revision N --decision decision.json`.
   The decision file contains exactly action (name, arguments) and patch (a list).
   Do not infer success before the tool completes. Execute only authorized tools.
5. Record its actual result with
   `skillstate run result OPERATION_ID --owner HOST --result result.json`.
   The file contains success (boolean) and observation. If the outcome is uncertain,
   run `skillstate run unknown OPERATION_ID --owner HOST` and reconcile before retrying.
6. For facts without an external action, use
   `skillstate run update RUN_ID --owner HOST --revision N --patch patch.json`.
   Patch uses set/delete with JSON Pointer paths. Null assignment is different from deletion.
7. Refresh context after each update; use its revision. Large outputs can be stored
   with `skillstate artifact put output.txt`. Keep future-relevant facts in state.
8. When the source procedure's completion checks pass, update with `--done`.
   To switch hosts, use `skillstate run handoff RUN_ID --owner HOST --revision N --to TARGET`.

Keep facts and hypotheses distinct. A native agent's reports are agent-reported
evidence, not independently verified tool results. Do not claim the host transcript
is replaced or that every native tool is automatically intercepted.
"""


def _manifest_path(project: Path) -> Path:
    return within(project, ".skillstate/local/install-record.json")


def _manifest(project: Path) -> dict:
    path = _manifest_path(project)
    data = read_json(path) if path.exists() else {"version": 1, "files": {}, "configs": {}}
    if (
        data.get("version") != 1
        or not isinstance(data.get("files"), dict)
        or not isinstance(data.get("configs"), dict)
    ):
        raise ValidationError("Unsupported installation manifest")
    return data


@contextmanager
def _lock(project: Path):
    path = within(project, ".skillstate/local/install-lock.sqlite3")
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10, isolation_level=None)
    try:
        db.execute("BEGIN IMMEDIATE")
        yield
        db.execute("COMMIT")
    finally:
        db.close()


def _config_entries(project: Path, hosts: list[str]) -> dict:
    # Local installation: absolute interpreter/project paths avoid PATH ambiguity
    # and support Windows spaces. These configurations must not be shared as-is.
    entry = {
        "command": sys.executable,
        "args": ["-m", "skillstate", "--project", str(project), "serve"],
    }
    result = {}
    if "codex" in hosts:
        result[".codex/config.toml"] = {"format": "toml", "section": "mcp_servers", "value": entry}
    if "claude-code" in hosts:
        result[".mcp.json"] = {"format": "json", "section": "mcpServers", "value": entry}
    if "antigravity" in hosts:
        result[".agents/mcp_config.json"] = {
            "format": "json",
            "section": "mcpServers",
            "value": entry,
        }
    return result


def _config_document(path: Path, format: str):
    text = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    if len(text.encode("utf-8")) > 512_000:
        raise ValidationError("Host configuration is too large")
    try:
        doc = tomlkit.parse(text) if format == "toml" else (loads(text) if text else {})
        if not isinstance(doc, dict):
            raise ValidationError("Host config must be an object")
        return doc
    except (ValueError, tomlkit.exceptions.ParseError) as exc:
        raise ValidationError(f"Cannot parse host config: {path.name}") from exc


def _commit(project: Path, changes: dict[str, str | None], manifest: dict) -> None:
    # Preflight happens before this call. Roll back write errors. Individual files
    # use atomic replacement; re-running init also converges after process death.
    originals = {}
    try:
        for relative, content in changes.items():
            path = within(project, relative)
            originals[relative] = path.read_bytes() if path.exists() else None
            if content is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, content)
        atomic_write(_manifest_path(project), dumps(manifest) + "\n")
    except BaseException:
        for relative, original in reversed(list(originals.items())):
            path = within(project, relative)
            if original is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, original)
        raise


def install(
    project: Path, hosts: list[str] | None = None, *, name: str | None = None, mcp: bool = False
) -> dict:
    project = project.resolve()
    hosts = list(dict.fromkeys(hosts or HOSTS))
    if any(host not in HOSTS for host in hosts):
        raise ValidationError("Unknown host")
    if mcp and importlib.util.find_spec("mcp") is None:
        raise ValidationError("Install skillstate-kit[mcp] before enabling MCP")
    skill_name, content = (name, wrapper(name)) if name else ("generate-skill-state", BOOTSTRAP)
    files = {}
    if "codex" in hosts or "antigravity" in hosts:
        files[f".agents/skills/{skill_name}/SKILL.md"] = content
    if "claude-code" in hosts:
        files[f".claude/skills/{skill_name}/SKILL.md"] = content
    if name is None:
        for relative in list(files):
            files[relative.replace("generate-skill-state", "skillstate-task")] = lifecycle_skill()
    with _lock(project):
        manifest = _manifest(project)
        manifest["hosts"] = list(dict.fromkeys([*manifest.get("hosts", []), *hosts]))
        changes = {}
        if name is None:
            instructions = manifest.setdefault("instructions", {})
            for host, relative in (("codex", "AGENTS.md"), ("claude-code", "CLAUDE.md")):
                if host not in hosts:
                    continue
                path = within(project, relative)
                if path.exists() and path.stat().st_size > 512000:
                    raise ValidationError("Project instruction file is too large")
                text = path.read_text(encoding="utf-8") if path.exists() else ""
                block = instruction_block(text)
                previous = instructions.get(relative, {})
                if block and digest(block) not in (digest(INSTRUCTION), previous.get("hash")):
                    raise ConflictError(f"User-modified instruction block: {relative}")
                updated = (
                    text.replace(block, INSTRUCTION)
                    if block
                    else text + ("\n\n" if text else "") + INSTRUCTION + "\n"
                )
                if updated != text:
                    changes[relative] = updated
                instructions[relative] = {
                    "hash": digest(INSTRUCTION),
                    "created": previous.get("created", not path.exists()),
                    "separator": previous.get("separator", "\n\n" if text else ""),
                }

        for relative, text in files.items():
            path = within(project, relative)
            existing_hash = digest(path.read_bytes()) if path.exists() else None
            if existing_hash not in (None, digest(text), manifest["files"].get(relative)):
                raise ConflictError(f"Refusing to overwrite user-modified skill: {relative}")
            if existing_hash != digest(text):
                changes[relative] = text
            manifest["files"][relative] = digest(text)
        configs = _config_entries(project, hosts) if mcp else {}
        for relative, entry in configs.items():
            path = within(project, relative)
            doc = _config_document(path, entry["format"])
            section = doc.setdefault(entry["section"], {})
            if not isinstance(section, dict):
                raise ValidationError("MCP config section must be a table/object")
            current = section.get("skillstate-kit")
            previous = manifest["configs"].get(relative, {}).get("value")
            if current is not None and current != entry["value"] and current != previous:
                raise ConflictError(
                    f"Existing skillstate-kit MCP entry belongs to the user: {relative}"
                )
            if current != entry["value"]:
                section["skillstate-kit"] = entry["value"]
                changes[relative] = (
                    tomlkit.dumps(doc) if entry["format"] == "toml" else dumps(doc) + "\n"
                )
            manifest["configs"][relative] = entry
        _commit(project, changes, manifest)
    return {
        "installed": skill_name,
        "hosts": hosts,
        "changed_files": list(changes),
        "mcp": mcp,
        "configuration_scope": "project-local",
        "next": "Run skillstate doctor; reload host skill/MCP discovery if needed.",
    }


def uninstall(project: Path, hosts: list[str] | None = None) -> dict:
    project = project.resolve()
    with _lock(project):
        manifest = _manifest(project)
        changes, retained = {}, []
        if hosts is not None and any(host not in HOSTS for host in hosts):
            raise ValidationError("Unknown host")
        remaining_hosts = set(manifest.get("hosts", HOSTS)) - set(hosts or HOSTS)

        def selected(relative):
            if relative.startswith(".agents/"):
                return not remaining_hosts.intersection({"codex", "antigravity"})
            if (
                relative.startswith(".claude/")
                or relative == ".mcp.json"
                or relative == "CLAUDE.md"
            ):
                return "claude-code" not in remaining_hosts
            return "codex" not in remaining_hosts

        for relative, record in list(manifest.get("instructions", {}).items()):
            if not selected(relative):
                continue
            path = within(project, relative)
            text = path.read_text(encoding="utf-8") if path.exists() else ""
            try:
                block = instruction_block(text)
            except ConflictError:
                retained.append(relative)
                continue
            if block and digest(block) != record["hash"]:
                retained.append(relative)
                continue
            if block:
                wrapped = record.get("separator", "") + block + "\n"
                updated = (
                    text.replace(wrapped, "", 1) if wrapped in text else text.replace(block, "")
                )
                changes[relative] = None if record["created"] and not updated.strip() else updated
            del manifest["instructions"][relative]
        manifest["hosts"] = sorted(remaining_hosts)
        for relative, fingerprint in list(manifest["files"].items()):
            if not selected(relative):
                continue
            path = within(project, relative)
            if path.exists() and digest(path.read_bytes()) != fingerprint:
                retained.append(relative)
                continue
            if path.exists():
                changes[relative] = None
            del manifest["files"][relative]
        for relative, entry in list(manifest["configs"].items()):
            if relative == ".agents/mcp_config.json" and "antigravity" in remaining_hosts:
                continue
            if relative != ".agents/mcp_config.json" and not selected(relative):
                continue
            path = within(project, relative)
            if path.exists():
                doc = _config_document(path, entry["format"])
                section = doc.get(entry["section"], {})
                if not isinstance(section, dict) or section.get("skillstate-kit") not in (
                    None,
                    entry["value"],
                ):
                    retained.append(relative)
                    continue
                section.pop("skillstate-kit", None)
                changes[relative] = (
                    tomlkit.dumps(doc) if entry["format"] == "toml" else dumps(doc) + "\n"
                )
            del manifest["configs"][relative]
        _commit(project, changes, manifest)
    return {
        "removed_or_updated": list(changes),
        "retained_modified_files": retained,
        "state_retained": True,
    }


def doctor(project: Path) -> dict:
    from .desktop import checks as desktop_checks

    project = project.resolve()
    manifest = _manifest(project)
    checks = []
    for relative, record in manifest.get("instructions", {}).items():
        path = within(project, relative)
        try:
            block = instruction_block(path.read_text(encoding="utf-8")) if path.exists() else None
            ok = block is not None and digest(block) == record["hash"]
        except (OSError, ConflictError):
            ok = False
        checks.append({"check": relative, "ok": ok, "kind": "lifecycle_instructions"})
    for relative, fingerprint in manifest["files"].items():
        path = within(project, relative)
        ok = path.is_file() and digest(path.read_bytes()) == fingerprint
        checks.append({"check": relative, "ok": ok, "kind": "managed_skill"})
    for relative, entry in manifest["configs"].items():
        path = within(project, relative)
        try:
            doc = _config_document(path, entry["format"])
            section = doc.get(entry["section"], {})
            ok = isinstance(section, dict) and section.get("skillstate-kit") == entry["value"]
        except ValidationError:
            ok = False
        checks.append(
            {
                "check": relative,
                "kind": "mcp_configuration",
                "ok": ok,
            }
        )
        command = entry["value"]["command"]
        checks.append(
            {
                "check": f"interpreter:{relative}",
                "kind": "executable",
                "ok": Path(command).is_file(),
            }
        )
    if manifest["configs"]:
        checks.append(
            {
                "check": "mcp dependency",
                "kind": "dependency",
                "ok": importlib.util.find_spec("mcp") is not None,
            }
        )
    checks.extend(desktop_checks(project))
    return {
        "ok": bool(checks) and all(check["ok"] for check in checks),
        "checks": checks,
        "host_executables": {
            host: shutil.which(binary)
            for host, binary in (
                ("codex", "codex"),
                ("claude-code", "claude"),
                ("antigravity", "agy"),
            )
        },
        "live_host_verified": False,
        "note": "File/config checks do not prove a host loaded the skill. Use doctor --mcp for a real protocol handshake, then verify a host session.",
    }
