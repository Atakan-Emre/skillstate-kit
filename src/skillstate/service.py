"""One project-bound facade shared by CLI and MCP."""

from __future__ import annotations

import uuid
from pathlib import Path

from . import compiler
from .errors import SourceChanged, ValidationError
from .jsonio import within
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
            bundle = compiler.load_bundle(self.project, snapshot["skill"]["name"])
            if (
                Skill.from_dict(bundle["skill"]).fingerprint
                != Skill.from_dict(snapshot["skill"]).fingerprint
            ):
                drift = "Definition changed; this run keeps its original immutable definition"
        except SourceChanged as exc:
            drift = str(exc)
        return {
            "run_id": run_id,
            "owner": snapshot["owner"],
            "revision": snapshot["revision"],
            "status": snapshot["status"],
            "pending_operation": snapshot["pending_operation"],
            "source_drift": drift,
            "context": context(snapshot),
        }

    def handoff(self, run_id: str, owner: str, revision: int, target: str) -> dict:
        snapshot = self.run_context(run_id)
        if snapshot["source_drift"]:
            raise SourceChanged("Resolve source/definition drift before handing off")
        with self.store() as store:
            return store.handoff(run_id, owner, revision, target)
