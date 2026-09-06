"""Strict JSON and bounded, local filesystem operations."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

from .errors import BudgetExceeded, ValidationError

MAX_JSON_BYTES = 2_000_000


def normalize(value: Any, depth: int = 0, active: set[int] | None = None) -> Any:
    if depth > 48:
        raise ValidationError("JSON nesting exceeds 48 levels")
    if value is None or type(value) in (bool, int):
        return value
    if type(value) is str:
        try:
            value.encode("utf-8")
        except UnicodeError as exc:
            raise ValidationError("JSON strings must be valid UTF-8") from exc
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValidationError("Non-finite JSON numbers are not supported")
        return value
    if type(value) not in (dict, list):
        raise ValidationError("Expected plain JSON values")
    active = set() if active is None else active
    if id(value) in active:
        raise ValidationError("Circular JSON value")
    active.add(id(value))
    try:
        if type(value) is list:
            return [normalize(v, depth + 1, active) for v in value]
        result = {}
        for key, item in value.items():
            if type(key) is not str:
                raise ValidationError("JSON keys must be plain strings")
            result[normalize(key)] = normalize(item, depth + 1, active)
        return result
    finally:
        active.remove(id(value))


def dumps(value: Any, limit: int = MAX_JSON_BYTES) -> str:
    try:
        result = json.dumps(
            normalize(value),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (ValueError, RecursionError) as exc:
        raise ValidationError("Invalid JSON value") from exc
    if len(result.encode("utf-8")) > limit:
        raise BudgetExceeded(f"JSON exceeds {limit} UTF-8 bytes")
    return result


def _pairs(items: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise ValidationError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValidationError(f"Invalid JSON constant: {value}")


def loads(text: str, limit: int = MAX_JSON_BYTES) -> Any:
    if type(text) is not str:
        raise ValidationError("JSON input must be text")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeError as exc:
        raise ValidationError("JSON input must be valid UTF-8") from exc
    if size > limit:
        raise BudgetExceeded(f"JSON exceeds {limit} UTF-8 bytes")
    try:
        return normalize(json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant))
    except (ValueError, RecursionError) as exc:
        raise ValidationError("Malformed JSON") from exc


def read_json(path: Path, limit: int = MAX_JSON_BYTES) -> Any:
    if path.stat().st_size > limit:
        raise BudgetExceeded(f"File exceeds {limit} bytes: {path.name}")
    return loads(path.read_text(encoding="utf-8-sig"), limit)


def digest(data: str | bytes) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def slug(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value) or len(value) > 64:
        raise ValidationError("Name must be 1–64 lowercase letters/digits separated by hyphens")
    return value


def within(root: Path, value: str | Path) -> Path:
    root = root.resolve()
    path = Path(value)
    path = path if path.is_absolute() else root / path
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValidationError("Path escapes project root")
    # Reject symlinks/junctions even when their target currently stays in the project.
    cursor = path.absolute()
    while cursor != root and cursor != cursor.parent:
        attrs = cursor.lstat().st_file_attributes if os.name == "nt" and cursor.exists() else 0
        if cursor.is_symlink() or attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
            raise ValidationError("Symlink/junction paths are not supported")
        cursor = cursor.parent
    return resolved


def atomic_write(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = data.encode("utf-8") if isinstance(data, str) else data
    descriptor, name = tempfile.mkstemp(prefix=".skillstate-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
