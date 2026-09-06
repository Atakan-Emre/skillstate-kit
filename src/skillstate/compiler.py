"""Source-preserving skill generation with deterministic and host-assisted paths."""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

import pathspec
import yaml

from .errors import BudgetExceeded, ConflictError, NotFoundError, SourceChanged, ValidationError
from .jsonio import atomic_write, digest, dumps, read_json, slug, within
from .models import Skill
from .schema import validate

EXCLUDED = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".skillstate",
    ".pytest_cache",
    ".ruff_cache",
    "research",
    "generate-skill-state",
}
SUFFIXES = {".md", ".py", ".toml", ".yaml", ".yml", ".json"}
SECRET_NAMES = {"credentials.json", "auth.json", "secrets.json", "package-lock.json", "uv.lock"}
IR_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["name", "instructions", "state_schema", "initial_state", "steps"],
    "properties": {
        "name": {"type": "string", "maxLength": 64},
        "instructions": {"type": "string", "minLength": 1, "maxLength": 32000},
        "state_schema": {"type": "object"},
        "initial_state": {"type": "object"},
        "steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": 64,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "description", "sources"],
                "properties": {
                    "id": {"type": "string", "pattern": "^[a-z0-9-]+$", "maxLength": 64},
                    "description": {"type": "string", "minLength": 1, "maxLength": 2000},
                    "sources": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 32,
                        "items": {"type": "string", "maxLength": 500},
                    },
                },
            },
        },
    },
}


def _redact(text: str) -> str:
    return re.sub(
        r"""(?im)(\b(?:api[_-]?key|access[_-]?token|password|secret)\s*[:=]\s*)["'][^"'\n]+["']""",
        r'\1"[REDACTED]"',
        text,
    )


def _source_allowed(path: Path) -> bool:
    return (
        path.suffix.lower() in SUFFIXES
        and path.name.lower() not in SECRET_NAMES
        and not path.name.lower().startswith(".env")
        and not any(part in EXCLUDED for part in path.parts)
    )


def scan(project: Path, source: str | Path = ".") -> dict:
    project = project.resolve()
    source_path = within(project, source)
    if not source_path.exists():
        raise NotFoundError("Source does not exist")
    patterns = []
    for name in (".gitignore", ".skillstateignore"):
        ignore_path = within(project, name)
        if ignore_path.is_file():
            if ignore_path.stat().st_size > 128_000:
                raise BudgetExceeded("Ignore file is too large")
            patterns.extend(ignore_path.read_text(encoding="utf-8").splitlines())
    ignore = pathspec.PathSpec.from_lines("gitwildmatch", patterns)
    candidates = []
    if source_path.is_file():
        candidates = [source_path]
    else:
        for base, dirs, names in os.walk(source_path, followlinks=False):
            dirs[:] = sorted(
                d
                for d in dirs
                if d not in EXCLUDED
                and not (Path(base) / d).is_symlink()
                and not ignore.match_file((Path(base) / d).relative_to(project).as_posix() + "/")
            )
            for name in sorted(names):
                path = Path(base) / name
                if _source_allowed(path.relative_to(project)) and not ignore.match_file(
                    path.relative_to(project).as_posix()
                ):
                    candidates.append(path)
                if len(candidates) > 128:
                    raise BudgetExceeded(
                        "More than 128 source files; narrow the source or add .skillstateignore"
                    )
    entries = []
    total = 0
    for candidate in candidates:
        relative = candidate.relative_to(project).as_posix()
        if not _source_allowed(Path(relative)) or ignore.match_file(relative):
            if source_path.is_file():
                raise ValidationError("Source is excluded or has an unsupported extension")
            continue
        path = within(project, candidate)
        size = path.stat().st_size
        if size > 96_000:
            raise BudgetExceeded(f"Source file exceeds 96000 bytes: {relative}")
        total += size
        if total > 512_000:
            raise BudgetExceeded("Source budget exceeds 512000 bytes; narrow the source")
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8-sig")
        except UnicodeError as exc:
            raise ValidationError(f"Source must be UTF-8: {relative}") from exc
        if "skillstate_generated: true" in text[:2000]:
            continue
        symbols = []
        if path.suffix == ".py":
            try:
                tree = ast.parse(text)
                symbols = [
                    {"name": node.name, "line": node.lineno, "kind": type(node).__name__}
                    for node in ast.walk(tree)
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                ]
            except SyntaxError:
                symbols = [{"parse_error": "Python syntax could not be parsed"}]
        entries.append(
            {"path": relative, "sha256": digest(raw), "text": _redact(text), "symbols": symbols}
        )
    if not entries:
        raise ValidationError("No supported source files found")
    manifest = [{"path": entry["path"], "sha256": entry["sha256"]} for entry in entries]
    return {
        "source": source_path.relative_to(project).as_posix(),
        "files": entries,
        "manifest": manifest,
        "source_hash": digest(dumps(manifest)),
    }


