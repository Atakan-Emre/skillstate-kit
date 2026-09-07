"""Explicit, reversible Claude Desktop connections to one local project."""

from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path

from .errors import ConflictError, ValidationError
from .hosts import _config_document
from .jsonio import atomic_write, digest, dumps, read_json, within


def checks(project: Path) -> list[dict]:
    """Inspect a saved connection; never imply that the host loaded it."""
    receipt_path = within(project.resolve(), ".skillstate/local/claude-desktop.json")
    if not receipt_path.exists():
        return []
    try:
        receipt = read_json(receipt_path)
        path = Path(receipt["config"])
        doc = _config_document(path, "json")
        matching = doc.get("mcpServers", {}).get(receipt["server_name"]) == receipt["entry"]
        executable = Path(receipt["entry"]["command"]).is_file()
    except (KeyError, TypeError, AttributeError, ValueError, OSError, ValidationError):
        matching, executable = False, False
    return [
        {"check": "claude-desktop config", "kind": "mcp_configuration", "ok": matching},
        {"check": "claude-desktop interpreter", "kind": "executable", "ok": executable},
    ]


def config_path() -> Path:
    """Resolve standalone and Microsoft Store installs without reading credentials."""
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        packaged = (
            Path(local)
            / "Packages/Claude_pzs8sxrjxfjjc/LocalCache/Roaming/Claude/claude_desktop_config.json"
            if local
            else None
        )
        roaming = os.environ.get("APPDATA")
        regular = Path(roaming) / "Claude/claude_desktop_config.json" if roaming else None
        existing = [p for p in (regular, packaged) if p is not None and p.is_file()]
        if len(existing) > 1:
            raise ValidationError("Multiple Claude Desktop configs found; select one with --config")
        if existing:
            return existing[0]
        if packaged is not None and packaged.parent.is_dir():
            return packaged
        if regular is not None:
            return regular
    elif sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    raise ValidationError("Specify the Claude Desktop config path with --config on this platform")


def connection(project: Path, *, config: Path | None = None, remove: bool = False) -> dict:
    """Merge only an owned project-specific server; preserve other app settings."""
    project = project.resolve()
    receipt_path = within(project, ".skillstate/local/claude-desktop.json")
    receipt = read_json(receipt_path) if receipt_path.exists() else None
    if remove and receipt is None:
        return {"connected": False, "changed": False, "state_retained": True}
    if receipt is not None and (
        not isinstance(receipt, dict)
        or set(receipt) != {"config", "server_name", "entry"}
        or not isinstance(receipt["config"], str)
        or not isinstance(receipt["entry"], dict)
    ):
        raise ValidationError("Invalid Claude Desktop connection receipt")
    target = config or (Path(receipt["config"]) if receipt else config_path())
    target = within(target.absolute().parent, target.absolute())
    server_name = "skillstate-" + digest(str(project))[:12]
    if receipt and (receipt["config"] != str(target) or receipt["server_name"] != server_name):
        raise ConflictError("Disconnect the existing Claude Desktop connection first")
    if not remove and importlib.util.find_spec("mcp") is None:
        raise ValidationError("Install skillstate-kit[mcp] before connecting Claude Desktop")
    entry = {
        "command": sys.executable,
        "args": ["-m", "skillstate", "--project", str(project), "serve"],
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    # Serialize our writers across projects and processes sharing this app config.
    lock = within(target.parent, target.name + ".skillstate-lock.sqlite3")
    with closing(sqlite3.connect(lock, timeout=10, isolation_level=None)) as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            original = target.read_bytes() if target.exists() else None
            doc = _config_document(target, "json")
            servers = doc.setdefault("mcpServers", {})
            if not isinstance(servers, dict):
                raise ValidationError("MCP config section must be an object")
            current = servers.get(server_name)
            if current is not None and (receipt is None or current != receipt["entry"]):
                raise ConflictError("Refusing to change a user-owned Claude Desktop server entry")
            if remove:
                servers.pop(server_name, None)
            else:
                servers[server_name] = entry
            updated = (dumps(doc) + "\n").encode("utf-8")
            # Also detect non-cooperating editor writes observed since the initial read.
            if (target.read_bytes() if target.exists() else None) != original:
                raise ConflictError("Claude Desktop config changed during connection; retry")
            changed = updated != original
            if changed:
                atomic_write(target, updated)
            try:
                if remove:
                    receipt_path.unlink(missing_ok=True)
                else:
                    atomic_write(
                        receipt_path,
                        dumps({"config": str(target), "server_name": server_name, "entry": entry})
                        + "\n",
                    )
            except BaseException:
                if changed:
                    if original is None:
                        target.unlink(missing_ok=True)
                    else:
                        atomic_write(target, original)
                raise
            db.execute("COMMIT")
        finally:
            if db.in_transaction:
                db.execute("ROLLBACK")
    return {
        "connected": not remove,
        "changed": changed,
        "host": "claude-desktop",
        "config": str(target),
        "server_name": server_name,
        "project": str(project),
        "state_retained": True,
        "live_host_verified": False,
        "next": "Fully quit and reopen Claude Desktop. Use Chat for local MCP, not Cowork.",
    }
