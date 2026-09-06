"""Transactional checkpoints and a durable operation journal.

SQLite transactions never span model or tool calls. A reserved operation prevents
other writers from advancing its run until its outcome is recorded or reconciled.
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .errors import ConflictError, NotFoundError, ValidationError
from .jsonio import dumps, loads
from .models import Skill
from .schema import apply_patch, validate


def _identifier(value: str) -> str:
    if type(value) is not str or not value or len(value) > 128:
        raise ValidationError("Identifiers must be nonempty strings up to 128 characters")
    return value


class SQLiteStore:
    """One local database, multiple processes, optimistic revision checks.

    Owner identifiers coordinate cooperating clients; they are not authentication.
    Keep this file private to the local project/user. Do not place it on network FS.
    """

    def __init__(self, path: str | Path = ":memory:"):
        self.path = str(path)
        if self.path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(
            self.path, timeout=10, isolation_level=None, check_same_thread=False
        )
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA busy_timeout=10000")
        self._db.execute("PRAGMA synchronous=FULL")
        version = self._db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self._db.close()
            raise ValidationError(f"Unsupported database version: {version}")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, skill TEXT NOT NULL, fingerprint TEXT NOT NULL,
                state TEXT NOT NULL, observation TEXT NOT NULL, revision INTEGER NOT NULL,
                status TEXT NOT NULL, owner TEXT NOT NULL, pending TEXT,
                created REAL NOT NULL, updated REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS operations (
                id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
                action TEXT NOT NULL, candidate TEXT NOT NULL, status TEXT NOT NULL,
                result TEXT, created REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(id), kind TEXT NOT NULL,
                payload TEXT NOT NULL, created REAL NOT NULL
            );
            PRAGMA user_version=1;
        """)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> SQLiteStore:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    @contextmanager
    def _transaction(self):
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise

    def _event(self, run_id: str, kind: str, payload: Any) -> None:
        self._db.execute(
            "INSERT INTO events(run_id,kind,payload,created) VALUES(?,?,?,?)",
            (run_id, kind, dumps(payload), time.time()),
        )

    def _row(self, run_id: str) -> sqlite3.Row:
        row = self._db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Run not found: {run_id}")
        return row

    def _guard(
        self, row: sqlite3.Row, owner: str, revision: int | None = None, pending: bool = False
    ) -> None:
        if row["owner"] != owner:
            raise ConflictError("Run belongs to a different owner; use handoff")
        if revision is not None and (type(revision) is not int or row["revision"] != revision):
            raise ConflictError("Stale revision; reload context and reconsider the decision")
        if not pending and row["pending"] is not None:
            raise ConflictError("An operation is pending or unknown; reconcile it first")
        if row["status"] in ("completed", "cancelled"):
            raise ConflictError("Run is already terminal")

    @staticmethod
    def _snapshot(row: sqlite3.Row) -> dict:
        return {
            "run_id": row["id"],
            "skill": loads(row["skill"]),
            "state": loads(row["state"]),
            "observation": loads(row["observation"]),
            "revision": row["revision"],
            "status": row["status"],
            "owner": row["owner"],
            "pending_operation": row["pending"],
        }

    def get(self, run_id: str) -> dict:
        with self._lock:
            return self._snapshot(self._row(run_id))

    def list_runs(self, limit: int = 100) -> list[dict]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValidationError("Run limit must be between 1 and 1000")
        with self._lock:
            rows = self._db.execute(
                "SELECT id,revision,status,owner,pending FROM runs ORDER BY updated DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def create(self, run_id: str, skill: Skill, owner: str, observation: Any = None) -> dict:
        _identifier(run_id)
        _identifier(owner)
        skill = Skill.from_dict(skill.to_dict())
        obs = dumps(observation, skill.limits.observation_bytes)
        with self._transaction():
            if self._db.execute("SELECT 1 FROM runs WHERE id=?", (run_id,)).fetchone():
                raise ConflictError("Run already exists; resume it without resetting its state")
            now = time.time()
            self._db.execute(
                "INSERT INTO runs VALUES(?,?,?,?,?,0,'ready',?,NULL,?,?)",
                (
                    run_id,
                    dumps(skill.to_dict()),
                    skill.fingerprint,
                    dumps(skill.initial_state),
                    obs,
                    owner,
                    now,
                    now,
                ),
            )
            self._event(run_id, "created", {"skill": skill.name, "owner": owner})
        return self.get(run_id)

    def _candidate(self, row, patch: list[dict]) -> dict:
        skill = Skill.from_dict(loads(row["skill"]))
        candidate = apply_patch(loads(row["state"]), patch)
        validate(skill.state_schema, candidate)
        dumps(candidate, skill.limits.state_bytes)
        return candidate

    def update(
        self,
        run_id: str,
        owner: str,
        revision: int,
        patch: list[dict],
        observation: Any = None,
        *,
        done: bool = False,
    ) -> dict:
        """Record agent-reported facts. Does not certify external business truth."""
        if type(done) is not bool:
            raise ValidationError("done must be boolean")
        with self._transaction():
            row = self._row(run_id)
            self._guard(row, owner, revision)
            skill = Skill.from_dict(loads(row["skill"]))
            candidate = self._candidate(row, patch)
            obs = dumps(observation, skill.limits.observation_bytes)
            self._db.execute(
                "UPDATE runs SET state=?,observation=?,revision=revision+1,status=?,updated=? WHERE id=?",
                (dumps(candidate), obs, "completed" if done else "ready", time.time(), run_id),
            )
            self._event(
                run_id,
                "completed" if done else "updated",
                {"patch": patch, "origin": "agent_reported"},
            )
        return self.get(run_id)

    def reserve(
        self, run_id: str, owner: str, revision: int, action: dict, patch: list[dict]
    ) -> dict:
        dumps(action, 32_000)
        if (
            type(action) is not dict
            or set(action) != {"name", "arguments"}
            or type(action["name"]) is not str
            or not action["name"]
            or type(action["arguments"]) is not dict
        ):
            raise ValidationError("Invalid action contract")
        with self._transaction():
            row = self._row(run_id)
            self._guard(row, owner, revision)
            candidate = self._candidate(row, patch)
            operation_id = uuid.uuid4().hex
            self._db.execute(
                "INSERT INTO operations VALUES(?,?,?,?,'pending',NULL,?)",
                (operation_id, run_id, dumps(action), dumps(candidate), time.time()),
            )
            self._db.execute(
                "UPDATE runs SET pending=?,status='running',revision=revision+1,updated=? WHERE id=?",
                (operation_id, time.time(), run_id),
            )
            self._event(run_id, "reserved", {"operation_id": operation_id, "action": action})
        return {"operation_id": operation_id, "run": self.get(run_id)}

    def operation(self, operation_id: str) -> dict:
        with self._lock:
            row = self._db.execute(
                "SELECT * FROM operations WHERE id=?", (operation_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError("Operation not found")
            return {
                "operation_id": row["id"],
                "run_id": row["run_id"],
                "action": loads(row["action"]),
                "status": row["status"],
                "result": loads(row["result"]) if row["result"] else None,
            }

    def mark_unknown(self, operation_id: str, owner: str, reason: str) -> dict:
        reason = str(reason)[:1000]
        with self._transaction():
            op = self.operation(operation_id)
            row = self._row(op["run_id"])
            self._guard(row, owner, pending=True)
            if row["pending"] != operation_id or op["status"] not in ("pending", "unknown"):
                raise ConflictError("Operation is not outstanding")
            self._db.execute("UPDATE operations SET status='unknown' WHERE id=?", (operation_id,))
            self._db.execute(
                "UPDATE runs SET status='unknown',revision=revision+1,updated=? WHERE id=?",
                (time.time(), op["run_id"]),
            )
            self._event(op["run_id"], "unknown", {"operation_id": operation_id, "reason": reason})
        return self.get(op["run_id"])

    def record_result(
        self,
        operation_id: str,
        owner: str,
        success: bool,
        observation: Any,
        *,
        reconcile: bool = False,
        origin: str = "agent_reported",
    ) -> dict:
        if type(success) is not bool or type(reconcile) is not bool:
            raise ValidationError("success and reconcile must be booleans")
        if origin not in ("agent_reported", "runtime_observed"):
            raise ValidationError("Invalid result origin")
        with self._transaction():
            op = self.operation(operation_id)
            row = self._row(op["run_id"])
            if row["owner"] != owner:
                raise ConflictError("Run owner mismatch")
            skill = Skill.from_dict(loads(row["skill"]))
            obs = dumps(observation, skill.limits.observation_bytes)
            result = {"success": success, "observation": loads(obs), "origin": origin}
            if op["status"] in ("succeeded", "failed"):
                if op["result"] != result:
                    raise ConflictError("Operation already has a different result")
                return self._snapshot(row)
            if row["pending"] != operation_id:
                raise ConflictError("Operation does not match run's pending operation")
            if op["status"] == "unknown" and not reconcile:
                raise ConflictError("Unknown result requires explicit reconciliation")
            candidate_row = self._db.execute(
                "SELECT candidate FROM operations WHERE id=?", (operation_id,)
            ).fetchone()
            next_state = candidate_row[0] if success else row["state"]
            self._db.execute(
                "UPDATE operations SET status=?,result=? WHERE id=?",
                ("succeeded" if success else "failed", dumps(result), operation_id),
            )
            self._db.execute(
                "UPDATE runs SET state=?,observation=?,pending=NULL,status='ready',revision=revision+1,updated=? WHERE id=?",
                (next_state, obs, time.time(), op["run_id"]),
            )
            self._event(op["run_id"], "result", {"operation_id": operation_id, **result})
        return self.get(op["run_id"])

    def handoff(self, run_id: str, owner: str, revision: int, target: str) -> dict:
        _identifier(target)
        with self._transaction():
            row = self._row(run_id)
            self._guard(row, owner, revision)
            self._db.execute(
                "UPDATE runs SET owner=?,revision=revision+1,updated=? WHERE id=?",
                (target, time.time(), run_id),
            )
            self._event(run_id, "handoff", {"from": owner, "to": target})
        return self.get(run_id)

    def events(self, run_id: str, after: int = 0, limit: int = 100) -> list[dict]:
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 1000:
            raise ValidationError("Invalid event pagination")
        with self._lock:
            self._row(run_id)
            rows = self._db.execute(
                "SELECT sequence,kind,payload FROM events WHERE run_id=? AND sequence>? ORDER BY sequence LIMIT ?",
                (run_id, after, limit),
            ).fetchall()
            return [{"sequence": r[0], "kind": r[1], "payload": loads(r[2])} for r in rows]
