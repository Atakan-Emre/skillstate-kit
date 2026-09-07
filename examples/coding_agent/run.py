"""Real Codex baseline/integrated coding benchmark with fresh-session boundaries."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from evaluate import evaluate

from skillstate import host_registry
from skillstate.jsonio import dumps
from skillstate.service import ProjectService

ROOT = Path(__file__).resolve().parent


def aggregate_usage(parts):
    if any(not isinstance(p["provider_usage"], list) or not p["provider_usage"] for p in parts):
        return {
            "status": "unavailable",
            "reason": "Complete usage is not available for every session",
        }
    usage = [u for p in parts for u in p["provider_usage"]]
    keys = ("input_tokens", "cached_input_tokens", "output_tokens")
    if any(type(u.get(k)) is not int or u[k] < 0 for u in usage for k in keys):
        return {"status": "unavailable", "reason": "Required usage fields are missing or invalid"}
    if any(u["cached_input_tokens"] > u["input_tokens"] for u in usage):
        return {"status": "unavailable", "reason": "Cached input exceeds reported input"}
    tokens = {k: sum(u[k] for u in usage) for k in keys}
    tokens["total_tokens"] = tokens["input_tokens"] + tokens["output_tokens"]
    return tokens


def estimate_cost(tokens, price):
    if "total_tokens" not in tokens:
        return {"status": "unavailable", "reason": "Complete token usage is unavailable"}
    keys = ("input_per_million", "cached_input_per_million", "output_per_million")
    if any(
        type(price.get(k)) not in (int, float) or not math.isfinite(price[k]) or price[k] < 0
        for k in keys
    ):
        raise ValueError(
            "Pricing must provide three finite, nonnegative USD rates per million tokens"
        )
    return {
        "status": "estimated",
        "currency": "USD",
        "pricing": price,
        "value": (
            (tokens["input_tokens"] - tokens["cached_input_tokens"]) * price["input_per_million"]
            + tokens["cached_input_tokens"] * price["cached_input_per_million"]
            + tokens["output_tokens"] * price["output_per_million"]
        )
        / 1000000,
    }


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def metrics(events, elapsed, prompt_bytes):
    items = [e["item"] for e in events if e.get("type") == "item.completed"]
    tools = [
        i for i in items if i.get("type") in ("command_execution", "mcp_tool_call", "web_search")
    ]
    commands = [i.get("command", "") for i in tools if i.get("type") == "command_execution"]
    usages = [
        e["usage"]
        for e in events
        if e.get("type") == "turn.completed" and isinstance(e.get("usage"), dict)
    ]
    contexts = []
    for item in tools:
        if item.get("tool") == "run_context" and item.get("result") is not None:
            contexts.append(len(json.dumps(item["result"], ensure_ascii=True).encode()))
    calls = [
        json.dumps(
            {
                "type": i.get("type"),
                "command": i.get("command"),
                "tool": i.get("tool"),
                "arguments": i.get("arguments"),
            },
            sort_keys=True,
        )
        for i in tools
    ]
    return {
        "wall_seconds": elapsed,
        "host_sessions": 1,
        "model_calls": {
            "status": "unavailable",
            "reason": "CLI exposes session usage, not individual model request count",
        },
        "tool_calls": len(tools),
        "exact_call_signatures": calls,
        "repository_search_commands": sum(
            bool(re.search(r"\brg\b|Select-String|Get-ChildItem", c)) for c in commands
        ),
        "file_read_commands": sum(
            bool(re.search(r"Get-Content|\bcat\b|read_text|read_bytes", c)) for c in commands
        ),
        "file_read_signatures": [
            c for c in commands if re.search(r"Get-Content|\bcat\b|read_text|read_bytes", c)
        ],
        "provider_usage": usages if usages else "unavailable",
        "prompt_bytes": prompt_bytes,
        "mcp_context_response_bytes": contexts,
        "command_errors": sum(
            i.get("exit_code", 0) not in (0, None)
            for i in tools
            if i.get("type") == "command_execution"
        ),
    }


def session(args, mode, boundary):
    work = Path(args.work).resolve()
    project = work / mode
    project.mkdir(parents=True, exist_ok=True)
    marker = project / ".fixture-ready"
    if not marker.exists():
        shutil.copytree(ROOT / "fixture", project, dirs_exist_ok=True)
        if mode == "skillstate":
            host_registry.initialize(project, ["codex"], True)
        marker.write_text("ready")
    results = work / "evidence" / mode
    results.mkdir(parents=True, exist_ok=True)
    if (results / f"{boundary}.json").exists():
        raise RuntimeError(
            "This boundary already has evidence; choose a fresh work directory for another trial"
        )
    task = (ROOT / "TASK.md").read_text(encoding="utf-8-sig")
    prompt = (
        task
        + f"\nThis is a fresh session. Continue the task from the repository and any applicable canonical execution state. Complete stages through {boundary}, then stop; do not work on later stages yet. "
    )
    prompt += f"Use this Python interpreter for tests: {sys.executable}. It has pytest and ruff. "
    prompt += "Follow project instructions. Return completed stages and actual validation results. "
    config = []
    if mode == "skillstate":
        config = [
            "-c",
            "mcp_servers.skillstate-kit.command=" + json.dumps(sys.executable),
            "-c",
            "mcp_servers.skillstate-kit.args="
            + json.dumps(["-m", "skillstate", "--project", str(project), "serve"]),
            "-c",
            "mcp_servers.skillstate-kit.required=true",
        ]
    command = [
        args.codex,
        "exec",
        "--ignore-user-config",
        "--skip-git-repo-check",
        "--ephemeral",
        "--approve-for-me",
        "--json",
        "-C",
        str(project),
        *config,
        "-o",
        str(results / f"{boundary}.final.txt"),
        "-",
    ]
    begin = time.monotonic()
    run = subprocess.run(
        command,
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    (results / f"{boundary}.events.jsonl").write_text(run.stdout, encoding="utf-8")
    (results / f"{boundary}.stderr.txt").write_text(run.stderr, encoding="utf-8")
    events = [json.loads(line) for line in run.stdout.splitlines() if line.startswith("{")]
    result = metrics(events, time.monotonic() - begin, len(prompt.encode()))
    result.update({"exit_code": run.returncode, "mode": mode, "boundary": boundary})
    if mode == "skillstate":
        service = ProjectService(project)
        runs = service.find_runs()
        result["run_count"] = len(runs)
        if len(runs) == 1:
            context = service.run_context(runs[0]["id"])
            write(results / f"{boundary}.checkpoint.json", context)
            result["run_id"] = context["run_id"]
            result["revision"] = context["revision"]
            result["completed_steps"] = context["context"]["state"].get("completed_steps", [])
            result["status"] = context["status"]
            result["canonical_context_bytes"] = len(dumps(context).encode())
    write(results / f"{boundary}.json", result)
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ("exact_call_signatures", "file_read_signatures")
            }
        ),
        flush=True,
    )
    if run.returncode:
        raise RuntimeError("Host session failed; inspect local evidence")


def summarize(args):
    work = Path(args.work).resolve()
    summary = {}
    for mode in ("baseline", "skillstate"):
        parts = [
            json.loads((work / "evidence" / mode / f"{b}.json").read_text()) for b in (2, 4, 6, 8)
        ]
        assert all(p["exit_code"] == 0 for p in parts)
        actual = evaluate(work / mode)
        test = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-c", os.devnull, "tests"],
            cwd=work / mode,
            capture_output=True,
            text=True,
            timeout=60,
        )
        actual["repository_tests_passed"] = test.returncode == 0
        calls = Counter(c for p in parts for c in p["exact_call_signatures"])
        reads = Counter(c for p in parts for c in p["file_read_signatures"])
        tokens = aggregate_usage(parts)
        cost = {"status": "unavailable", "reason": "pricing not explicitly configured"}
        if args.pricing:
            cost = estimate_cost(tokens, json.loads(Path(args.pricing).read_text(encoding="utf-8")))
        summary[mode] = {
            "correctness": actual,
            "tool_calls": sum(p["tool_calls"] for p in parts),
            "repository_search_commands": sum(p["repository_search_commands"] for p in parts),
            "file_read_commands": sum(p["file_read_commands"] for p in parts),
            "repeated_exact_tool_calls": sum(n - 1 for n in calls.values()),
            "repeated_exact_file_read_commands": sum(n - 1 for n in reads.values()),
            "tokens": tokens,
            "wall_seconds": sum(p["wall_seconds"] for p in parts),
            "cost": cost,
            "model_calls": {"status": "unavailable"},
            "sessions": 4,
            "prompt_bytes": [p["prompt_bytes"] for p in parts],
            "mcp_context_response_bytes": [
                n for p in parts for n in p["mcp_context_response_bytes"]
            ],
        }
        if mode == "skillstate":
            assert len({p["run_id"] for p in parts}) == 1
            assert [len(p["completed_steps"]) for p in parts] == [2, 4, 6, 8]
            assert parts[-1]["status"] == "completed"
            assert all(
                a["revision"] < b["revision"] for a, b in zip(parts, parts[1:], strict=False)
            )
            summary[mode]["run_id"] = parts[-1]["run_id"]
            summary[mode]["revisions"] = [p["revision"] for p in parts]
            summary[mode]["canonical_context_bytes"] = [p["canonical_context_bytes"] for p in parts]
        assert actual["passed"] and actual["repository_tests_passed"], actual
    summary.update(
        {
            "correctness": {
                "independent_checks_per_mode": summary["baseline"]["correctness"]["checks"],
                "both_passed": True,
            },
            "repeated_work": {
                "measurement": "Exact call/read-command repetition; necessary validation and avoidable replay are not automatically distinguishable."
            },
            "context": {
                "measurement": "prompt and MCP response bytes only; native transcript is not controlled"
            },
            "tokens": {
                "measurement": "Actual Codex CLI turn.completed usage; includes native host overhead and cached input"
            },
            "latency": {
                "measurement": "Sum of host session wall times, including host/MCP startup"
            },
            "cost": {"measurement": "Unavailable unless explicit pricing provided"},
            "scope": "One paired deterministic coding task. Planned fresh-session boundaries after stages 2/4/6; not forced mid-tool crash.",
        }
    )
    write(work / "summary.json", summary)
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", required=True)
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--pricing")
    parser.add_argument("--mode", choices=["baseline", "skillstate"])
    parser.add_argument("--boundary", type=int, choices=[2, 4, 6, 8])
    parser.add_argument("--summarize", action="store_true")
    args = parser.parse_args()
    if args.summarize:
        summarize(args)
    elif args.mode and args.boundary:
        session(args, args.mode, args.boundary)
    else:
        parser.error("Provide --mode and --boundary, or --summarize")
