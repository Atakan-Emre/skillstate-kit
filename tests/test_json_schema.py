import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from skillstate import BudgetExceeded, ValidationError, apply_patch
from skillstate.jsonio import dumps, loads, normalize, slug, within
from skillstate.schema import check_schema, validate


@pytest.mark.parametrize(
    "text", ["NaN", "Infinity", "-Infinity", '{"a":1,"a":2}', "[", '"\\ud800"']
)
def test_invalid_json(text):
    with pytest.raises(ValidationError):
        loads(text)


@pytest.mark.parametrize("value", [math.nan, math.inf, {1: "x"}, (1, 2), {1, 2}, object()])
def test_non_json_values(value):
    with pytest.raises(ValidationError):
        normalize(value)


def test_rejects_scalar_subclasses_cycles_and_depth():
    class Forged(int):
        pass

    with pytest.raises(ValidationError):
        normalize(Forged(1))
    value = []
    value.append(value)
    with pytest.raises(ValidationError):
        normalize(value)
    value = {}
    for _ in range(50):
        value = {"next": value}
    with pytest.raises(ValidationError):
        normalize(value)


def test_json_budgets_use_utf8_bytes():
    with pytest.raises(BudgetExceeded):
        dumps("ö" * 20, 30)
    with pytest.raises(BudgetExceeded):
        loads('"' + "x" * 20 + '"', 10)


@given(
    st.dictionaries(
        st.text(alphabet="abc", max_size=8),
        st.integers(min_value=-1000, max_value=1000),
        max_size=10,
    )
)
def test_roundtrip_and_patch_preserves_other_fields(state):
    assert loads(dumps(state)) == state
    new = apply_patch(state, [{"op": "set", "path": "/target", "value": 42}])
    assert new == {**state, "target": 42}
    assert "target" not in state


def test_null_delete_nested_and_pointer_escape():
    state = {"a/b": {"~": 1, "keep": 2}, "x": 1}
    result = apply_patch(
        state, [{"op": "set", "path": "/x", "value": None}, {"op": "delete", "path": "/a~1b/~0"}]
    )
    assert result == {"a/b": {"keep": 2}, "x": None}
    assert state["a/b"]["~"] == 1


@pytest.mark.parametrize(
    "patch",
    [
        {},
        [{"op": "replace", "path": "/a", "value": 1}],
        [{"op": "set", "path": "", "value": 1}],
        [{"op": "delete", "path": "/missing"}],
        [{"op": "set", "path": "/a/missing", "value": 1}],
        [{"op": "set", "path": "/a~2", "value": 1}],
        [{"op": "delete", "path": "/a", "value": None}],
    ],
)
def test_bad_patch_is_atomic(patch):
    state = {"a": 1}
    with pytest.raises(ValidationError):
        apply_patch(state, patch)
    assert state == {"a": 1}


@pytest.mark.parametrize(
    "schema",
    [
        {"type": "array"},
        {"type": "object", "$ref": "https://untrusted.invalid/schema"},
        {"type": "object", "$ref": "#"},
        {"type": "object", "$schema": "unknown"},
        {"type": "object", "required": "bad"},
    ],
)
def test_invalid_or_remote_schema_rejected(schema):
    with pytest.raises(ValidationError):
        check_schema(schema)


def test_schema_rejects_unknown_field():
    with pytest.raises(ValidationError):
        validate({"type": "object", "additionalProperties": False}, {"oops": 1})


@pytest.mark.parametrize("name", ["../x", "", "a/b", "A", "a--b", "-a", "x" * 65])
def test_bad_skill_names(name):
    with pytest.raises(ValidationError):
        slug(name)


def test_path_escape(tmp_path):
    with pytest.raises(ValidationError):
        within(tmp_path, "../secret")