def _frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}, text
    parts = re.split(r"^---\s*$", text, maxsplit=2, flags=re.MULTILINE)
    if len(parts) < 3:
        raise ValidationError("Unclosed skill frontmatter")
    if "&" in parts[1] or "*" in parts[1]:
        raise ValidationError("YAML aliases are not supported in skill frontmatter")
    try:
        metadata = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        raise ValidationError("Invalid skill frontmatter") from exc
    if type(metadata) is not dict:
        raise ValidationError("Skill frontmatter must be an object")
    return metadata, parts[2].strip()


def tracking_ir(inventory: dict, name: str | None = None, profile: str = "auto") -> dict:
    files = inventory["files"]
    skill_files = [entry for entry in files if Path(entry["path"]).name == "SKILL.md"]
    if len(skill_files) > 1:
        raise ValidationError("Multiple skills found; generate one skill at a time")
    primary = skill_files[0] if skill_files else files[0]
    metadata, body = _frontmatter(primary["text"])
    if profile not in ("auto", "tracking", "python-tests"):
        raise ValidationError("Unknown generation profile")
    is_python = any(entry["path"].endswith(".py") for entry in files)
    if profile == "python-tests" and not is_python:
        raise ValidationError("python-tests profile requires Python source")
    base_name = str(metadata.get("name") or Path(primary["path"]).parent.name or "project")
    base_name = re.sub("[^a-z0-9]+", "-", base_name.lower()).strip("-")[:48] or "project"
    name = slug(name or base_name + "-state")
    # This adapter preserves the original procedure. It does not claim to infer
    # a domain-specific state machine from arbitrary prose.
    descriptions = re.findall(r"^\s*\d+[.)]\s+(.+)$", body, flags=re.MULTILINE)[:32]
    if not descriptions:
        descriptions = [
            "Inspect task inputs",
            "Execute the source procedure",
            "Verify and report the result",
        ]
    steps = [
        {"id": f"step-{i + 1}", "description": desc[:2000], "sources": [primary["path"]]}
        for i, desc in enumerate(descriptions)
    ]
    if profile == "python-tests":
        body = (
            "Inspect the Python project and its test configuration. Run the existing tests using "
            "the project's documented runner. Record observed failures, make task-authorized "
            "changes, rerun relevant tests, and provide evidence. Do not claim unexecuted tests passed."
        )
    instructions = (
        f"Source procedure: {primary['path']}. Resolve its resource paths relative to "
        f"{Path(primary['path']).parent.as_posix()}. Follow the user's current task and authorizations.\n\n"
        + body
        + "\n\nTrack active_step, completed_steps, facts, blockers and artifacts. "
        "Only mark steps complete after checking their results. Retain facts needed by later steps. "
        "Store large outputs as artifacts. The original source remains authoritative for procedure details."
    )
    state_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["goal", "active_step", "completed_steps", "facts", "blockers", "artifacts"],
        "properties": {
            "goal": {"type": "string", "maxLength": 2000},
            "active_step": {"enum": [s["id"] for s in steps] + ["done"]},
            "completed_steps": {
                "type": "array",
                "maxItems": len(steps),
                "uniqueItems": True,
                "items": {"enum": [s["id"] for s in steps]},
            },
            "facts": {
                "type": "object",
                "maxProperties": 32,
                "additionalProperties": {"type": "string", "maxLength": 1000},
            },
            "blockers": {
                "type": "array",
                "maxItems": 16,
                "items": {"type": "string", "maxLength": 500},
            },
            "artifacts": {
                "type": "array",
                "maxItems": 32,
                "items": {"type": "string", "maxLength": 200},
            },
        },
    }
    return {
        "name": name,
        "instructions": instructions,
        "state_schema": state_schema,
        "initial_state": {
            "goal": "",
            "active_step": steps[0]["id"],
            "completed_steps": [],
            "facts": {},
            "blockers": [],
            "artifacts": [],
        },
        "steps": steps,
    }


