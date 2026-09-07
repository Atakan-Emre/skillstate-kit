"""Project-scoped STDIO MCP server; no model invocation or arbitrary code tool."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from .artifacts import ArtifactStore
from .compiler import generate, prepare
from .hosts import install
from .service import ProjectService


def create_server(project: Path):
    from mcp.server.fastmcp import FastMCP

    project = project.resolve()
    service = ProjectService(project)
    server = FastMCP(
        "skillstate-kit",
        instructions=(
            "Manage bounded, structured skill execution state in this project. "
            "Use prepare/apply for generation. Read context and its revision before writes. "
            "Reserve effects before executing; record actual outcomes. Unknown operations "
            "require reconciliation, never blind replay. Native reports are agent-reported. "
            "Do not claim host conversation history is replaced."
        ),
    )

    @server.tool()
    def generation_prepare(source: str = ".", name: str | None = None) -> dict:
        """Scan local sources and return the schema for a host-generated SkillIR proposal."""
        return prepare(project, source, name)

    @server.tool()
    def generation_apply(
        source: str, proposal: dict, source_hash: str, install_skills: bool = True
    ) -> dict:
        """Validate a source-bound proposal, persist its bundle and optionally install wrappers."""
        result = generate(project, source, proposal=proposal, expected_source_hash=source_hash)
        if install_skills:
            result["installation"] = install(project, name=result["name"])
        return result

    @server.tool()
    def run_find(goal: str | None = None, limit: int = 20) -> list[dict]:
        """Find bounded goal/active-step summaries; inspect before choosing an existing run."""
        return service.find_runs(goal, limit)

    @server.tool()
    def task_start(goal: str, owner: str, steps: list[str], run_id: str | None = None) -> dict:
        """Start or resume an identical evidence-backed task; never reset existing progress."""
        return service.start_task(goal, owner, steps, run_id)

    @server.tool()
    def task_checkpoint(
        run_id: str,
        owner: str,
        revision: int,
        step: str,
        summary: str,
        evidence: list[str],
        resources: list[str],
        revalidation_reason: str = "",
    ) -> dict:
        """Save actual milestone evidence and resource fingerprints; repeating a step needs a reason."""
        return service.checkpoint_task(
            run_id, owner, revision, step, summary, evidence, resources, revalidation_reason
        )

    @server.tool()
    def task_complete(run_id: str, owner: str, revision: int) -> dict:
        """Check required milestone evidence and freshness before marking a task complete."""
        return service.complete_task(run_id, owner, revision)

    @server.tool()
    def run_open(name: str, owner: str, observation: dict, run_id: str | None = None) -> dict:
        """Open a new run; duplicate IDs are rejected instead of resetting existing work."""
        return service.open_run(name, owner, run_id, observation)

    @server.tool()
    def run_context(run_id: str) -> dict:
        """Get current state, instructions, observation, revision and source drift status."""
        return service.run_context(run_id)

    @server.tool()
    def run_update(
        run_id: str,
        owner: str,
        revision: int,
        patch: list[dict],
        observation: dict | None = None,
        done: bool = False,
    ) -> dict:
        """Apply validated agent-reported facts without executing external actions."""
        return service.update_run(run_id, owner, revision, patch, observation, done=done)

    @server.tool()
    def run_reserve(
        run_id: str, owner: str, revision: int, action: dict, patch: list[dict]
    ) -> dict:
        """Persist an operation intent before the host executes its authorized tool."""
        with service.store() as store:
            return store.reserve(run_id, owner, revision, action, patch)

    @server.tool()
    def run_record_result(
        operation_id: str, owner: str, success: bool, observation: dict, reconcile: bool = False
    ) -> dict:
        """Record a native tool outcome; reconcile=true explicitly resolves uncertainty."""
        with service.store() as store:
            return store.record_result(
                operation_id, owner, success, observation, reconcile=reconcile
            )

    @server.tool()
    def run_unknown(operation_id: str, owner: str, reason: str) -> dict:
        """Mark an ambiguous outcome; blocks further actions until reconciled."""
        with service.store() as store:
            return store.mark_unknown(operation_id, owner, reason)

    @server.tool()
    def run_handoff(run_id: str, owner: str, revision: int, target: str) -> dict:
        """Transfer an idle run to another owner, refusing pending actions and source drift."""
        return service.handoff(run_id, owner, revision, target)

    @server.tool()
    def run_status() -> list[dict]:
        """List recent runs in this project."""
        with service.store() as store:
            return store.list_runs()

    @server.tool()
    def artifact_put(content: str) -> dict:
        """Persist a bounded text artifact outside execution context."""
        return {"id": ArtifactStore(project).put(content)}

    @server.tool()
    def artifact_read(artifact_id: str, offset: int = 0, length: int = 4000) -> dict:
        """Read at most 8000 characters from a content-addressed artifact."""
        return ArtifactStore(project).read(artifact_id, offset, length)

    return server


def serve(project: Path) -> None:
    create_server(project).run(transport="stdio")


async def smoke_test(project: Path) -> dict:
    """Negotiate MCP with a real child server and call the read-only status tool."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "skillstate", "--project", str(project.resolve()), "serve"],
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
            result = await session.initialize()
            tools = await session.list_tools()
            status = await session.call_tool("run_status", {})
            return {
                "ok": not status.isError,
                "protocol_version": result.protocolVersion,
                "tool_count": len(tools.tools),
                "transport": "stdio",
            }

    return await asyncio.wait_for(exercise(), timeout=20)
