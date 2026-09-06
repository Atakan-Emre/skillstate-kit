"""Content-addressed artifacts, separate from the model's execution context."""

from __future__ import annotations

import re
from pathlib import Path

from .errors import BudgetExceeded, NotFoundError, ValidationError
from .jsonio import atomic_write, digest, within


class ArtifactStore:
    def __init__(self, project: Path):
        self.root = within(project, ".skillstate/local/artifacts")

    def put(self, content: str) -> str:
        if type(content) is not str:
            raise ValidationError("Artifact content must be text")
        raw = content.encode("utf-8")
        if len(raw) > 2_000_000:
            raise BudgetExceeded("Artifact exceeds 2000000 bytes")
        key = digest(raw)
        path = within(self.root, key + ".txt")
        if path.exists() and digest(path.read_bytes()) != key:
            raise ValidationError("Existing artifact integrity check failed")
        if not path.exists():
            atomic_write(path, raw)
        return key

    def read(self, key: str, offset: int = 0, length: int = 4000) -> dict:
        if type(key) is not str or not re.fullmatch(r"[a-f0-9]{64}", key):
            raise ValidationError("Invalid artifact ID")
        if (
            type(offset) is not int
            or offset < 0
            or type(length) is not int
            or not 1 <= length <= 8000
        ):
            raise ValidationError("Invalid artifact character range")
        path = within(self.root, key + ".txt")
        if not path.is_file():
            raise NotFoundError("Artifact not found")
        if path.stat().st_size > 2_000_000:
            raise BudgetExceeded("Artifact exceeds storage budget")
        raw = path.read_bytes()
        if digest(raw) != key:
            raise ValidationError("Artifact integrity check failed")
        content = raw.decode("utf-8")
        return {
            "id": key,
            "offset": offset,
            "content": content[offset : offset + length],
            "next_offset": min(offset + length, len(content)),
            "total_characters": len(content),
        }
