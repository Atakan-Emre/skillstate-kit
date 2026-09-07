"""One project-bound facade shared by CLI and MCP."""

from __future__ import annotations

import uuid
from pathlib import Path

from . import compiler, lifecycle
from .errors import ConflictError, NotFoundError, SourceChanged, ValidationError
from .jsonio import digest, dumps, within
from .models import Skill
from .runtime import context
from .store import SQLiteStore


class ProjectService:
    def __init__(self, project: Path):
        self.project = project.resolve()
        if not self.project.is_dir():
            raise ValidationError("Project root must be an existing directory")

    def store(self) -> SQLiteStore:
        return SQLiteStore(within(self.project, ".skillstate/local/state.sqlite3"))

    def open_run(self, name: str, owner: str, run_id: str | None = None, observation=None) -> dict:
        bundle = compiler.load_bundle(self.project, name)
        skill = Skill.from_dict(bundle["skill"])
        with self.store() as store:
            return store.create(run_id or uuid.uuid4().hex, skill, owner, observation)

    def run_context(self, run_id: str) -> dict:
        with self.store() as store:
            snapshot = store.get(run_id)
        drift = None
        try:
            if snapshot["state"].get("profile") == lifecycle.PROFILE:
                raise NotFoundError("Built-in task profile")
            bundle = compiler.load_bundle(self.project, snapshot["skill"]["name"])
            if (
                Skill.from_dict(bundle["skill"]).fingerprint
                != Skill.from_dict(snapshot["skill"]).fingerprint
            ):
                drift = "Definition changed; this run keeps its original immutable definition"
        except NotFoundError:
            if snapshot["state"].get("profile") != lifecycle.PROFILE:
                drift = "Definition unavailable; run retains its pinned instructions"
        except SourceChanged as exc:
            drift = str(exc)
        result = {
            "run_id": run_id,
            "owner": snapshot["owner"],
            "revision": snapshot["revision"],
            "status": snapshot["status"],
            "pending_operation": snapshot["pending_operation"],
            "source_drift": drift,
            "context": context(snapshot),
        }
        if snapshot["state"].get("profile") == lifecycle.PROFILE:
            result["milestone_validity"] = lifecycle.freshness(self.project, snapshot["state"])
        if snapshot["pending_operation"]:
            with self.store() as store:
                result["pending"] = store.operation(snapshot["pending_operation"])
        dumps(result, Skill.from_dict(snapshot["skill"]).limits.context_bytes)
        return result

    def handoff(self, run_id: str, owner: str, revision: int, target: str) -> dict:
        snapshot = self.run_context(run_id)
        if snapshot["source_drift"] or any(
            not v["valid"] for v in snapshot.get("milestone_validity", [])
        ):
            raise SourceChanged("Resolve source/definition drift before handing off")
        with self.store() as store:
            return store.handoff(run_id, owner, revision, target)

    def find_runs(self, goal: str | None = None, limit: int = 20) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValidationError("Run summary limit must be 1-100")
        result = []
        with self.store() as store:
            for item in store.list_runs(100):
                row = store.get(item["id"])
                task_goal = row["state"].get("goal", "")
                if goal is not None and task_goal != goal:
                    continue
                result.append(
                    {
                        **item,
                        "skill": row["skill"]["name"],
                        "goal": str(task_goal)[:2000],
                        "active_step": str(row["state"].get("active_step", ""))[:160],
                    }
                )
                if len(result) >= limit:
                    break
        dumps(result, 64000)
        return result

    def start_task(
        self, goal: str, owner: str, steps: list[str], run_id: str | None = None
    ) -> dict:
        skill = lifecycle.task_skill(goal, steps)
        run_id = run_id or "task-" + digest(goal)[:24]
        with self.store() as store:
            try:
                row = store.create(run_id, skill, owner, {"goal": goal})
            except ConflictError:
                row = store.get(run_id)
                if row["skill"] != skill.to_dict():
                    raise ConflictError(
                        "Run ID already refers to a different task or plan; resume explicitly or choose a new ID"
                    ) from None
                if row["owner"] != owner:
                    raise ConflictError(
                        "Existing task has another owner; request explicit handoff"
                    ) from None
        return self.run_context(row["run_id"])

    def checkpoint_task(
        self,
        run_id: str,
        owner: str,
        revision: int,
        step: str,
        summary: str,
        evidence: list[str],
        resources: list[str],
        revalidation_reason: str = "",
    ) -> dict:
        with self.store() as store:
            snapshot = store.get(run_id)
            patch = lifecycle.checkpoint_patch(
                self.project, snapshot, step, summary, evidence, resources, revalidation_reason
            )
            return store.update(
                run_id, owner, revision, patch, {"milestone": step, "summary": summary}
            )

    def complete_task(self, run_id: str, owner: str, revision: int) -> dict:
        with self.store() as store:
            snapshot = store.get(run_id)
            lifecycle.validate_completion(self.project, snapshot)
            return store.update(
                run_id,
                owner,
                revision,
                [{"op": "set", "path": "/active_step", "value": "done"}],
                {
                    "validation": "evidence integrity and declared resource freshness checked; business outcome remains agent-reported"
                },
                done=True,
            )

    def update_run(
        self,
        run_id: str,
        owner: str,
        revision: int,
        patch: list[dict],
        observation=None,
        *,
        done: bool = False,
    ) -> dict:
        with self.store() as store:
            snapshot = store.get(run_id)
            if done and snapshot["state"].get("profile") == lifecycle.PROFILE:
                raise ValidationError("Use task_complete to validate task milestone evidence")
            lifecycle.guard_generic_patch(snapshot, patch)
            return store.update(run_id, owner, revision, patch, observation, done=done)

    def reserve_run(
        self, run_id: str, owner: str, revision: int, action: dict, patch: list[dict]
    ) -> dict:
        with self.store() as store:
            lifecycle.guard_generic_patch(store.get(run_id), patch)
            return store.reserve(run_id, owner, revision, action, patch)
