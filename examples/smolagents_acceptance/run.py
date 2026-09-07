"""Real-model acceptance harness for the upstream smolagents SQL agent.

Requires a separately installed upstream checkout, SQLAlchemy, skillstate-kit,
and an authenticated Codex CLI. No scripted model responses are used.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import hashlib
import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path

from smolagents import CodeAgent, Model
from smolagents.models import ChatMessage, MessageRole
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from skillstate import Skill, SkillRuntime, SQLiteStore, Tool, ToolResult
from skillstate.compiler import generate, load_bundle, prepare

FIELDS = ["receipt_count", "gross_total", "tip_total", "top_customer", "low_tip_count"]
TASK = """Audit the receipts table with columns receipt_id, customer_name, price, tip.
Use exactly one SELECT query per model turn and retrieve each of these five checks separately:
1. receipt_count: total number of rows.
2. gross_total: sum of price, rounded to two decimal places.
3. tip_total: sum of tip, rounded to two decimal places.
4. top_customer: customer_name with highest SUM(price), tie break by customer_name ascending.
5. low_tip_count: number of rows with tip < price * 0.10 (strict inequality).
For this comparison use integer cents: ROUND(tip*100)*10 < ROUND(price*100), avoiding floating-point boundary errors.
Never infer answers from examples or invent query outputs. Do not change the database.
Return all five named fields as one JSON object after observing the five query results.
"""


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=True), encoding="utf-8")


class CodexCompletion(Model):
    """Explicit CLI-backed model adapter for this experiment, not a package feature."""

    def __init__(self, executable, work, label):
        super().__init__(model_id="installed-codex-default")
        self.executable, self.work, self.label = executable, Path(work), label
        self.work.mkdir(parents=True, exist_ok=True)
        self.logs = self.work / "calls" / label
        self.logs.mkdir(parents=True, exist_ok=True)
        self.counter = len(list(self.logs.glob("*.answer.json")))
        self.schema = self.work / "response-schema.json"
        dump(
            self.schema,
            {
                "type": "object",
                "properties": {"content": {"type": "string"}},
                "required": ["content"],
                "additionalProperties": False,
            },
        )
        self.empty = self.work / "completion-workspace"
        self.empty.mkdir(exist_ok=True)

    def complete(self, payload):
        self.counter += 1
        prefix = self.logs / str(self.counter)
        body = json.dumps(payload, ensure_ascii=True, default=lambda x: x.dict())
        prompt = (
            "You are the model completion backend for an external agent runtime. "
            "Return ONLY the next assistant response inside the content string. "
            "Do not use Codex tools, inspect files, run shell commands or delegate. "
            "The external runtime will execute any code or action you produce. "
            "Use only the supplied context; do not invent observations. "
            "Follow the response format and instructions in this context:\n" + body
        )
        args = [
            self.executable,
            "exec",
            "--ignore-user-config",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--json",
            "-C",
            str(self.empty),
            "--output-schema",
            str(self.schema),
            "-o",
            str(prefix.with_suffix(".answer.json")),
            "-",
        ]
        start = time.monotonic()
        result = subprocess.run(
            args, input=prompt, capture_output=True, encoding="utf-8", timeout=180
        )
        prefix.with_suffix(".events.jsonl").write_text(result.stdout, encoding="utf-8")
        prefix.with_suffix(".stderr.txt").write_text(result.stderr, encoding="utf-8")
        dump(prefix.with_suffix(".input.json"), json.loads(body))
        events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
        actions = [
            e.get("item", {}).get("type") for e in events if e.get("type") == "item.completed"
        ]
        forbidden = [a for a in actions if a not in ("agent_message", "reasoning", None)]
        if result.returncode or forbidden:
            raise RuntimeError(
                f"Completion failed: exit={result.returncode}, unexpected actions={forbidden}"
            )
        content = json.loads(prefix.with_suffix(".answer.json").read_text())["content"]
        usage = [e.get("usage") for e in events if e.get("type") == "turn.completed"]
        dump(
            prefix.with_suffix(".metrics.json"),
            {
                "context_bytes": len(body.encode()),
                "seconds": time.monotonic() - start,
                "usage": usage,
                "unexpected_actions": forbidden,
            },
        )
        print(
            f"MODEL {self.label} call {self.counter}: {len(body.encode())} context bytes",
            flush=True,
        )
        return content

    def generate(self, messages, **kwargs):
        return ChatMessage(role=MessageRole.ASSISTANT, content=self.complete(messages))


def load_upstream(repo):
    path = Path(repo) / "examples/text_to_sql.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    # Execute the upstream setup and actual @tool function, stopping before its
    # paid provider construction and run. The supplied adapter replaces only the model.
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "agent" for t in node.targets
        ):
            break
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "engine" for t in node.targets
        ):
            node.value.keywords.extend(
                [
                    ast.keyword(arg="poolclass", value=ast.Name(id="StaticPool", ctx=ast.Load())),
                    ast.keyword(
                        arg="connect_args",
                        value=ast.Dict(
                            keys=[ast.Constant("check_same_thread")], values=[ast.Constant(False)]
                        ),
                    ),
                ]
            )
        nodes.append(node)
    ns = {"__name__": "upstream_sql_fixture", "StaticPool": StaticPool}
    exec(
        compile(
            ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[])), str(path), "exec"
        ),
        ns,
    )
    return ns


def fixture(work):
    database = work / "receipts.sqlite3"
    if not database.exists():
        rows = []
        for i in range(1, 1001):
            price_cents = 500 + (i * 7919) % 24500
            tip_cents = (price_cents * (i % 6) * 5) // 100
            rows.append((i, f"customer-{i % 37:02d}", price_cents / 100, tip_cents / 100))
        with sqlite3.connect(database) as con:
            con.execute(
                "CREATE TABLE receipts(receipt_id INTEGER PRIMARY KEY,customer_name TEXT,price REAL,tip REAL)"
            )
            con.executemany("INSERT INTO receipts VALUES(?,?,?,?)", rows)
    return database


def oracle(database):
    # Independent Python/Decimal computation, not the agent's SQL or state declaration.
    from collections import defaultdict
    from decimal import Decimal

    with sqlite3.connect(database) as con:
        rows = con.execute("SELECT receipt_id,customer_name,price,tip FROM receipts").fetchall()
    prices, tips, totals, low = [], [], defaultdict(Decimal), 0
    for _, name, price, tip in rows:
        price, tip = Decimal(str(price)), Decimal(str(tip))
        prices.append(price)
        tips.append(tip)
        totals[name] += price
        low += tip < price * Decimal("0.10")
    return {
        "receipt_count": len(rows),
        "gross_total": float(sum(prices)),
        "tip_total": float(sum(tips)),
        "top_customer": sorted(totals, key=lambda k: (-totals[k], k))[0],
        "low_tip_count": low,
    }


def sql_adapter(ns, database, work, label):
    ns["engine"].dispose()
    # Durable file-backed DB also works in SkillRuntime's worker threads and new processes.
    ns["engine"] = create_engine("sqlite:///" + database.as_posix())
    upstream_tool = ns["sql_engine"]
    original = upstream_tool.forward

    def observed(query):
        if not query.lstrip().upper().startswith("SELECT") or ";" in query.rstrip().rstrip(";"):
            raise ValueError("Acceptance fixture allows one SELECT only")
        result = original(query=query)
        with (work / f"{label}-queries.jsonl").open("a", encoding="utf-8") as out:
            out.write(json.dumps({"query": query, "result": result}) + "\n")
        return result

    upstream_tool.forward = observed
    return upstream_tool


def parse_json(content):
    if content.strip().startswith("```"):
        content = "\n".join(content.strip().splitlines()[1:-1])
    return json.loads(content)


async def main(args):
    work = Path(args.work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    if not (work / "upstream.json").exists():
        repo = Path(args.upstream).resolve()
        source_files = list((repo / "src").rglob("*.py"))
        dump(
            work / "upstream.json",
            {
                "full_name": "huggingface/smolagents",
                "html_url": "https://github.com/huggingface/smolagents",
                "commit": subprocess.check_output(
                    ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
                ).strip(),
                "python_source_files": len(source_files),
                "python_source_lines": sum(
                    len(p.read_text(encoding="utf-8").splitlines()) for p in source_files
                ),
            },
        )
    model = CodexCompletion(args.codex, work, args.stage)
    ns = load_upstream(args.upstream)
    if args.stage == "original":
        agent = CodeAgent(tools=[ns["sql_engine"]], model=model, max_steps=8, verbosity_level=0)
        answer = agent.run(
            "Can you give me the name of the client who got the most expensive receipt?"
        )
        assert "Woodrow Wilson" in str(answer), answer
        dump(work / "original-result.json", {"answer": str(answer), "passed": True})
        return
    database = fixture(work)
    expected = oracle(database)
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    sql_tool = sql_adapter(ns, database, work, args.stage)
    if args.stage == "baseline":
        agent = CodeAgent(tools=[sql_tool], model=model, max_steps=15, verbosity_level=0)
        answer = agent.run(TASK)
        actual = answer if isinstance(answer, dict) else parse_json(str(answer))
        dump(
            work / "baseline-result.json",
            {"actual": actual, "expected": expected, "passed": actual == expected},
        )
        assert actual == expected, (actual, expected)
    elif args.stage == "generate":
        source = work / "source"
        source.mkdir(exist_ok=True)
        (source / "text_to_sql.py").write_bytes(
            (Path(args.upstream) / "examples/text_to_sql.py").read_bytes()
        )
        (source / "SKILL.md").write_text(
            TASK
            + """\nFor managed execution, retain a bounded state with:
