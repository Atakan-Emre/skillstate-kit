import asyncio

import pytest

from skillstate import (
    BudgetExceeded,
    ConflictError,
    OperationUncertain,
    SkillRuntime,
    StepLimitExceeded,
    Tool,
    ToolResult,
    ValidationError,
)
from skillstate.demo import run_demo
from skillstate.jsonio import dumps
from skillstate.runtime import context


def tool(handler=None, timeout=1):
    return Tool(
        "record",
        "Record",
        {
            "type": "object",
            "properties": {"value": {"type": "integer"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        handler or (lambda args, op: ToolResult(True, {"value": args["value"]})),
        timeout,
    )


def decision():
    return {
        "patch": [{"op": "set", "path": "/count", "value": 1}],
        "action": {"name": "record", "arguments": {"value": 1}},
        "done": False,
    }


def test_offline_demo_completes():
    result = asyncio.run(run_demo())
    assert result["status"] == "completed"
    assert result["unique_operations"] == 5
    assert result["prompt_bytes"][1:] == [result["prompt_bytes"][1]] * 5


def test_retry_preserves_original_observation(store):
    seen = []

    def model(payload):
        seen.append(payload)
        return {"bad": True} if len(seen) == 1 else decision()

    runtime = SkillRuntime(store, model, [tool()])
    result = asyncio.run(runtime.step("run", "owner"))
    assert result["state"]["count"] == 1
    assert seen[1]["observation"] == {"request_id": "original-request"}
    assert "validation_feedback" in seen[1]
    assert "history" not in seen[1]


@pytest.mark.parametrize("kind", ["arguments", "tool", "patch", "done", "extra", "null_action"])
def test_invalid_decisions_never_execute(store, kind):
    value = decision()
    if kind == "arguments":
        value["action"]["arguments"]["value"] = "one"
    elif kind == "tool":
        value["action"]["name"] = "unknown"
    elif kind == "patch":
        value["patch"][0]["value"] = 99
    elif kind == "done":
        value["done"] = 1
    elif kind == "extra":
        value["reasoning"] = "not supported"
    else:
        value["action"] = None
    calls = []
    runtime = SkillRuntime(
        store, lambda p: value, [tool(lambda a, o: calls.append(o))], max_retries=0
    )
    with pytest.raises(ValidationError):
        asyncio.run(runtime.step("run", "owner"))
    assert not calls
    assert store.get("run")["revision"] == 0


def test_tool_failure_does_not_commit_prediction(store):
    runtime = SkillRuntime(
        store, lambda p: decision(), [tool(lambda a, o: ToolResult(False, {"error": "no"}))]
    )
    result = asyncio.run(runtime.step("run", "owner"))
    assert result["state"] == {"count": 0}
    assert result["observation"] == {"error": "no"}


@pytest.mark.parametrize("mode", ["exception", "bad_result", "large_observation", "timeout"])
def test_ambiguous_outcomes_are_not_retried(store, mode):
    calls = []

    async def handler(args, op):
        calls.append(op)
        if mode == "exception":
            raise OSError("effect may have happened")
        if mode == "bad_result":
            return {"success": True}
        if mode == "large_observation":
            return ToolResult(True, "x" * 40_000)
        await asyncio.sleep(1)

    runtime = SkillRuntime(store, lambda p: decision(), [tool(handler, 0.01)])
    with pytest.raises(OperationUncertain):
        asyncio.run(runtime.step("run", "owner"))
    assert len(calls) == 1
    assert store.get("run")["status"] == "unknown"
    with pytest.raises(ConflictError):
        asyncio.run(runtime.step("run", "owner"))


def test_completion_guard_and_step_limit(store):
    runtime = SkillRuntime(
        store,
        lambda p: {"patch": [], "action": None, "done": True},
        [],
        completion_check=lambda s: False,
        max_retries=0,
    )
    with pytest.raises(ValidationError):
        asyncio.run(runtime.step("run", "owner"))
    runtime = SkillRuntime(store, lambda p: decision(), [tool()])
    with pytest.raises(StepLimitExceeded):
        asyncio.run(runtime.run("run", "owner", max_steps=1))
    assert store.get("run")["state"]["count"] == 1


def test_context_is_history_free_and_bounded(store):
    snapshot = store.get("run")
    assert context(snapshot) == context(snapshot)
    assert "events" not in context(snapshot)
    snapshot["skill"]["limits"]["context_bytes"] = 256
    with pytest.raises(BudgetExceeded):
        context(snapshot)


def test_async_model_and_async_tool(store):
    async def model(payload):
        return dumps(decision())

    async def handler(args, op):
        return ToolResult(True, {"id": op})

    result = asyncio.run(SkillRuntime(store, model, [tool(handler)]).step("run", "owner"))
    assert result["state"] == {"count": 1}


def test_model_cannot_mutate_checkpoint_during_retry(store):
    seen = []

    def model(payload):
        seen.append(payload["observation"].copy())
        payload["state"]["count"] = 9
        payload["observation"].clear()
        payload["tools"][0]["input_schema"]["required"] = []
        return {} if len(seen) == 1 else decision()

    runtime = SkillRuntime(store, model, [tool()])
    assert asyncio.run(runtime.step("run", "owner"))["state"] == {"count": 1}
    assert seen == [{"request_id": "original-request"}] * 2
    assert runtime.tools["record"].input_schema["required"] == ["value"]


def test_long_run_retains_fixed_context_despite_growing_audit():
    from skillstate import Skill, SQLiteStore

    sizes = []

    def model(payload):
        sizes.append(len(dumps(payload).encode("utf-8")))
        if len(sizes) > 100:
            return {"patch": [], "action": None, "done": True}
        return {"patch": [], "action": {"name": "tick", "arguments": {}}, "done": False}

    skill = Skill("long-run", "Repeat the scripted check.", {"type": "object"}, {})
    tick = Tool("tick", "Scripted tick", {"type": "object"}, lambda a, o: ToolResult(True, {}))
    with SQLiteStore() as storage:
        storage.create("long", skill, "worker", {})
        runtime = SkillRuntime(storage, model, [tick])
        result = asyncio.run(runtime.run("long", "worker", max_steps=101))
        assert result["status"] == "completed"
        assert len(storage.events("long", limit=1000)) == 202
        assert len(set(sizes)) == 1


def test_fresh_runtime_uses_latest_observation_without_old_transcript(tmp_path):
    from skillstate import Skill, SQLiteStore

    path = tmp_path / "state.sqlite3"
    schema = {"type": "object", "properties": {"next": {"type": "integer"}}, "required": ["next"]}
    skill = Skill(
        "conformance", "Process the next item using only current state.", schema, {"next": 0}
    )
    observed = []

    def model(payload):
        n = payload["state"]["next"]
        assert payload["observation"] == {"current": f"observation-{n}"}
        serialized = dumps(payload)
        assert "history" not in payload and "events" not in payload
        for prior in range(n):
            assert f'"observation-{prior}"' not in serialized
        observed.append(n)
        return {
            "patch": [{"op": "set", "path": "/next", "value": n + 1}],
            "action": {"name": "advance", "arguments": {"next": n + 1}},
            "done": False,
        }

    tool = Tool(
        "advance",
        "Advance current observation",
        schema,
        lambda args, op: ToolResult(True, {"current": f"observation-{args['next']}"}),
    )
    with SQLiteStore(path) as store:
        store.create("conformance", skill, "owner", {"current": "observation-0"})
    for _ in range(6):
        with SQLiteStore(path) as store:
            asyncio.run(SkillRuntime(store, model, [tool]).step("conformance", "owner"))
    assert observed == list(range(6))
    with SQLiteStore(path) as store:
        assert len(store.events("conformance")) == 13
        assert store.get("conformance")["state"] == {"next": 6}
