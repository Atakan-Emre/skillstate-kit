import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from skillstate import desktop
from skillstate.cli import main
from skillstate.errors import ConflictError, ValidationError
from skillstate.hosts import doctor


def test_desktop_connect_reconnect_disconnect_preserves_settings(project, tmp_path):
    config = tmp_path / "desktop" / "claude_desktop_config.json"
    config.parent.mkdir()
    original = {"preferences": {"theme": "dark"}, "mcpServers": {"other": {"command": "keep"}}}
    config.write_text(json.dumps(original))
    first = desktop.connection(project, config=config)
    assert first["connected"] and first["changed"]
    assert doctor(project)["ok"]
    assert not desktop.connection(project)["changed"]
    value = json.loads(config.read_text())
    entry = value["mcpServers"][first["server_name"]]
    assert entry["args"][-2:] == [str(project.resolve()), "serve"]
    assert value["preferences"] == original["preferences"]
    assert value["mcpServers"]["other"] == original["mcpServers"]["other"]
    assert not desktop.connection(project, remove=True)["connected"]
    assert json.loads(config.read_text()) == original


def test_desktop_refuses_user_modified_entry(project, tmp_path):
    config = tmp_path / "desktop.json"
    result = desktop.connection(project, config=config)
    value = json.loads(config.read_text())
    value["mcpServers"][result["server_name"]]["command"] = "custom"
    config.write_text(json.dumps(value))
    before = config.read_bytes()
    assert not doctor(project)["ok"]
    for remove in (False, True):
        with pytest.raises(ConflictError):
            desktop.connection(project, remove=remove)
        assert config.read_bytes() == before


def test_desktop_multiple_projects_and_config_switch(project, tmp_path):
    config = tmp_path / "desktop.json"
    first = desktop.connection(project, config=config)
    second = desktop.connection(tmp_path / "second", config=config)
    assert first["server_name"] != second["server_name"]
    desktop.connection(project, remove=True)
    assert list(json.loads(config.read_text())["mcpServers"]) == [second["server_name"]]
    with pytest.raises(ConflictError):
        desktop.connection(tmp_path / "second", config=tmp_path / "other.json")


def test_concurrent_desktop_connections_do_not_lose_other_projects(tmp_path):
    config = tmp_path / "desktop.json"
    projects = [tmp_path / f"project-{i}" for i in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda project: desktop.connection(project, config=config), projects)
        )
    assert set(json.loads(config.read_text())["mcpServers"]) == {
        result["server_name"] for result in results
    }
    assert all(desktop.checks(project)[0]["ok"] for project in projects)


def test_desktop_receipt_failure_rolls_back_config(project, tmp_path, monkeypatch):
    config = tmp_path / "desktop.json"
    config.write_text('{"preferences":{"keep":true}}')
    before = config.read_bytes()
    real_write = desktop.atomic_write

    def fail_receipt(path, content):
        if path.name == "claude-desktop.json":
            raise OSError("simulated receipt disk failure")
        real_write(path, content)

    monkeypatch.setattr(desktop, "atomic_write", fail_receipt)
    with pytest.raises(OSError):
        desktop.connection(project, config=config)
    assert config.read_bytes() == before


def test_desktop_windows_store_detection_and_ambiguity(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    packaged = (
        tmp_path
        / "local/Packages/Claude_pzs8sxrjxfjjc/LocalCache/Roaming/Claude/claude_desktop_config.json"
    )
    packaged.parent.mkdir(parents=True)
    packaged.write_text("{}")
    assert desktop.config_path() == packaged
    regular = tmp_path / "roaming/Claude/claude_desktop_config.json"
    regular.parent.mkdir(parents=True)
    regular.write_text("{}")
    with pytest.raises(ValidationError, match="Multiple"):
        desktop.config_path()


def test_desktop_cli_and_invalid_config(project, tmp_path, capsys):
    config = tmp_path / "desktop.json"
    prefix = ["--project", str(project)]
    assert main(prefix + ["connect", "claude-desktop", "--config", str(config)]) == 0
    assert json.loads(capsys.readouterr().out)["connected"]
    assert main(prefix + ["disconnect", "claude-desktop"]) == 0
    config.write_text('{"mcpServers":[]}')
    with pytest.raises(ValidationError):
        desktop.connection(project, config=config)


def test_disconnect_without_receipt_does_not_discover_or_touch_config(project, monkeypatch):
    monkeypatch.setattr(desktop, "config_path", lambda: pytest.fail("must not discover config"))
    assert desktop.connection(project, remove=True) == {
        "connected": False,
        "changed": False,
        "state_retained": True,
    }
