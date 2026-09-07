"""JSON-first command line interface for people and coding agents."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from pathlib import Path

from . import __version__, compiler, host_registry, hosts
from .artifacts import ArtifactStore
from .demo import run_demo
from .errors import SkillStateError, ValidationError
from .jsonio import dumps, read_json, within
from .service import ProjectService


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="skillstate", description="Portable, validated execution state for agent skills"
    )
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument(
        "--project", type=Path, default=Path.cwd(), help="Project root (before the subcommand)"
    )
    subs = p.add_subparsers(dest="command", required=True)
    init = subs.add_parser("init", help="Install project-scoped generator skills")
    init.add_argument("--host", action="append", choices=hosts.HOSTS)
    init.add_argument(
        "--mcp",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Also merge local MCP configurations (requires mcp extra)",
    )
    detection = subs.add_parser(
        "hosts", help="Detect host executables/configuration without reading credentials"
    )
    detection.add_argument("action", nargs="?", choices=("detect",), default="detect")
    gen = subs.add_parser(
        "generate", help="Convert a source skill or prepare a semantic generation request"
    )
    gen.add_argument("source", nargs="?", default=".")
    gen.add_argument("--name")
    gen.add_argument("--profile", choices=("auto", "tracking", "python-tests"), default="auto")
    mode = gen.add_mutually_exclusive_group()
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--proposal", type=Path)
    mode.add_argument("--base-url", help="Configured JSON chat endpoint, including /v1 if required")
    gen.add_argument("--model")
    gen.add_argument("--api-key-env", default="SKILLSTATE_API_KEY")
    gen.add_argument("--source-hash", help="Required with --proposal")
    gen.add_argument("--install", action="store_true")
    check = subs.add_parser(
        "validate", help="Validate bundle integrity, schema and source freshness"
    )
    check.add_argument("name")
    doctor = subs.add_parser(
        "doctor", help="Check managed files and local integration configuration"
    )
    doctor.add_argument("host", nargs="?", choices=tuple(host_registry.REGISTRY))
    doctor.add_argument(
        "--mcp", action="store_true", help="Also perform a real local MCP handshake"
    )
    subs.add_parser("uninstall", help="Remove unmodified managed host files; retain run data")
    subs.add_parser("status", help="List local runs")
    subs.add_parser("demo", help="Run the explicit offline scripted-model example")
    subs.add_parser("serve", help="Start a project-scoped STDIO MCP server")
    for command in ("connect", "disconnect"):
        desktop = subs.add_parser(command, help=f"{command.title()} this project to Claude Desktop")
        desktop.add_argument("host", choices=tuple(host_registry.REGISTRY))
        desktop.add_argument("--config", type=Path, help="Explicit desktop config path")
    task = subs.add_parser(
        "task", help="Evidence-backed task lifecycle without a custom Python agent"
    )
    tasks = task.add_subparsers(dest="operation", required=True)
    start = tasks.add_parser("start")
    start.add_argument("--goal", required=True)
    start.add_argument("--owner", required=True)
    start.add_argument("--steps", type=Path, required=True)
    start.add_argument("--id")
    checkpoint = tasks.add_parser("checkpoint")
    complete = tasks.add_parser("complete")
    for child in (checkpoint, complete):
        child.add_argument("run_id")
        child.add_argument("--owner", required=True)
        child.add_argument("--revision", type=int, required=True)
    checkpoint.add_argument("--step", required=True)
    checkpoint.add_argument("--summary", required=True)
    checkpoint.add_argument("--evidence", nargs="+", required=True)
    checkpoint.add_argument("--resource", action="append", default=[])
    checkpoint.add_argument("--revalidation-reason", default="")
    run = subs.add_parser("run", help="Operate a durable run")
    r = run.add_subparsers(dest="operation", required=True)
    find = r.add_parser("find")
    find.add_argument("--goal")
    find.add_argument("--limit", type=int, default=20)
    open_p = r.add_parser("open")
    open_p.add_argument("name")
    open_p.add_argument("--owner", required=True)
    open_p.add_argument("--id")
    open_p.add_argument("--observation", type=Path)
    for command in ("context", "events"):
        child = r.add_parser(command)
        child.add_argument("run_id")
        if command == "events":
            child.add_argument("--after", type=int, default=0)
    update = r.add_parser("update")
    reserve = r.add_parser("reserve")
    handoff = r.add_parser("handoff")
    for child in (update, reserve, handoff):
        child.add_argument("run_id")
        child.add_argument("--owner", required=True)
        child.add_argument("--revision", type=int, required=True)
    update.add_argument("--patch", type=Path, required=True)
    update.add_argument("--observation", type=Path)
    update.add_argument("--done", action="store_true")
    reserve.add_argument("--decision", type=Path, required=True)
    handoff.add_argument("--to", required=True)
    result = r.add_parser("result")
    unknown = r.add_parser("unknown")
    for child in (result, unknown):
        child.add_argument("operation_id")
        child.add_argument("--owner", required=True)
    result.add_argument("--result", type=Path, required=True)
    result.add_argument("--reconcile", action="store_true")
    unknown.add_argument("--reason", default="Host could not determine the tool outcome")
    artifact = subs.add_parser("artifact")
    a = artifact.add_subparsers(dest="operation", required=True)
    put = a.add_parser("put")
    put.add_argument("file", type=Path)
    read = a.add_parser("read")
    read.add_argument("id")
    read.add_argument("--offset", type=int, default=0)
    read.add_argument("--length", type=int, default=4000)
    return p


def dispatch(args) -> dict | list | None:
    project = args.project.resolve()
    service = ProjectService(project)

    def read(path):
        return read_json(within(project, path)) if path else None

    if args.command == "init":
        return host_registry.initialize(project, args.host, args.mcp)
    if args.command == "hosts":
        return host_registry.detect(project)
    if args.command in ("connect", "disconnect"):
        if args.host == "claude-desktop":
            from .desktop import connection

            return connection(project, config=args.config, remove=args.command == "disconnect")
        if args.config is not None:
            raise ValidationError("--config is only supported by claude-desktop")
        adapter = host_registry.get(args.host)
        return (
            adapter.uninstall(project)
            if args.command == "disconnect"
            else adapter.install(project, mcp=True)
        )
    if args.command == "generate":
        if args.prepare:
            return compiler.prepare(project, args.source, args.name)
        proposal, source_hash = read(args.proposal), args.source_hash
        if proposal is not None and not source_hash:
            raise ValidationError("--proposal requires --source-hash from the prepare response")
        if args.base_url:
            from .providers import JSONChatModel

            request = compiler.prepare(project, args.source, args.name)
            model = JSONChatModel(args.base_url, args.model, os.environ.get(args.api_key_env))
            proposal = asyncio.run(model(request))
            source_hash = request["inventory"]["source_hash"]
        result = compiler.generate(
            project,
            args.source,
            name=args.name,
            profile=args.profile,
            proposal=proposal,
            expected_source_hash=source_hash,
        )
        if args.install:
            result["installation"] = hosts.install(project, name=result["name"])
        return result
    if args.command == "validate":
        bundle = compiler.load_bundle(project, args.name)
        return {"valid": True, "name": args.name, **bundle["generation"]}
    if args.command == "doctor":
        result = (
            host_registry.get(args.host).doctor(project) if args.host else hosts.doctor(project)
        )
        if args.mcp:
            try:
                from .mcp_server import smoke_test

                result["mcp_transport"] = asyncio.run(smoke_test(project))
                result["ok"] = result["ok"] and result["mcp_transport"]["ok"]
            except ImportError as exc:
                raise ValidationError(
                    "Install skillstate-kit[mcp] for the MCP transport check"
                ) from exc
            except Exception as exc:
                result["mcp_transport"] = {"ok": False, "error": type(exc).__name__}
                result["ok"] = False
        return result
    if args.command == "uninstall":
        return hosts.uninstall(project)
    if args.command == "demo":
        return asyncio.run(run_demo())
    if args.command == "serve":
        try:
            from .mcp_server import serve

            serve(project)
        except ImportError as exc:
            raise ValidationError("Install skillstate-kit[mcp] to run the MCP server") from exc
        return None
    if args.command == "artifact":
        store = ArtifactStore(project)
        if args.operation == "put":
            path = within(project, args.file)
            if path.stat().st_size > 2_000_000:
                raise ValidationError("Artifact file too large")
            return {"id": store.put(path.read_text(encoding="utf-8"))}
        return store.read(args.id, args.offset, args.length)
    if args.command == "status":
        with service.store() as store:
            return store.list_runs()
    if args.command == "task":
        if args.operation == "start":
            return service.start_task(args.goal, args.owner, read(args.steps), args.id)
        if args.operation == "checkpoint":
            return service.checkpoint_task(
                args.run_id,
                args.owner,
                args.revision,
                args.step,
                args.summary,
                args.evidence,
                args.resource,
                args.revalidation_reason,
            )
        return service.complete_task(args.run_id, args.owner, args.revision)
    if args.command == "run":
        op = args.operation
        if op == "find":
            return service.find_runs(args.goal, args.limit)
        if op == "open":
            return service.open_run(args.name, args.owner, args.id, read(args.observation))
        if op == "context":
            return service.run_context(args.run_id)
        if op == "handoff":
            return service.handoff(args.run_id, args.owner, args.revision, args.to)
        with service.store() as store:
            if op == "update":
                return service.update_run(
                    args.run_id,
                    args.owner,
                    args.revision,
                    read(args.patch),
                    read(args.observation),
                    done=args.done,
                )
            if op == "events":
                return store.events(args.run_id, args.after)
            if op == "reserve":
                decision = read(args.decision)
                if not isinstance(decision, dict) or set(decision) != {"action", "patch"}:
                    raise ValidationError("Native decision must contain exactly action and patch")
                return service.reserve_run(
                    args.run_id, args.owner, args.revision, decision["action"], decision["patch"]
                )
            if op == "unknown":
                return store.mark_unknown(args.operation_id, args.owner, args.reason)
            if op == "result":
                result = read(args.result)
                if not isinstance(result, dict) or set(result) != {"success", "observation"}:
                    raise ValidationError("Result must contain exactly success and observation")
                return store.record_result(
                    args.operation_id,
                    args.owner,
                    result["success"],
                    result["observation"],
                    reconcile=args.reconcile,
                )
    raise ValidationError("Unknown command")


def main(argv: list[str] | None = None) -> int:
    def emit(value, *, stream=None):
        # Strict validation first; ASCII JSON escapes also work in legacy Windows
        # pipes without failing after a mutation has already committed.
        print(json.dumps(json.loads(dumps(value)), ensure_ascii=True), file=stream)

    args = parser().parse_args(argv)
    try:
        result = dispatch(args)
        if result is not None:
            emit(result)
        return 1 if args.command == "doctor" and not result["ok"] else 0
    except SkillStateError as exc:
        emit({"error": exc.code, "message": str(exc)}, stream=sys.stderr)
        return 2
    except (OSError, UnicodeError) as exc:
        emit({"error": "io_error", "message": str(exc)}, stream=sys.stderr)
        return 3
    except sqlite3.Error as exc:
        emit(
            {
                "error": "storage_error",
                "message": f"SQLite operation failed: {type(exc).__name__}",
            },
            stream=sys.stderr,
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
