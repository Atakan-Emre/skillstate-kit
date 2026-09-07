import json

import pytest

from skillstate import ConflictError, ValidationError, host_registry, hosts
from skillstate.cli import main


def test_detection_and_init_without_optional_mcp(project, monkeypatch):
    monkeypatch.setattr(
        host_registry.shutil, "which", lambda name: "/bin/codex" if name == "codex" else None
    )
    monkeypatch.setattr(host_registry.importlib.util, "find_spec", lambda name: None)
    result = host_registry.initialize(project, None, None)
    assert result["hosts"] == ["codex"] and not result["mcp"]
    assert (project / "AGENTS.md").is_file()
    assert host_registry.get("codex").doctor(project)["ok"]
    assert host_registry.get("codex").integration_manifest()["state_engine"] == "skillstate"
    with pytest.raises(ValidationError):
        host_registry.get("not-a-host")


def test_instruction_blocks_preserve_outside_edits_and_uninstall(project):
    p = project / "AGENTS.md"
    p.write_text("Original instructions\n")
    hosts.install(project, ["codex"])
    p.write_text(p.read_text().replace("Original instructions", "User edited instructions"))
    assert hosts.install(project, ["codex"])["changed_files"] == []
    hosts.uninstall(project)
    assert p.read_text() == "User edited instructions\n"


def test_changed_instruction_block_conflicts_and_is_retained(project):
    hosts.install(project, ["codex"])
    p = project / "AGENTS.md"
    p.write_text(p.read_text().replace("multi-step", "user-modified"))
    with pytest.raises(ConflictError):
        hosts.install(project, ["codex"])
    assert not hosts.doctor(project)["ok"]
    assert "AGENTS.md" in hosts.uninstall(project)["retained_modified_files"]


def test_malformed_markers_and_preflight_rollback(project):
    p = project / "CLAUDE.md"
    p.write_text(hosts.BEGIN + "\nuser content")
    with pytest.raises(ConflictError):
        hosts.install(project, ["claude-code", "codex"])
    assert not (project / "AGENTS.md").exists()


def test_disconnect_one_host_preserves_shared_skills_and_other_config(project):
    hosts.install(project, mcp=True)
    host_registry.get("codex").uninstall(project)
    assert (project / ".agents/skills/skillstate-task/SKILL.md").is_file()
    assert (project / "CLAUDE.md").is_file()
    assert not (project / "AGENTS.md").exists()
    assert host_registry.get("claude-code").doctor(project)["ok"]
    host_registry.get("antigravity").uninstall(project)
    assert not (project / ".agents/skills/skillstate-task/SKILL.md").exists()
    assert (project / ".claude/skills/skillstate-task/SKILL.md").exists()
    host_registry.get("claude-code").uninstall(project)
    assert not (project / "CLAUDE.md").exists()


def test_host_cli_and_desktop_registry_are_explicit(project, capsys, monkeypatch):
    prefix = ["--project", str(project)]
    assert main(prefix + ["hosts", "detect"]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 4
    assert main(prefix + ["connect", "codex"]) == 0
    capsys.readouterr()
    assert main(prefix + ["doctor", "codex"]) == 0
    capsys.readouterr()
    assert main(prefix + ["disconnect", "codex"]) == 0
    capsys.readouterr()
    assert main(prefix + ["connect", "codex", "--config", "custom.json"]) == 2
    capsys.readouterr()
    desktop = host_registry.get("claude-desktop")
    monkeypatch.setattr(
        host_registry.desktop, "config_path", lambda: project / "desktop/config.json"
    )
    assert not desktop.detect(project)["detected"]
    assert not desktop.doctor(project)["ok"]
    assert desktop.integration_manifest()["explicit_connect_required"]
    assert desktop.uninstall(project)["state_retained"]
    monkeypatch.setattr(host_registry.desktop, "connection", lambda p: {"connected": True})
    assert desktop.install(project)["connected"]


def test_shared_skills_do_not_certify_an_uninstalled_host(project):
    hosts.install(project, ["antigravity"])
    assert not host_registry.get("codex").doctor(project)["ok"]
    assert host_registry.get("antigravity").doctor(project)["ok"]
    hosts.install(project, ["codex"])
    hosts.uninstall(project, ["codex"])
    assert not host_registry.get("codex").doctor(project)["ok"]


def test_generated_wrapper_preserves_selected_hosts(project):
    hosts.install(project, ["codex"])
    result = hosts.install(project, name="qa-state")
    assert result["hosts"] == ["codex"]
    assert not (project / ".claude").exists()
    assert (project / ".agents/skills/qa-state/SKILL.md").is_file()
