import pytest
import tomlkit

from skillstate import BudgetExceeded, ConflictError, SourceChanged, ValidationError
from skillstate.artifacts import ArtifactStore
from skillstate.compiler import generate, load_bundle, prepare, scan, tracking_ir
from skillstate.hosts import doctor, install, uninstall
from skillstate.jsonio import dumps, read_json
from skillstate.service import ProjectService

SOURCE = "skills/qa/SKILL.md"


def test_tracking_generation_preserves_source_and_is_idempotent(project):
    before = (project / SOURCE).read_bytes()
    first = generate(project, SOURCE)
    second = generate(project, SOURCE)
    assert first == second
    assert (project / SOURCE).read_bytes() == before
    bundle = load_bundle(project, first["name"])
    assert bundle["skill"]["initial_state"]["active_step"] == "step-1"
    assert len(bundle["steps"]) == 3
    assert bundle["generation"]["behaviorally_checked"] is False


def test_semantic_proposal_and_source_bound_validation(project):
    request = prepare(project, SOURCE)
    proposal = tracking_ir(request["inventory"], "semantic-qa")
    result = generate(
        project, SOURCE, proposal=proposal, expected_source_hash=request["inventory"]["source_hash"]
    )
    assert result["mode"] == "semantic"
    (project / SOURCE).write_text("# Changed", encoding="utf-8")
    with pytest.raises(SourceChanged):
        generate(
            project,
            SOURCE,
            proposal=proposal,
            expected_source_hash=request["inventory"]["source_hash"],
        )


def test_invalid_proposal_does_not_write_bundle(project):
    proposal = tracking_ir(scan(project, SOURCE))
    proposal["steps"][0]["sources"] = ["fabricated.py"]
    with pytest.raises(ValidationError):
        generate(project, SOURCE, proposal=proposal)
    assert not (project / ".skillstate/definitions").exists()


def test_duplicate_step_ids_and_wrong_initial_state(project):
    proposal = tracking_ir(scan(project, SOURCE))
    proposal["steps"][1]["id"] = proposal["steps"][0]["id"]
    with pytest.raises(ValidationError):
        generate(project, SOURCE, proposal=proposal)
    proposal = tracking_ir(scan(project, SOURCE))
    proposal["initial_state"]["unknown"] = 1
    with pytest.raises(ValidationError):
        generate(project, SOURCE, proposal=proposal)


