"""Inline JSON Schema validation and explicit dictionary patches."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from jsonschema.exceptions import ValidationError as JSONSchemaError

from .errors import ValidationError
from .jsonio import dumps, normalize


def check_schema(schema: dict) -> None:
    dumps(schema, 128_000)
    if type(schema) is not dict or schema.get("type") != "object":
        raise ValidationError("Root schema must have type=object")
    if (
        schema.get("$schema", "https://json-schema.org/draft/2020-12/schema")
        != "https://json-schema.org/draft/2020-12/schema"
    ):
        raise ValidationError("Only JSON Schema draft 2020-12 is supported")

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if "$ref" in node or "$dynamicRef" in node:
                raise ValidationError("Use inline schemas; references are disabled")
            if "patternProperties" in node:
                raise ValidationError("patternProperties is disabled; use named properties")
            if "pattern" in node and node["pattern"] not in ("^[a-z0-9-]+$",):
                raise ValidationError(
                    "Unrestricted regex patterns are disabled; use enum or a trusted application validator"
                )
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValidationError(f"Invalid schema: {exc.message}") from exc


def validate(schema: dict, value: Any) -> None:
    check_schema(schema)
    value = normalize(value)
    try:
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
    except (JSONSchemaError, RecursionError) as exc:
        message = exc.message if isinstance(exc, JSONSchemaError) else "schema recursion"
        raise ValidationError(f"State/arguments do not match schema: {message}") from exc


def apply_patch(state: dict, operations: list[dict]) -> dict:
    """Set/delete dictionary keys using JSON Pointer; replace arrays as a whole."""
    state = normalize(state)
    operations = normalize(operations)
    if type(state) is not dict or type(operations) is not list or len(operations) > 128:
        raise ValidationError("Expected object state and at most 128 patch operations")
    result = deepcopy(state)
    for op in operations:
        if not isinstance(op, dict) or op.get("op") not in ("set", "delete"):
            raise ValidationError("Patch operation must be set or delete")
        expected = {"op", "path", "value"} if op["op"] == "set" else {"op", "path"}
        if set(op) != expected:
            raise ValidationError("Unexpected patch fields")
        path = op["path"]
        if not isinstance(path, str) or not path.startswith("/"):
            raise ValidationError("Patch path must be a non-root JSON Pointer")
        segments = path[1:].split("/")
        for segment in segments:
            if "~" in segment.replace("~0", "").replace("~1", ""):
                raise ValidationError("Invalid JSON Pointer escape")
        segments = [s.replace("~1", "/").replace("~0", "~") for s in segments]
        parent = result
        for segment in segments[:-1]:
            if segment not in parent or type(parent[segment]) is not dict:
                raise ValidationError("Patch parent must be an existing object")
            parent = parent[segment]
        if op["op"] == "set":
            parent[segments[-1]] = deepcopy(op["value"])
        else:
            if segments[-1] not in parent:
                raise ValidationError("Cannot delete a missing key")
            del parent[segments[-1]]
    return result
