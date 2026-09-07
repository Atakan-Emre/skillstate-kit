import json

import pytest

from skillstate import ConflictError, SourceChanged, ValidationError
from skillstate.artifacts import ArtifactStore
from skillstate.cli import main
from skillstate.compiler import generate
from skillstate.lifecycle import fingerprint, task_skill
from skillstate.service import ProjectService


def opened(project, steps=None):
    service = ProjectService(project)
    row = service.start_task("Implement feature", "codex", steps or ["inspect", "implement"])
    return service, row["run_id"]


def checkpoint(service, run_id, step, resources=None, **kwargs):
    evidence = ArtifactStore(service.project).put("Actual fixture evidence: " + step)
    with service.store() as store:
        row = store.get(run_id)
    return service.checkpoint_task(
        run_id,
        row["owner"],
        row["revision"],
        step,
        "Verified fixture",
        [evidence],
        resources or [],
        **kwargs,
    )


def test_task_resume_handoff_and_complete_without_reset(project):
    service, rid = opened(project)
    assert (
        service.start_task("Implement feature", "codex", ["inspect", "implement"])["revision"] == 0
    )
    first = checkpoint(service, rid, "inspect")
    service.handoff(rid, "codex", first["revision"], "claude-code")
    other = ProjectService(project)
    context = other.run_context(rid)
    assert context["owner"] == "claude-code"
    assert context["context"]["state"]["active_step"] == "implement"
    assert "events" not in context
    last = checkpoint(other, rid, "implement")
    done = other.complete_task(rid, "claude-code", last["revision"])
    assert done["status"] == "completed"
    assert other.find_runs("Implement feature")[0]["id"] == rid
    assert other.find_runs("different") == []
    assert (
        other.start_task("Implement feature", "claude-code", ["inspect", "implement"])["status"]
        == "completed"
    )


def test_evidence_and_granular_drift_require_justified_revalidation(project):
    service, rid = opened(project, ["implement"])
    (project / "app.py").write_text("value = 1")
    row = checkpoint(service, rid, "implement", ["app.py"])
    (project / "unrelated.py").write_text("value = 10")
    assert service.run_context(rid)["milestone_validity"][0]["valid"]
    with pytest.raises(ConflictError, match="already completed"):
        checkpoint(service, rid, "implement")
    (project / "app.py").write_text("value = 2")
    assert service.run_context(rid)["milestone_validity"][0]["changed_resources"] == ["app.py"]
    with pytest.raises(ConflictError):
        service.complete_task(rid, "codex", row["revision"])
    with pytest.raises(SourceChanged):
        service.handoff(rid, "codex", row["revision"], "claude-code")
    row = checkpoint(
        service,
        rid,
        "implement",
        ["app.py"],
        revalidation_reason="Source changed; reran verification",
    )
    assert service.complete_task(rid, "codex", row["revision"])["status"] == "completed"


def test_missing_or_corrupt_evidence_blocks_completion(project):
    service, rid = opened(project, ["check"])
    row = checkpoint(service, rid, "check", ["removed.txt"])
    key = row["state"]["artifacts"][0]
    path = ArtifactStore(project).root / (key + ".txt")
    path.write_text("tampered")
    assert not service.run_context(rid)["milestone_validity"][0]["valid"]
    with pytest.raises(ConflictError):
        service.complete_task(rid, "codex", row["revision"])
    path.unlink()
    assert not service.run_context(rid)["milestone_validity"][0]["evidence_integrity"]


def test_pending_unknown_and_stale_revision_still_block_task_mutations(project):
    service, rid = opened(project, ["check"])
    with service.store() as store:
        op = store.reserve(rid, "codex", 0, {"name": "external", "arguments": {}}, [])
    assert service.run_context(rid)["pending"]["status"] == "pending"
    with pytest.raises(ConflictError):
        checkpoint(service, rid, "check")
    with service.store() as store:
        store.mark_unknown(op["operation_id"], "codex", "uncertain")
        with pytest.raises(ConflictError):
            store.record_result(op["operation_id"], "codex", True, {})
        store.record_result(op["operation_id"], "codex", True, {}, reconcile=True)
    evidence = ArtifactStore(project).put("ok")
    with pytest.raises(ConflictError):
        service.checkpoint_task(rid, "codex", 0, "check", "ok", [evidence], [])
    row = checkpoint(service, rid, "check")
    assert service.complete_task(rid, "codex", row["revision"])["status"] == "completed"


def test_no_task_completion_bypass_or_cross_task_adoption(project):
    service, rid = opened(project)
    with pytest.raises(ConflictError):
        service.start_task("Other goal", "codex", ["inspect"], rid)
    with pytest.raises(ConflictError):
        service.start_task("Implement feature", "claude-code", ["inspect", "implement"])
    with pytest.raises(ValidationError):
        service.update_run(rid, "codex", 0, [], done=True)
    with pytest.raises(ValidationError):
        service.complete_task(rid, "codex", 0)
    with pytest.raises(ValidationError):
        checkpoint(service, rid, "implement")
    with pytest.raises(ValidationError):
        service.find_runs(limit=101)
    generate(project, "skills/qa/SKILL.md")
    old = service.open_run("qa-state", "codex", "legacy")
    with pytest.raises(ValidationError):
        checkpoint(service, "legacy", "inspect")
    with pytest.raises(ValidationError):
        service.complete_task("legacy", "codex", old["revision"])
    assert service.update_run("legacy", "codex", 0, [], done=True)["status"] == "completed"


@pytest.mark.parametrize(
    "goal,steps", [("", ["a"]), ("x", []), ("x", ["a", "a"]), ("x", [3]), ("x" * 2001, ["a"])]
)
def test_invalid_task_contract(goal, steps):
    with pytest.raises(ValidationError):
        task_skill(goal, steps)


def test_checkpoint_input_validation_and_resource_bounds(project):
    service, rid = opened(project, ["check"])
    evidence = ArtifactStore(project).put("ok")
    for summary, refs, reason in [("", [evidence], ""), ("ok", [], ""), ("ok", [evidence], 3)]:
        with pytest.raises(ValidationError):
            service.checkpoint_task(rid, "codex", 0, "check", summary, refs, [], reason)
    for paths in [["../escape"], ["."], [str(i) for i in range(17)], [3]]:
        with pytest.raises(ValidationError):
            fingerprint(project, paths)
    assert fingerprint(project, ["absent"])[0]["sha256"] is None


def test_task_cli_routes_to_shared_service(project, capsys):
    prefix = ["--project", str(project)]
    (project / "plan.json").write_text('["verify"]')
    assert (
        main(
            prefix
            + [
                "task",
                "start",
                "--goal",
                "CLI task",
                "--owner",
                "codex",
                "--steps",
                "plan.json",
                "--id",
                "cli-task",
            ]
        )
        == 0
    )
    capsys.readouterr()
    evidence = ArtifactStore(project).put("checked")
    assert (
        main(
            prefix
            + [
                "task",
                "checkpoint",
                "cli-task",
                "--owner",
                "codex",
                "--revision",
                "0",
                "--step",
                "verify",
                "--summary",
                "checked",
                "--evidence",
                evidence,
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(prefix + ["task", "complete", "cli-task", "--owner", "codex", "--revision", "1"]) == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "completed"
    assert main(prefix + ["run", "find", "--goal", "CLI task"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["id"] == "cli-task"
