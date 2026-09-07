# Coding task

Add `timebox.parse_duration(value)` without changing format_seconds.

Contract:
- Input must be a string; other types raise TypeError.
- Accept one or more adjacent or whitespace-separated integer tokens with units h, m, s.
- Units are lowercase, each may appear at most once, in any order.
- Leading/trailing whitespace is allowed. Whitespace between a number and its unit is not.
- Reject blank strings, signs, decimals, unknown units, uppercase units, duplicated units,
  trailing junk or bare numbers with ValueError.
- Return an integer total in seconds, inclusive range 0..86400; larger totals raise ValueError.
- Examples: "1h30m" -> 5400, "5s 2m" -> 125, "0s" -> 0, "24h" -> 86400.

Use these eight ordered stages (and exact stage names for any progress tracking):
1. inspect
2. plan
3. implement
4. add-tests
5. run-tests
6. resolve-failures
7. style-check
8. final-validation

Inspect the repository, record a concise design plan, implement the feature and meaningful
regression tests, run them, resolve failures if present, check formatting/compilation and
perform final verification. If no failure occurs, stage 6 records that observed result;
do not introduce a failure deliberately. Do not spawn subagents, access other projects,
use external connectors or commit/push. Work only in this fixture. Normal project-local
notes are allowed in either comparison mode. Do not read the independent evaluator.