completed_checks: array of unique checked field names (maximum five);
report: object containing exactly the five report fields with initial numeric values zero and top_customer empty.
When a SQL observation arrives, record that check and its result in state, then query the next check.
Only mark done when all five observed checks have been saved. SQL tool name is sql_engine, argument query.
""",
            encoding="utf-8",
        )
        prepared = prepare(work, "source", "sql-audit")
        prompt = {
            "task": "Generate a semantic skill proposal matching proposal_schema exactly. Name sql-audit. Include the actual SQL table schema from the source in instructions. Use bounded inline JSON Schema, additionalProperties=false, all fields required, no references. Return only the proposal JSON.",
            "prepared": prepared,
        }
        proposal = parse_json(model.complete(prompt))
        dump(work / "proposal.json", proposal)
        generated = generate(
            work,
            "source",
            name="sql-audit",
            proposal=proposal,
            expected_source_hash=prepared["inventory"]["source_hash"],
        )
        dump(work / "generation-result.json", generated)
        load_bundle(work, "sql-audit")
    else:
        bundle = load_bundle(work, "sql-audit")
        skill = Skill.from_dict(bundle["skill"])
        tool = Tool(
            "sql_engine",
            sql_tool.description,
            {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
                "additionalProperties": False,
            },
            lambda arguments, operation_id: ToolResult(True, {"result": sql_tool(**arguments)}),
        )
        with SQLiteStore(work / "state.sqlite3") as store:
            if args.stage == "managed-start":
                store.create("sql-audit-01", skill, "auditor", {"task": TASK})
            runtime = SkillRuntime(
                store,
                lambda ctx: parse_json(model.complete(ctx)),
                [tool],
                model_timeout=190,
                completion_check=lambda state: (
                    state["report"] == expected and set(state["completed_checks"]) == set(FIELDS)
                ),
            )
            if args.stage == "managed-start":
                for _ in range(3):
                    snapshot = await runtime.step("sql-audit-01", "auditor")
                dump(work / "interrupted-checkpoint.json", snapshot)
                print(
                    "FAULT INJECTION: terminating process after third committed SQL operation",
                    flush=True,
                )
                os._exit(75)
            snapshot = await runtime.run("sql-audit-01", "auditor", max_steps=15)
            assert snapshot["state"]["report"] == expected
            assert snapshot["status"] == "completed"
            dump(work / "managed-result.json", snapshot)
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before, "Agent changed receipt data"
    print(f"{args.stage}: PASS", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--codex", required=True)
    parser.add_argument(
        "stage", choices=["original", "baseline", "generate", "managed-start", "managed-resume"]
    )
    asyncio.run(main(parser.parse_args()))
