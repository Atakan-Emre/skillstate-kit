import concurrent.futures
import subprocess
import sys

import pytest

from skillstate import ConflictError, SQLiteStore, ValidationError

PATCH = [{"op": "set", "path": "/count", "value": 1}]
ACTION = {"name": "record", "arguments": {"value": 1}}


def test_duplicate_run_does_not_reset(store, skill):
    with pytest.raises(ConflictError):
        store.create("run", skill, "other")
    assert store.get("run")["state"] == {"count": 0}


def test_state_and_definition_access_are_defensive(store):
    state = store.get("run")
    state["state"]["count"] = 100
    state["skill"]["initial_state"]["count"] = 100
    assert store.get("run")["state"] == {"count": 0}
    assert store.get("run")["skill"]["initial_state"] == {"count": 0}


def test_validation_revision_and_owner_fail_without_writes(store):
    for patch, owner, rev, error in [
        ([{"op": "set", "path": "/count", "value": 99}], "owner", 0, ValidationError),
        (PATCH, "wrong", 0, ConflictError),
        (PATCH, "owner", 1, ConflictError),
        (PATCH, "owner", False, ConflictError),
    ]:
        with pytest.raises(error):
            store.update("run", owner, rev, patch)
    assert store.get("run")["revision"] == 0
    assert len(store.events("run")) == 1


@pytest.mark.parametrize("success,expected", [(True, 1), (False, 0)])
def test_result_commits_only_after_tool_and_is_idempotent(store, success, expected):
    reservation = store.reserve("run", "owner", 0, ACTION, PATCH)
    op = reservation["operation_id"]
    assert store.get("run")["state"] == {"count": 0}
    with pytest.raises(ConflictError):
        store.update("run", "owner", 1, PATCH)
    result = store.record_result(op, "owner", success, {"actual": True})
    assert result["state"] == {"count": expected}
    assert store.record_result(op, "owner", success, {"actual": True}) == result
    with pytest.raises(ConflictError):
        store.record_result(op, "owner", not success, {})


def test_unknown_blocks_actions_and_handoff_until_explicit_reconciliation(store):
    op = store.reserve("run", "owner", 0, ACTION, PATCH)["operation_id"]
    state = store.mark_unknown(op, "owner", "Timeout")
    with pytest.raises(ConflictError):
        store.reserve("run", "owner", state["revision"], ACTION, PATCH)
    with pytest.raises(ConflictError):
        store.handoff("run", "owner", state["revision"], "other")
    with pytest.raises(ConflictError):
        store.record_result(op, "owner", True, {})
    result = store.record_result(op, "owner", True, {}, reconcile=True)
    assert result["pending_operation"] is None
    assert result["state"]["count"] == 1


def test_handoff_prevents_old_owner_writes(store):
    state = store.handoff("run", "owner", 0, "claude-code")
    with pytest.raises(ConflictError):
        store.update("run", "owner", state["revision"], PATCH)
    assert store.update("run", "claude-code", state["revision"], PATCH)["state"]["count"] == 1


def test_audit_failure_rolls_back_result_and_state(store, monkeypatch):
    op = store.reserve("run", "owner", 0, ACTION, PATCH)["operation_id"]

    def fail(*args):
        raise OSError("disk fault")

    monkeypatch.setattr(store, "_event", fail)
    with pytest.raises(OSError):
        store.record_result(op, "owner", True, {})
    assert store.get("run")["state"] == {"count": 0}
    assert store.operation(op)["status"] == "pending"


def test_independent_connections_only_one_revision_wins(tmp_path, skill):
    path = tmp_path / "race.sqlite3"
    with SQLiteStore(path) as store:
        store.create("race", skill, "owner")

    def update():
        with SQLiteStore(path) as store:
            try:
                store.update("race", "owner", 0, PATCH)
                return "ok"
            except ConflictError:
                return "conflict"

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: update(), range(4)))
    assert results.count("ok") == 1
    assert results.count("conflict") == 3


def test_process_death_after_external_effect_retains_pending_intent(tmp_path, skill):
    path = tmp_path / "crash.sqlite3"
    with SQLiteStore(path) as store:
        store.create("crash", skill, "owner")
    script = """
import os,sys
from pathlib import Path
from skillstate import SQLiteStore
s=SQLiteStore(sys.argv[1])
s.reserve('crash','owner',0,{'name':'record','arguments':{}},[{'op':'set','path':'/count','value':1}])
Path(sys.argv[2]).write_text('effect happened')
os._exit(17)
"""
    effect = tmp_path / "effect.txt"
    result = subprocess.run([sys.executable, "-c", script, str(path), str(effect)], timeout=15)
    assert result.returncode == 17
    assert effect.read_text() == "effect happened"
    with SQLiteStore(path) as store:
        run = store.get("crash")
        assert run["state"] == {"count": 0}
        assert store.operation(run["pending_operation"])["status"] == "pending"
        with pytest.raises(ConflictError):
            store.reserve("crash", "owner", run["revision"], ACTION, PATCH)


def test_completed_run_rejects_changes(store):
    state = store.update("run", "owner", 0, [], done=True)
    with pytest.raises(ConflictError):
        store.update("run", "owner", state["revision"], PATCH)


def test_database_unknown_version_rejected(tmp_path):
    import sqlite3

    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(ValidationError):
        SQLiteStore(path)