def prepare(project: Path, source: str | Path = ".", name: str | None = None) -> dict:
    inventory = scan(project, source)
    return {
        "protocol_version": 1,
        "inventory": inventory,
        "proposal_schema": IR_SCHEMA,
        "suggested_name": name,
        "instructions": (
            "Propose a SkillIR JSON object matching proposal_schema. Preserve the user's procedure. "
            "Reference existing inventory paths in each step's sources. Use inline draft 2020-12 "
            "state_schema and a valid initial_state. Bound collections and strings. Do not invent "
            "executed results, credentials, or tools. The proposal will be checked before writing."
        ),
    }


def generate(
    project: Path,
    source: str | Path = ".",
    *,
    name: str | None = None,
    profile: str = "auto",
    proposal: dict | None = None,
    expected_source_hash: str | None = None,
) -> dict:
    project = project.resolve()
    inventory = scan(project, source)
    if expected_source_hash is not None and inventory["source_hash"] != expected_source_hash:
        raise SourceChanged("Sources changed after generation_prepare; prepare again")
    ir = proposal if proposal is not None else tracking_ir(inventory, name, profile)
    validate(IR_SCHEMA, ir)
    if name is not None and ir["name"] != name:
        raise ValidationError("Proposal name differs from requested name")
    known = {entry["path"] for entry in inventory["files"]}
    ids = [step["id"] for step in ir["steps"]]
    if len(ids) != len(set(ids)):
        raise ValidationError("Step IDs must be unique")
    for step in ir["steps"]:
        slug(step["id"])
        if any(path not in known for path in step["sources"]):
            raise ValidationError("Step references a source outside the scanned inventory")
    skill = Skill(ir["name"], ir["instructions"], ir["state_schema"], ir["initial_state"])
    bundle = {
        "format_version": 1,
        "skill": skill.to_dict(),
        "steps": ir["steps"],
        "source": inventory["source"],
        "manifest": inventory["manifest"],
        "source_hash": inventory["source_hash"],
        "generation": {
            "mode": "semantic" if proposal is not None else "tracking",
            "validation": "statically_checked",
            "behaviorally_checked": False,
        },
    }
    # Content-addressed revisions keep already-running skills immutable.
    bundle_hash = digest(dumps(bundle))
    directory = within(project, f".skillstate/definitions/{skill.name}")
    path = within(project, directory / f"{bundle_hash}.json")
    if not path.exists():
        atomic_write(path, dumps(bundle) + "\n")
    elif read_json(path) != bundle:
        raise ConflictError("Existing content-addressed bundle was modified")
    atomic_write(within(project, directory / "latest.json"), dumps({"hash": bundle_hash}) + "\n")
    return {
        "name": skill.name,
        "bundle_hash": bundle_hash,
        "path": path.relative_to(project).as_posix(),
        **bundle["generation"],
    }


def load_bundle(project: Path, name: str, *, check_sources: bool = True) -> dict:
    directory = within(project, f".skillstate/definitions/{slug(name)}")
    pointer = within(project, directory / "latest.json")
    if not pointer.exists():
        raise NotFoundError(f"No generated skill: {name}")
    latest = read_json(pointer)
    fingerprint = latest.get("hash") if type(latest) is dict else None
    if not isinstance(fingerprint, str) or not re.fullmatch(r"[a-f0-9]{64}", fingerprint):
        raise ValidationError("Invalid bundle pointer")
    bundle = read_json(within(project, directory / f"{fingerprint}.json"))
    if digest(dumps(bundle)) != fingerprint:
        raise ValidationError("Bundle integrity check failed")
    if bundle.get("format_version") != 1:
        raise ValidationError("Unsupported bundle format")
    Skill.from_dict(bundle["skill"])
    if check_sources:
        for source in bundle["manifest"]:
            path = within(project, source["path"])
            if (
                not path.is_file()
                or path.stat().st_size > 96_000
                or digest(path.read_bytes()) != source["sha256"]
            ):
                raise SourceChanged(f"Source changed: {source['path']}; regenerate the skill")
    return bundle
