"""Offline end-to-end runtime example; the model is explicitly scripted."""

from __future__ import annotations

import asyncio

from .jsonio import dumps
from .models import Skill, Tool, ToolResult
from .runtime import SkillRuntime
from .store import SQLiteStore


async def run_demo() -> dict:
    sizes = []
    effects = []

    def model(payload):
        sizes.append(len(dumps(payload).encode("utf-8")))
        count = payload["state"]["count"]
        if count == 5:
            return {"patch": [], "action": None, "done": True}
        return {
            "patch": [{"op": "set", "path": "/count", "value": count + 1}],
            "action": {"name": "record", "arguments": {"value": count + 1}},
            "done": False,
        }

    def record(arguments, operation_id):
        effects.append(operation_id)
        return ToolResult(True, {"recorded": arguments["value"]})

    skill = Skill(
        "counter-demo",
        "Record five numbered items, then finish.",
        {
            "type": "object",
            "properties": {"count": {"type": "integer", "minimum": 0, "maximum": 5}},
            "required": ["count"],
            "additionalProperties": False,
        },
        {"count": 0},
    )
    tool = Tool(
        "record",
        "Record one item",
        {
            "type": "object",
            "properties": {"value": {"type": "integer", "minimum": 1, "maximum": 5}},
            "required": ["value"],
            "additionalProperties": False,
        },
        record,
    )
    with SQLiteStore() as store:
        store.create("demo", skill, "demo", {"event": "start"})
        runtime = SkillRuntime(store, model, [tool], completion_check=lambda s: s["count"] == 5)
        result = await runtime.run("demo", "demo")
        return {
            "status": result["status"],
            "state": result["state"],
            "model": "scripted (offline)",
            "model_calls": len(sizes),
            "prompt_bytes": sizes,
            "unique_operations": len(set(effects)),
            "events": len(store.events("demo")),
        }


def main():
    print(dumps(asyncio.run(run_demo())))


if __name__ == "__main__":
    main()