def test_bundle_integrity_and_source_freshness(project):
    generated = generate(project, SOURCE)
    path = project / generated["path"]
    original = path.read_bytes()
    bundle = read_json(path)
    bundle["skill"]["instructions"] = "tampered"
    path.write_text(dumps(bundle), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_bundle(project, generated["name"])
    path.write_bytes(original)
    (project / SOURCE).write_text("# different", encoding="utf-8")
    with pytest.raises(SourceChanged):
        load_bundle(project, generated["name"])


def test_scan_excludes_credentials_ignored_and_generated_files(project):
    (project / ".env").write_text("SECRET=should-not-appear", encoding="utf-8")
    (project / "credentials.json").write_text('{"token":"never"}', encoding="utf-8")
    (project / "ignored.py").write_text("hidden = 1", encoding="utf-8")
    (project / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    install(project)
    paths = {entry["path"] for entry in scan(project)["files"]}
    assert paths == {SOURCE}


def test_ast_scan_does_not_import_code(project):
    (project / "app.py").write_text(
        "raise RuntimeError('must never import')\ndef handle(value: int):\n    return value\n",
        encoding="utf-8",
    )
    inventory = scan(project, "app.py")
    assert inventory["files"][0]["symbols"][0]["name"] == "handle"
    result = generate(project, ".", profile="python-tests")
    assert result["mode"] == "tracking"


def test_oversized_source_and_escaping_symlink(project, tmp_path):
    (project / "large.md").write_text("x" * 100_000, encoding="utf-8")
    with pytest.raises(BudgetExceeded):
        scan(project, "large.md")
    with pytest.raises(ValidationError):
        scan(project, "../outside")


def test_symlink_source_rejected(project):
    link = project / "linked.md"
    try:
        link.symlink_to(project / SOURCE)
    except OSError:
        pytest.skip("OS does not permit symlink creation")
    with pytest.raises(ValidationError):
        scan(project, "linked.md")


def test_install_three_hosts_idempotent_and_configuration_merge(project):
    (project / ".codex").mkdir()
    (project / ".codex/config.toml").write_text(
        '# keep comment\nmodel = "user-model"\n[mcp_servers.other]\ncommand = "other-tool"\n',
        encoding="utf-8",
    )
    (project / ".mcp.json").write_text(
        '{"mcpServers":{"other":{"command":"echo"}},"custom":true}', encoding="utf-8"
    )
    first = install(project, mcp=True)
    second = install(project, mcp=True)
    assert first["changed_files"]
    assert second["changed_files"] == []
    assert doctor(project)["ok"]
    toml = (project / ".codex/config.toml").read_text(encoding="utf-8")
    assert "# keep comment" in toml
    assert tomlkit.parse(toml)["model"] == "user-model"
    assert read_json(project / ".mcp.json")["custom"] is True
    assert (
        read_json(project / ".agents/mcp_config.json")["mcpServers"]["skillstate-kit"]["args"][-1]
        == "serve"
    )
    result = uninstall(project)
    assert not result["retained_modified_files"]
    assert read_json(project / ".mcp.json")["mcpServers"] == {"other": {"command": "echo"}}


def test_install_refuses_user_file_and_uninstall_retains_edits(project):
    path = project / ".agents/skills/generate-skill-state/SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text("User-owned skill", encoding="utf-8")
    with pytest.raises(ConflictError):
        install(project)
    assert path.read_text() == "User-owned skill"
    path.unlink()
    install(project)
    path.write_text("User modification", encoding="utf-8")
    result = uninstall(project)
    assert path.relative_to(project).as_posix() in result["retained_modified_files"]
    assert path.read_text() == "User modification"


def test_config_conflict_preflight_leaves_skills_unwritten(project):
    (project / ".mcp.json").write_text(
        '{"mcpServers":{"skillstate-kit":{"command":"mine"}}}', encoding="utf-8"
    )
    with pytest.raises(ConflictError):
        install(project, mcp=True)
    assert not (project / ".agents/skills/generate-skill-state/SKILL.md").exists()


def test_artifact_ranges_integrity_and_limits(project):
    artifacts = ArtifactStore(project)
    key = artifacts.put("Merhaba dünya")
    assert artifacts.put("Merhaba dünya") == key
    assert artifacts.read(key, 8, 5)["content"] == "dünya"
    with pytest.raises(ValidationError):
        artifacts.read("../oops")
    with pytest.raises(ValidationError):
        artifacts.read(key, 0, 8001)
    with pytest.raises(BudgetExceeded):
        artifacts.put("x" * 2_000_001)
    (artifacts.root / f"{key}.txt").write_text("tampered", encoding="utf-8")
    with pytest.raises(ValidationError):
        artifacts.read(key)


def test_three_host_sequential_handoff_preserves_state(project):
    generated = generate(project, SOURCE)
    service = ProjectService(project)
    run = service.open_run(generated["name"], "codex", "qa-run", {"task": "check"})
    with service.store() as store:
        run = store.update(
            "qa-run",
            "codex",
            run["revision"],
            [{"op": "set", "path": "/goal", "value": "Verify checkout"}],
        )
    run = service.handoff("qa-run", "codex", run["revision"], "claude-code")
    run = service.handoff("qa-run", "claude-code", run["revision"], "antigravity")
    assert run["state"]["goal"] == "Verify checkout"
    assert run["owner"] == "antigravity"
    # This verifies our protocol, not live IDE applications.


def test_root_skill_resource_directory_is_unambiguous(project):
    (project / "SKILL.md").write_text("# Check\n1. Read fixtures/input.json.\n", encoding="utf-8")
    generated = generate(project, "SKILL.md", name="root-check")
    service = ProjectService(project)
    opened = service.open_run(generated["name"], "codex", "root-run", {})
    assert "relative to `.` within the project root." in opened["skill"]["instructions"]


def test_source_drift_is_reported_and_blocks_handoff(project):
    generated = generate(project, SOURCE)
    service = ProjectService(project)
    service.open_run(generated["name"], "codex", "qa-run", {})
    (project / SOURCE).write_text("# New instructions", encoding="utf-8")
    assert service.run_context("qa-run")["source_drift"]
    with pytest.raises(SourceChanged):
        service.handoff("qa-run", "codex", 0, "claude-code")


def test_installer_rolls_back_partial_write_failure(project, monkeypatch):
    from skillstate import hosts

    config = project / ".mcp.json"
    config.write_text('{"custom":"preserve"}', encoding="utf-8")
    original = config.read_bytes()
    real_write = hosts.atomic_write
    writes = []

    def fail_once(path, data):
        writes.append(path)
        if len(writes) == 3:
            raise OSError("simulated disk failure")
        real_write(path, data)

    monkeypatch.setattr(hosts, "atomic_write", fail_once)
    with pytest.raises(OSError, match="disk failure"):
        install(project, mcp=True)
    assert config.read_bytes() == original
    assert not (project / ".agents/skills/generate-skill-state/SKILL.md").exists()
    assert not (project / ".claude/skills/generate-skill-state/SKILL.md").exists()
    assert not (project / ".skillstate/local/install-record.json").exists()
    monkeypatch.setattr(hosts, "atomic_write", real_write)
    install(project, mcp=True)
    assert doctor(project)["ok"]
