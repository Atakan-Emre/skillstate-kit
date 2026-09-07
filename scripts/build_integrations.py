"""Build thin host distribution assets from the canonical lifecycle instructions."""

import json
from pathlib import Path

from skillstate import __version__
from skillstate.hosts import lifecycle_skill

root = Path(__file__).resolve().parents[1]
for host, directory in [("codex", ".codex-plugin"), ("claude", ".claude-plugin")]:
    plugin = root / "integrations" / host / "skillstate-kit"
    (plugin / directory).mkdir(parents=True, exist_ok=True)
    skill = plugin / "skills/skillstate-task"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(lifecycle_skill(), encoding="utf-8")
    manifest = {
        "name": "skillstate-kit",
        "version": __version__,
        "description": "Portable execution state, evidence-backed progress and explicit task continuation.",
        "author": {"name": "Atakan Emre"},
        "license": "MIT",
        "repository": "https://github.com/Atakan-Emre/skillstate-kit",
        "skills": "./skills/",
    }
    if host == "codex":
        manifest["interface"] = {
            "displayName": "SkillState Kit",
            "shortDescription": "Validated execution state for agent tasks.",
            "longDescription": "Preserve evidence-backed task progress and continue from explicit checkpoints using the canonical Python CLI and MCP server.",
            "developerName": "Atakan Emre",
            "category": "Productivity",
            "capabilities": ["Read", "Write"],
            "defaultPrompt": [
                "Use skillstate-task to continue this project from its current checkpoint."
            ],
        }
    (plugin / directory / "plugin.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
