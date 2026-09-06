"""Provider-independent skill and tool contracts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from .errors import ValidationError
from .jsonio import digest, dumps, loads, slug
from .schema import validate


@dataclass(frozen=True)
class Limits:
    state_bytes: int = 64_000
    observation_bytes: int = 32_000
    context_bytes: int = 160_000
    output_bytes: int = 64_000

    def __post_init__(self):
        if any(type(v) is not int or not 256 <= v <= 2_000_000 for v in asdict(self).values()):
            raise ValidationError("Byte budgets must be integers between 256 and 2000000")


@dataclass(frozen=True)
class Skill:
    name: str
    instructions: str
    state_schema: dict
    initial_state: dict
    version: str = "1"
    limits: Limits = field(default_factory=Limits)

    def __post_init__(self):
        slug(self.name)
        if not isinstance(self.instructions, str) or not self.instructions.strip():
            raise ValidationError("Skill instructions are required")
        if not isinstance(self.version, str) or not self.version:
            raise ValidationError("Skill version is required")
        dumps(self.instructions, 48_000)
        validate(self.state_schema, self.initial_state)
        dumps(self.initial_state, self.limits.state_bytes)

    def to_dict(self) -> dict:
        return loads(dumps(asdict(self)))

    @property
    def fingerprint(self) -> str:
        return digest(dumps(self.to_dict()))

    @classmethod
    def from_dict(cls, data: dict) -> Skill:
        try:
            data = loads(dumps(data))
            limits = Limits(**data.pop("limits", {}))
            return cls(**data, limits=limits)
        except (TypeError, KeyError) as exc:
            raise ValidationError("Invalid skill definition") from exc


@dataclass(frozen=True)
class ToolResult:
    success: bool
    observation: Any


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict
    handler: Callable[[dict, str], Any]
    timeout: float = 60.0
    # A handler receives (arguments, operation_id). The operation_id can be forwarded
    # to a service's idempotency facility; it is not an exactly-once promise.
    output_schema: dict | None = None

    def specification(self) -> dict:
        return loads(
            dumps(
                {
                    "name": self.name,
                    "description": self.description,
                    "input_schema": self.input_schema,
                }
            )
        )
