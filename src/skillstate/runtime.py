"""History-free managed execution with bounded inputs and durable tool intents."""

from __future__ import annotations

import asyncio
import inspect
import math
from collections.abc import Callable
from typing import Any

from .errors import ConflictError, OperationUncertain, StepLimitExceeded, ValidationError
from .jsonio import dumps, loads, normalize
from .models import Skill, Tool, ToolResult
from .schema import apply_patch, check_schema, validate
from .store import SQLiteStore

CONTRACT = {
    "patch": [{"op": "set or delete", "path": "/field", "value": "set only"}],
    "action": {"name": "registered tool", "arguments": {}},
    "done": False,
}


def context(snapshot: dict, tools: list[dict] | None = None, feedback: str | None = None) -> dict:
    skill = Skill.from_dict(snapshot["skill"])
    value = {
        "instructions": skill.instructions,
        "state_schema": skill.state_schema,
        "state": snapshot["state"],
        "observation": snapshot["observation"],
        "tools": tools or [],
        "response_contract": CONTRACT,
        "response_rules": "Return only JSON with patch, action, done. To finish, set done=true and action=null. Do not include reasoning traces.",
    }
    if feedback is not None:
        value["validation_feedback"] = feedback[:2000]
    return loads(dumps(value, skill.limits.context_bytes))


async def _call(function: Callable, *args):
    if inspect.iscoroutinefunction(function):
        return await function(*args)
    result = await asyncio.to_thread(function, *args)
    return await result if inspect.isawaitable(result) else result


class SkillRuntime:
    def __init__(
        self,
        store: SQLiteStore,
        model: Callable,
        tools: list[Tool],
        *,
        max_retries: int = 2,
        model_timeout: float = 120,
        completion_check: Callable[[dict], bool] | None = None,
    ):
        if type(max_retries) is not int or not 0 <= max_retries <= 10:
            raise ValidationError("max_retries must be an integer from 0 to 10")
        if (
            not isinstance(model_timeout, (int, float))
            or not math.isfinite(model_timeout)
            or model_timeout <= 0
        ):
            raise ValidationError("model_timeout must be positive and finite")
        self.store, self.model = store, model
        self.tools = {}
        for tool in tools:
            if not tool.name or tool.name in self.tools:
                raise ValidationError("Tool names must be nonempty and unique")
            check_schema(tool.input_schema)
            if tool.output_schema is not None:
                check_schema(tool.output_schema)
            if not math.isfinite(tool.timeout) or tool.timeout <= 0:
                raise ValidationError("Tool timeout must be positive and finite")
            self.tools[tool.name] = tool
        self.max_retries, self.model_timeout = max_retries, model_timeout
        self.completion_check = completion_check

    def _decision(self, raw: Any, snapshot: dict) -> dict:
        skill = Skill.from_dict(snapshot["skill"])
        decision = (
            loads(raw, skill.limits.output_bytes)
            if isinstance(raw, str)
            else loads(dumps(raw, skill.limits.output_bytes))
        )
        if type(decision) is not dict or set(decision) != {"patch", "action", "done"}:
            raise ValidationError("Decision requires exactly patch, action, done")
        if type(decision["done"]) is not bool:
            raise ValidationError("done must be boolean")
        candidate = apply_patch(snapshot["state"], decision["patch"])
        validate(skill.state_schema, candidate)
        dumps(candidate, skill.limits.state_bytes)
        action = decision["action"]
        if decision["done"]:
            if action is not None:
                raise ValidationError("A final decision must have action=null")
            if self.completion_check is not None and self.completion_check(candidate) is not True:
                raise ValidationError("Application completion check did not pass")
        else:
            if (
                type(action) is not dict
                or set(action) != {"name", "arguments"}
                or type(action["name"]) is not str
                or action["name"] not in self.tools
            ):
                raise ValidationError("Action must name a registered tool")
            validate(self.tools[action["name"]].input_schema, action["arguments"])
        return decision

    async def step(self, run_id: str, owner: str) -> dict:
        snapshot = self.store.get(run_id)
        if (
            snapshot["owner"] != owner
            or snapshot["pending_operation"]
            or snapshot["status"] != "ready"
        ):
            raise ConflictError("Run is not ready for this owner")
        feedback = None
        for attempt in range(self.max_retries + 1):
            payload = context(snapshot, [t.specification() for t in self.tools.values()], feedback)
            raw = await asyncio.wait_for(_call(self.model, payload), self.model_timeout)
            try:
                decision = self._decision(raw, snapshot)
                break
            except ValidationError as exc:
                if attempt == self.max_retries:
                    raise
                feedback = str(exc)
        if decision["done"]:
            return self.store.update(
                run_id,
                owner,
                snapshot["revision"],
                decision["patch"],
                snapshot["observation"],
                done=True,
            )
        reservation = self.store.reserve(
            run_id, owner, snapshot["revision"], decision["action"], decision["patch"]
        )
        op_id = reservation["operation_id"]
        tool = self.tools[decision["action"]["name"]]
        try:
            result = await asyncio.wait_for(
                _call(tool.handler, normalize(decision["action"]["arguments"]), op_id), tool.timeout
            )
            if type(result) is not ToolResult or type(result.success) is not bool:
                raise ValidationError("Tool must return ToolResult with boolean success")
            if tool.output_schema is not None:
                validate(tool.output_schema, result.observation)
            return self.store.record_result(
                op_id, owner, result.success, result.observation, origin="runtime_observed"
            )
        except BaseException as exc:
            # Cancellation/timeout does not imply the external side effect stopped.
            # If persistence itself is broken, the prior pending intent is retained.
            try:
                if self.store.operation(op_id)["status"] in ("pending", "unknown"):
                    self.store.mark_unknown(op_id, owner, type(exc).__name__)
            except Exception:
                pass
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
            raise OperationUncertain(
                f"Operation {op_id} needs reconciliation ({type(exc).__name__})"
            ) from exc

    async def run(self, run_id: str, owner: str, *, max_steps: int = 30) -> dict:
        if type(max_steps) is not int or not 1 <= max_steps <= 10_000:
            raise ValidationError("max_steps must be an integer between 1 and 10000")
        snapshot = self.store.get(run_id)
        if snapshot["status"] == "completed":
            return snapshot
        for _ in range(max_steps):
            snapshot = await self.step(run_id, owner)
            if snapshot["status"] == "completed":
                return snapshot
        raise StepLimitExceeded("Step budget exhausted; checkpoint retained for an explicit resume")
