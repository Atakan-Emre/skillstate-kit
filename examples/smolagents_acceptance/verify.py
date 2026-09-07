"""Verify saved acceptance evidence without making any model calls."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from run import FIELDS, oracle

from skillstate import SQLiteStore
from skillstate.compiler import load_bundle


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def verify(work):
    assert version("skillstate-kit") == "0.1.2", (
        "This acceptance protocol targets the public 0.1.2 package"
    )
    expected = oracle(work / "receipts.sqlite3")
    baseline = read(work / "baseline-result.json")
    assert baseline["passed"] and baseline["actual"] == expected
    assert read(work / "original-result.json")["passed"]
    checkpoint = read(work / "interrupted-checkpoint.json")
    assert checkpoint["status"] == "ready" and checkpoint["revision"] == 6
    assert checkpoint["pending_operation"] is None
    with SQLiteStore(work / "state.sqlite3") as store:
        final = store.get("sql-audit-01")
        events = store.events("sql-audit-01")
    assert final["status"] == "completed" and final["revision"] == 11
    assert final["pending_operation"] is None
    assert final["state"]["report"] == expected
    assert set(final["state"]["completed_checks"]) == set(FIELDS)
    assert len(events) == 12
    results = [e["payload"] for e in events if e["kind"] == "result"]
    assert len(results) == len({r["operation_id"] for r in results}) == 5
    assert all(r["success"] and r["origin"] == "runtime_observed" for r in results)
    first = lines(work / "managed-start-queries.jsonl")
    resumed = lines(work / "managed-resume-queries.jsonl")
    before = lines(work / "baseline-queries.jsonl")
    assert len(first) == 3 and len(resumed) == 2 and len(before) == 5
    assert [q["result"] for q in before] == [q["result"] for q in first + resumed]
    assert len({q["query"].strip().rstrip(";") for q in first + resumed}) == 5
    stages = {}
    for stage in ["baseline", "generate", "managed-start", "managed-resume"]:
        files = sorted(
            (work / "calls" / stage).glob("*.metrics.json"), key=lambda p: int(p.name.split(".")[0])
        )
        metrics = [read(p) for p in files]
        assert metrics and all(not m["unexpected_actions"] for m in metrics)
        stages[stage] = {
            "model_calls": len(metrics),
            "context_bytes": [m["context_bytes"] for m in metrics],
        }
    assert stages["baseline"]["model_calls"] == 6
    assert stages["managed-start"]["model_calls"] == stages["managed-resume"]["model_calls"] == 3
    for path in (work / "calls" / "managed-resume").glob("*.input.json"):
        context = read(path)
        assert set(context) == {
            "instructions",
            "state_schema",
            "state",
            "observation",
            "tools",
            "response_contract",
            "response_rules",
        }
    bundle = load_bundle(work, "sql-audit")
    generation = read(work / "generation-result.json")
    assert generation["mode"] == "semantic"
    return {
        "date": datetime.now(UTC).date().isoformat(),
        "upstream": read(work / "upstream.json"),
        "skillstate_version": "0.1.2 (public PyPI install)",
        "model": "Authenticated installed Codex CLI default; fresh ephemeral completion per call",
        "dataset": {
            "kind": "synthetic receipts",
            "rows": 1000,
            "sha256": hashlib.sha256((work / "receipts.sqlite3").read_bytes()).hexdigest(),
        },
        "expected_and_observed_report": expected,
        "baseline": {"passed": True, "tool_calls": 5},
        "managed": {
            "passed": True,
            "tool_calls": 5,
            "before_restart": 3,
            "after_restart": 2,
            "checkpoint_revision": 6,
            "final_revision": 11,
            "events": 12,
            "repeated_queries": 0,
            "pending_operation": None,
        },
        "generation": {
            "source_hash": bundle["source_hash"],
            "bundle_hash": generation["bundle_hash"],
            "mode": "real-model semantic proposal",
        },
        "application_payload_measurements": stages,
        "limits": [
            "One task, one dataset, one successful paired run.",
            "Existing smolagents SQL example, not every feature of its repository.",
            "Synthetic data and read-only SQL, not production or mutating API validation.",
            "Manual tool/model adapter and task specification; no automatic rewrite of arbitrary agent code.",
            "Original upstream in-memory SQLite setup required a shared-connection compatibility fix.",
            "Crash injected after a committed operation, not during an external side effect.",
            "Context bytes measure application JSON payload only, not billed tokens or total provider context.",
            "Baseline uses CodeAgent Python actions; managed mode uses registered JSON tool actions.",
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = verify(args.work.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(
        "PASS: baseline, independent report oracle, semantic generation, process restart, five unique SQL operations, durable events and bounded resume input."
    )
