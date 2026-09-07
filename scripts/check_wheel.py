"""Install a built wheel into a fresh environment and test public entrypoints."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def run(args, cwd):
    result = subprocess.run(
        args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", timeout=180
    )
    if result.returncode:
        raise RuntimeError(f"Command failed: {args[0]}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def main():
    dist = Path(sys.argv[1] if len(sys.argv) > 1 else "dist").resolve()
    wheels = sorted(dist.glob("skillstate_kit-*.whl"))
    if len(wheels) != 1:
        raise SystemExit("Expected exactly one skillstate-kit wheel")
    with tempfile.TemporaryDirectory(prefix="skillstate-wheel-") as temporary:
        root = Path(temporary)
        venv.EnvBuilder(with_pip=True).create(root / "env")
        python = root / "env" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run([str(python), "-m", "pip", "install", "--upgrade", "pip>=26.2"], root)
        run([str(python), "-m", "pip", "install", str(wheels[0])], root)
        project = root / "project with spaces"
        project.mkdir()
        (project / "SKILL.md").write_text(
            "---\nname: verify\ndescription: Verify the result.\n---\n1. Inspect.\n2. Verify.\n",
            encoding="utf-8",
        )
        command = [str(python), "-m", "skillstate", "--project", str(project)]
        run(command + ["init", "--host", "codex", "--host", "claude-code", "--no-mcp"], root)
        assert (project / ".agents/skills/skillstate-task/SKILL.md").is_file()
        assert (project / ".claude/skills/skillstate-task/SKILL.md").is_file()
        smoke = """
from pathlib import Path
from skillstate import ProjectService
from skillstate.artifacts import ArtifactStore
s = ProjectService(Path.cwd())
r = s.start_task('Installed wheel acceptance', 'python', ['verify'])
key = ArtifactStore(Path.cwd()).put('Installed SDK and canonical lifecycle asset verified')
r = s.checkpoint_task(r['run_id'], 'python', 0, 'verify', 'Checked package', [key], [])
assert s.complete_task(r['run_id'], 'python', r['revision'])['status'] == 'completed'
"""
        run([str(python), "-c", smoke], project)
        run([str(python), "-m", "pip", "install", str(wheels[0]) + "[mcp]"], root)
        assert json.loads(run(command + ["demo"], root))["status"] == "completed"
        run(command + ["init", "--mcp"], root)
        generated = json.loads(run(command + ["generate", "SKILL.md", "--install"], root))
        assert json.loads(run(command + ["validate", generated["name"]], root))["valid"]
        doctor = json.loads(run(command + ["doctor", "--mcp"], root))
        assert doctor["ok"] and doctor["mcp_transport"]["ok"]
        print(
            json.dumps(
                {
                    "wheel": wheels[0].name,
                    "fresh_install": True,
                    "base_package_lifecycle": True,
                    "generation": True,
                    "mcp_transport": doctor["mcp_transport"],
                }
            )
        )


if __name__ == "__main__":
    main()
