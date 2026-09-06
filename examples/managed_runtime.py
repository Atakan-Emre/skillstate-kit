"""Runnable SDK example. Uses a scripted model, not a paid provider."""

import asyncio

from skillstate import Skill, SkillRuntime, SQLiteStore, Tool, ToolResult


async def main():
    skill = Skill(
        "record-job",
        "Record the job; finish after its result is confirmed.",
        {
            "type": "object",
            "properties": {"recorded": {"type": "boolean"}},
            "required": ["recorded"],
            "additionalProperties": False,
        },
        {"recorded": False},
    )

    def model(context):
        if context["state"]["recorded"]:
            return {"patch": [], "action": None, "done": True}
        return {
            "patch": [{"op": "set", "path": "/recorded", "value": True}],
            "action": {"name": "record", "arguments": {}},
            "done": False,
        }

    def record(arguments, operation_id):
        return ToolResult(True, {"recorded": True, "operation_id": operation_id})

    tool = Tool("record", "Record a job", {"type": "object", "additionalProperties": False}, record)
    with SQLiteStore() as store:
        store.create("example", skill, "worker", {"job": "example"})
        runtime = SkillRuntime(store, model, [tool], completion_check=lambda s: s["recorded"])
        result = await runtime.run("example", "worker")
        print(result["status"], result["state"])


if __name__ == "__main__":
    asyncio.run(main())
