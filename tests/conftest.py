from pathlib import Path

import pytest

from skillstate import Skill, SQLiteStore


@pytest.fixture
def skill():
    return Skill(
        "counter",
        "Record up to five items, then finish.",
        {
            "type": "object",
            "properties": {"count": {"type": "integer", "minimum": 0, "maximum": 5}},
            "required": ["count"],
            "additionalProperties": False,
        },
        {"count": 0},
    )


@pytest.fixture
def store(tmp_path, skill):
    with SQLiteStore(tmp_path / "state.sqlite3") as value:
        value.create("run", skill, "owner", {"request_id": "original-request"})
        yield value


@pytest.fixture
def project(tmp_path: Path):
    source = tmp_path / "skills" / "qa" / "SKILL.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        """---
name: qa
description: Check a project and report its test results.
---
# QA
1. Inspect the test inputs.
2. Run the documented tests.
3. Verify results and report evidence.
""",
        encoding="utf-8",
    )
    return tmp_path
