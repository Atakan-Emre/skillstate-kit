"""Read-only checks after a manually executed Codex -> Claude Code handoff."""

import argparse
import json
from pathlib import Path

from evaluate import evaluate

from skillstate.service import ProjectService


def verify(project: Path, before: dict) -> dict:
    service = ProjectService(project)
    current = service.run_context(before["run_id"])
    with service.store() as store:
        events = []
        after = 0
        while page := store.events(before["run_id"], after=after, limit=1000):
            events.extend(page)
            after = page[-1]["sequence"]
    old = before["context"]["state"]
    new = current["context"]["state"]
    milestones = {m["step"]: m for m in new["milestones"]}
    checks = {
        "same_run_id": current["run_id"] == before["run_id"],
        "revision_increased": current["revision"] > before["revision"],
        "owner_transition": before["owner"] == "codex" and current["owner"] == "claude-code",
        "handoff_event": any(
            e["kind"] == "handoff" and e["payload"] == {"from": "codex", "to": "claude-code"}
            for e in events
        ),
        "no_reset": sum(e["kind"] == "created" for e in events) == 1,
        "earlier_milestones_preserved": all(
            milestones.get(m["step"]) == m for m in old["milestones"]
        ),
        "evidence_valid": all(v["valid"] for v in current["milestone_validity"]),
        "completed": current["status"] == "completed" and not new["remaining_steps"],
        "independent_correctness": evaluate(project)["passed"],
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "run_id": current["run_id"],
        "revision_before": before["revision"],
        "revision_after": current["revision"],
        "tool_replay": "Review host logs separately; unchanged milestones alone cannot prove absence of external tool replay.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--before", required=True)
    args = parser.parse_args()
    result = verify(
        Path(args.project).resolve(), json.loads(Path(args.before).read_text(encoding="utf-8-sig"))
    )
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
