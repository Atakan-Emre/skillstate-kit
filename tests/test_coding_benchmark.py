"""Measurement contract tests; these are not live host acceptance results."""

import importlib.util
import sys
from pathlib import Path

import pytest


@pytest.fixture
def benchmark(monkeypatch):
    root = Path(__file__).resolve().parents[1] / "examples/coding_agent"
    monkeypatch.syspath_prepend(str(root))
    spec = importlib.util.spec_from_file_location("coding_benchmark", root / "run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("evaluate", None)


def test_missing_usage_is_not_silently_estimated(benchmark):
    assert benchmark.metrics([], 1, 400)["provider_usage"] == "unavailable"
    usage = {"input_tokens": 100, "cached_input_tokens": 60, "output_tokens": 20}
    parts = [{"provider_usage": [usage]}, {"provider_usage": "unavailable"}]
    assert benchmark.aggregate_usage(parts)["status"] == "unavailable"
    assert (
        benchmark.aggregate_usage([{"provider_usage": [{"input_tokens": 1}]}])["status"]
        == "unavailable"
    )


def test_cached_tokens_are_not_double_counted_and_cost_requires_rates(benchmark):
    tokens = benchmark.aggregate_usage(
        [
            {
                "provider_usage": [
                    {"input_tokens": 100, "cached_input_tokens": 60, "output_tokens": 20}
                ]
            }
        ]
    )
    assert tokens["total_tokens"] == 120
    price = {"input_per_million": 10, "cached_input_per_million": 1, "output_per_million": 30}
    assert benchmark.estimate_cost(tokens, price)["value"] == pytest.approx(0.00106)
    with pytest.raises(ValueError):
        benchmark.estimate_cost(tokens, {**price, "input_per_million": float("nan")})
    with pytest.raises(ValueError):
        benchmark.estimate_cost(tokens, {})
