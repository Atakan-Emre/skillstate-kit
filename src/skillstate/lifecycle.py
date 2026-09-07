"""Optional evidence-backed task profile; no host-specific persistence or schema migration."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .artifacts import ArtifactStore
from .errors import ConflictError, SkillStateError, ValidationError
from .jsonio import digest, dumps, within
from .models import Skill

PROFILE = "skillstate-task-v1"


def task_skill(goal: str, steps: list[str]) -> Skill:
    if not isinstance(goal, str) or not goal.strip() or len(goal) > 2000:
        raise ValidationError("Goal must contain 1-2000 characters")
    if (
        not isinstance(steps, list)
        or not 1 <= len(steps) <= 32
        or any(not isinstance(s, str) or not s.strip() or len(s) > 160 for s in steps)
        or len(set(steps)) != len(steps)
    ):
        raise ValidationError("Provide 1-32 unique, nonempty steps up to 160 characters")
    string = {"type": "string", "maxLength": 2000}
    strings = {"type": "array", "maxItems": 32, "items": string, "uniqueItems": True}
    resource = {
        "type": "object",
        "additionalProperties": False,
        "required": ["path", "sha256"],
        "properties": {"path": string, "sha256": {"type": ["string", "null"], "maxLength": 64}},
    }
    milestone = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "step",
            "summary",
            "evidence",
            "resources",
            "completed_at",
            "source_fingerprint",
            "revalidation_reason",
        ],
        "properties": {
            "step": string,
            "summary": string,
            "evidence": strings,
            "resources": {"type": "array", "maxItems": 16, "items": resource},
            "completed_at": string,
            "source_fingerprint": string,
            "revalidation_reason": string,
        },
    }
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "profile": {"const": PROFILE},
            "goal": string,
            "active_step": string,
            "completed_steps": strings,
            "remaining_steps": strings,
            "artifacts": {"type": "array", "maxItems": 256, "items": string, "uniqueItems": True},
            "blockers": strings,
            "milestones": {"type": "array", "maxItems": 32, "items": milestone},
        },
        "required": [
            "profile",
            "goal",
            "active_step",
            "completed_steps",
            "remaining_steps",
            "artifacts",
            "blockers",
            "milestones",
        ],
    }
    return Skill(
        "task-progress",
        "Maintain authoritative task progress. Read current state before work. Do not repeat completed steps merely because old reasoning is absent. Inspect evidence and freshness; repeat only for explicit revalidation, dependencies/source drift, uncertainty or user direction. Record milestone evidence using task_checkpoint; finish through task_complete. Native results are agent-reported, not independently certified.",
        schema,
        {
            "profile": PROFILE,
            "goal": goal,
            "active_step": steps[0],
            "completed_steps": [],
            "remaining_steps": steps,
            "artifacts": [],
            "blockers": [],
            "milestones": [],
        },
    )


def fingerprint(project: Path, paths: list[str]) -> list[dict]:
    if not isinstance(paths, list) or len(paths) > 16 or any(not isinstance(p, str) for p in paths):
        raise ValidationError("At most 16 project resource paths may be fingerprinted")
    values = []
    for value in paths:
        path = within(project, value)
        if path.exists() and (not path.is_file() or path.stat().st_size > 2_000_000):
            raise ValidationError("Resources must be files of at most 2000000 bytes")
        values.append(
            {
                "path": path.relative_to(project).as_posix(),
                "sha256": digest(path.read_bytes()) if path.exists() else None,
            }
        )
    return values


def freshness(project: Path, state: dict) -> list[dict]:
    if state.get("profile") != PROFILE:
        return []
    result = []
    for m in state["milestones"]:
        changed = []
        for resource in m["resources"]:
            try:
                current = fingerprint(project, [resource["path"]])[0]
                if current != resource:
                    changed.append(resource["path"])
            except (OSError, ValidationError):
                changed.append(resource["path"])
        try:
            for artifact in m["evidence"]:
                ArtifactStore(project).read(artifact, length=1)
            evidence_ok = True
        except (OSError, ValueError, SkillStateError):
            evidence_ok = False
        result.append(
            {
                "step": m["step"],
                "valid": not changed and evidence_ok,
                "changed_resources": changed,
                "evidence_integrity": evidence_ok,
            }
        )
    return result


def checkpoint_patch(
    project: Path,
    snapshot: dict,
    step: str,
    summary: str,
    evidence: list[str],
    resources: list[str],
    revalidation_reason: str = "",
) -> list[dict]:
    state = snapshot["state"]
    if state.get("profile") != PROFILE:
        raise ValidationError(
            "Task checkpoints require a task_start run; semantic runs retain run_update"
        )
    if not isinstance(summary, str) or not summary.strip() or len(summary) > 2000:
        raise ValidationError("A concise milestone summary is required")
    if not isinstance(revalidation_reason, str) or len(revalidation_reason) > 2000:
        raise ValidationError("Invalid revalidation reason")
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 8:
        raise ValidationError("Each milestone requires 1-8 existing evidence artifacts")
    for key in evidence:
        ArtifactStore(project).read(key, length=1)
    if step in state["completed_steps"]:
        if not revalidation_reason.strip():
            raise ConflictError(
                "Step already completed; inspect evidence or provide a revalidation reason"
            )
    elif not state["remaining_steps"] or step != state["remaining_steps"][0]:
        raise ValidationError("Complete the active step before advancing the plan")
    hashes = fingerprint(project, resources)
    milestone = {
        "step": step,
        "summary": summary,
        "evidence": evidence,
        "resources": hashes,
        "completed_at": datetime.now(UTC).isoformat(),
        "source_fingerprint": digest(dumps(hashes)),
        "revalidation_reason": revalidation_reason,
    }
    completed = list(dict.fromkeys([*state["completed_steps"], step]))
    remaining = [s for s in state["remaining_steps"] if s != step]
    milestones = [milestone if m["step"] == step else m for m in state["milestones"]]
    if step not in [m["step"] for m in state["milestones"]]:
        milestones.append(milestone)
    artifacts = list(dict.fromkeys(a for m in milestones for a in m["evidence"]))
    return [
        {"op": "set", "path": "/" + key, "value": value}
        for key, value in {
            "completed_steps": completed,
            "remaining_steps": remaining,
            "active_step": remaining[0] if remaining else "final-validation",
            "milestones": milestones,
            "artifacts": artifacts,
        }.items()
    ]


def validate_completion(project: Path, snapshot: dict):
    state = snapshot["state"]
    if state.get("profile") != PROFILE:
        raise ValidationError("Use the domain completion contract for this semantic run")
    if (
        state["remaining_steps"]
        or state["blockers"]
        or not state["milestones"]
        or set(state["completed_steps"])
        != set(snapshot["skill"]["initial_state"]["remaining_steps"])
    ):
        raise ValidationError("Finish required steps and resolve blockers before completion")
    if set(state["completed_steps"]) != {m["step"] for m in state["milestones"]}:
        raise ValidationError("Each completed step requires milestone evidence")
    if not all(item["valid"] for item in freshness(project, state)):
        raise ConflictError(
            "Milestone evidence is stale or missing; explicitly revalidate affected steps"
        )
