"""Thin host registry; detection never reads authentication or executes hosts."""

from __future__ import annotations

import importlib.util
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

from . import desktop, hosts
from .errors import ValidationError


class HostAdapter(Protocol):
    name: str

    def detect(self, project: Path) -> dict: ...
    def install(self, project: Path, *, mcp: bool = False) -> dict: ...
    def uninstall(self, project: Path) -> dict: ...
    def doctor(self, project: Path) -> dict: ...
    def integration_manifest(self) -> dict: ...


@dataclass(frozen=True)
class ProjectHost:
    name: str
    executable: str
    config: str
    skills: str
    instructions: str | None

    def detect(self, project: Path) -> dict:
        binary = shutil.which(self.executable)
        configured = (project / self.config).is_file()
        return {
            "name": self.name,
            "detected": bool(binary or configured),
            "executable": binary,
            "project_config_present": configured,
            "live_host_verified": False,
        }

    def install(self, project: Path, *, mcp: bool = False) -> dict:
        return hosts.install(project, [self.name], mcp=mcp)

    def uninstall(self, project: Path) -> dict:
        return hosts.uninstall(project, [self.name])

    def doctor(self, project: Path) -> dict:
        report = hosts.doctor(project)
        relevant = [
            c
            for c in report["checks"]
            if c["check"]
            in (self.config, self.instructions, "interpreter:" + self.config, "mcp dependency")
            or c["check"].startswith(self.skills)
        ]
        relevant.append(
            {
                "check": "registered:" + self.name,
                "kind": "installation",
                "ok": self.name in report["installed_hosts"],
            }
        )
        return {
            "host": self.name,
            "ok": bool(relevant) and all(c["ok"] for c in relevant),
            "checks": relevant,
            "detection": self.detect(project),
            "live_host_verified": False,
        }

    def integration_manifest(self) -> dict:
        return {
            **asdict(self),
            "scope": "project",
            "state_engine": "skillstate",
            "transport": ["cli", "stdio-mcp"],
        }


@dataclass(frozen=True)
class DesktopHost:
    name: str = "claude-desktop"

    def detect(self, project: Path) -> dict:
        try:
            config = desktop.config_path()
            found = config.parent.is_dir()
            reason = "configuration directory" if found else "not found"
        except ValidationError as exc:
            found, reason = False, str(exc)
        return {
            "name": self.name,
            "detected": found,
            "evidence": reason,
            "live_host_verified": False,
        }

    def install(self, project: Path, *, mcp: bool = False) -> dict:
        return desktop.connection(project)

    def uninstall(self, project: Path) -> dict:
        return desktop.connection(project, remove=True)

    def doctor(self, project: Path) -> dict:
        checks = desktop.checks(project)
        return {
            "host": self.name,
            "ok": bool(checks) and all(c["ok"] for c in checks),
            "checks": checks,
            "live_host_verified": False,
        }

    def integration_manifest(self) -> dict:
        return {
            "name": self.name,
            "scope": "application",
            "state_engine": "skillstate",
            "transport": ["stdio-mcp"],
            "explicit_connect_required": True,
        }


REGISTRY: dict[str, HostAdapter] = {
    "codex": ProjectHost("codex", "codex", ".codex/config.toml", ".agents/skills/", "AGENTS.md"),
    "claude-code": ProjectHost(
        "claude-code", "claude", ".mcp.json", ".claude/skills/", "CLAUDE.md"
    ),
    "antigravity": ProjectHost(
        "antigravity", "agy", ".agents/mcp_config.json", ".agents/skills/", None
    ),
    "claude-desktop": DesktopHost(),
}


def get(name: str) -> HostAdapter:
    if name not in REGISTRY:
        raise ValidationError("Unknown host")
    return REGISTRY[name]


def detect(project: Path) -> list[dict]:
    return [adapter.detect(project) for adapter in REGISTRY.values()]


def initialize(project: Path, selected: list[str] | None, mcp: bool | None) -> dict:
    detected = detect(project)
    targets = selected or [
        d["name"] for d in detected if d["detected"] and d["name"] in hosts.HOSTS
    ]
    # Preserve offline setup when no host is discoverable, and the historical all-host templates.
    targets = targets or list(hosts.HOSTS)
    enabled = (
        mcp if mcp is not None else not selected and importlib.util.find_spec("mcp") is not None
    )
    result = hosts.install(project, targets, mcp=enabled)
    return {
        **result,
        "detected": detected,
        "selection": "explicit" if selected else "detected-or-offline-fallback",
        "lifecycle_skill": "skillstate-task",
        "desktop_setup": "Use skillstate connect claude-desktop for its separate app-wide connection",
        "mcp_setup": "enabled"
        if enabled
        else "CLI available; install skillstate-kit[mcp] and rerun init --mcp for MCP",
    }
