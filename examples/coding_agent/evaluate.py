"""Independent evaluator, run outside the host's task directory."""

import importlib.util
import json
import sys
from pathlib import Path


def evaluate(project: Path) -> dict:
    spec = importlib.util.spec_from_file_location(
        "evaluated_timebox", project / "timebox/__init__.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases = [
        ("1h30m", 5400),
        ("5s 2m", 125),
        ("0s", 0),
        ("24h", 86400),
        (" 2h 3m 4s ", 7384),
        ("1s1h1m", 3661),
        ("0002m", 120),
        ("1440m", 86400),
    ]
    invalid = [
        "",
        " ",
        "3",
        "1H",
        "1 h",
        "-1s",
        "+1m",
        "1.5h",
        "1h1h",
        "1m 2m",
        "2d",
        "1sx",
        "24h1s",
        "86401s",
        "1h,2m",
    ]
    failures = []
    for value, expected in cases:
        try:
            result = module.parse_duration(value)
            if type(result) is not int or result != expected:
                failures.append({"input": value, "expected": expected, "actual": repr(result)})
        except Exception as exc:
            failures.append({"input": value, "error": type(exc).__name__})
    for value in invalid + [None, 1, True, [], {}]:
        exception = ValueError if isinstance(value, str) else TypeError
        try:
            module.parse_duration(value)
            failures.append({"input": repr(value), "error": "accepted invalid input"})
        except exception:
            pass
        except Exception as exc:
            failures.append({"input": repr(value), "error": type(exc).__name__})
    if module.format_seconds(3661) != "1h 1m 1s":
        failures.append({"error": "existing API regression"})
    return {
        "passed": not failures,
        "checks": len(cases) + len(invalid) + 5 + 1,
        "failures": failures,
    }


if __name__ == "__main__":
    result = evaluate(Path(sys.argv[1]).resolve())
    print(json.dumps(result))
    raise SystemExit(0 if result["passed"] else 1)
