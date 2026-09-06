import asyncio
import json
import os
import subprocess
import sys

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from skillstate import ValidationError
from skillstate.cli import main
from skillstate.compiler import generate
from skillstate.providers import JSONChatModel


def test_cli_generate_open_update_context(project, capsys):
    prefix = ["--project", str(project)]
    assert main(prefix + ["init"]) == 0
    capsys.readouterr()
    assert main(prefix + ["generate", "skills/qa/SKILL.md", "--install"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["name"] == "qa-state"
    assert main(prefix + ["run", "open", "qa-state", "--owner", "codex", "--id", "test"]) == 0
    capsys.readouterr()
    (project / "patch.json").write_text('[{"op":"set","path":"/goal","value":"working"}]')
    assert (
        main(
            prefix
            + [
                "run",
                "update",
                "test",
                "--owner",
                "codex",
                "--revision",
                "0",
                "--patch",
                "patch.json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(prefix + ["run", "context", "test"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["context"]["state"]["goal"] == "working"
    assert result["revision"] == 1
    assert main(prefix + ["validate", "qa-state"]) == 0


def test_cli_errors_are_structured(project, capsys):
    assert main(["--project", str(project), "generate", "../escape"]) == 2
    assert json.loads(capsys.readouterr().err)["error"] == "validation_error"
    assert main(["--project", str(project), "doctor"]) == 1


def test_cli_installed_entrypoint_and_demo():
    result = subprocess.run(
        [sys.executable, "-m", "skillstate", "demo"], capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "completed"


def test_http_adapter_is_stateless_and_parses_json():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"ok":true}'}}]})

    model = JSONChatModel(
        "https://example.invalid/v1",
        "configured-model",
        "not-a-real-key",
        transport=httpx.MockTransport(handler),
    )
    assert asyncio.run(model({"state": {"step": 1}})) == {"ok": True}
    assert asyncio.run(model({"state": {"step": 2}})) == {"ok": True}
    assert len(requests[1]["messages"]) == 2
    assert 'step":1' not in requests[1]["messages"][1]["content"]


@pytest.mark.parametrize("status", [401, 429, 500, 302])
def test_http_errors_do_not_leak_response_or_key(status):
    model = JSONChatModel(
        "https://example.invalid",
        "model",
        "private-key",
        transport=httpx.MockTransport(lambda r: httpx.Response(status, text="sensitive-body")),
    )
    with pytest.raises(ValidationError) as caught:
        asyncio.run(model({}))
    assert "sensitive-body" not in str(caught.value)
    assert "private-key" not in str(caught.value)


def test_real_stdio_mcp_session(project):
    """Actual SDK client/server transport, not a mock tool invocation."""
    generate(project, "skills/qa/SKILL.md")

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "skillstate", "--project", str(project), "serve"],
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
            await client.initialize()
            tools = await client.list_tools()
            assert "run_context" in {t.name for t in tools.tools}
            opened = await client.call_tool(
                "run_open",
                {"name": "qa-state", "owner": "codex", "observation": {}, "run_id": "mcp-run"},
            )
            assert not opened.isError
            changed = await client.call_tool(
                "run_update",
                {
                    "run_id": "mcp-run",
                    "owner": "codex",
                    "revision": 0,
                    "patch": [{"op": "set", "path": "/goal", "value": "MCP works"}],
                },
            )
            assert not changed.isError
            context = await client.call_tool("run_context", {"run_id": "mcp-run"})
            assert "MCP works" in str(context)
            bad = await client.call_tool(
                "run_update", {"run_id": "mcp-run", "owner": "codex", "revision": 0, "patch": []}
            )
            assert bad.isError

    asyncio.run(asyncio.wait_for(exercise(), timeout=30))


def test_cli_uncertain_operation_reconciliation_and_handoff(project, capsys):
    def call(*args, code=0):
        assert main(["--project", str(project), *args]) == code
        captured = capsys.readouterr()
        return json.loads(captured.out if code == 0 else captured.err)

    call("generate", "skills/qa/SKILL.md")
    call("run", "open", "qa-state", "--owner", "codex", "--id", "effect")
    (project / "decision.json").write_text(
        json.dumps(
            {
                "action": {"name": "test", "arguments": {}},
                "patch": [{"op": "set", "path": "/goal", "value": "verified"}],
            }
        )
    )
    reserved = call(
        "run",
        "reserve",
        "effect",
        "--owner",
        "codex",
        "--revision",
        "0",
        "--decision",
        "decision.json",
    )
    operation = reserved["operation_id"]
    assert reserved["run"]["state"]["goal"] != "verified"
    call("run", "unknown", operation, "--owner", "codex")
    (project / "result.json").write_text('{"success":true,"observation":{"verified":true}}')
    call("run", "result", operation, "--owner", "codex", "--result", "result.json", code=2)
    reconciled = call(
        "run", "result", operation, "--owner", "codex", "--result", "result.json", "--reconcile"
    )
    assert reconciled["state"]["goal"] == "verified"
    transferred = call(
        "run",
        "handoff",
        "effect",
        "--owner",
        "codex",
        "--revision",
        str(reconciled["revision"]),
        "--to",
        "claude-code",
    )
    assert transferred["owner"] == "claude-code"
    events = call("run", "events", "effect")
    assert [event["kind"] for event in events] == [
        "created",
        "reserved",
        "unknown",
        "result",
        "handoff",
    ]
    assert call("status")[0]["owner"] == "claude-code"
    (project / "evidence.txt").write_text("verified evidence", encoding="utf-8")
    artifact = call("artifact", "put", "evidence.txt")
    assert call("artifact", "read", artifact["id"])["content"] == "verified evidence"


def test_cli_semantic_generation_and_real_doctor(project, capsys):
    from skillstate.compiler import tracking_ir

    prefix = ["--project", str(project)]
    assert main(prefix + ["generate", "skills/qa/SKILL.md", "--prepare"]) == 0
    request = json.loads(capsys.readouterr().out)
    (project / "proposal.json").write_text(json.dumps(tracking_ir(request["inventory"])))
    command = prefix + ["generate", "skills/qa/SKILL.md", "--proposal", "proposal.json"]
    assert main(command) == 2
    capsys.readouterr()
    assert main(command + ["--source-hash", request["inventory"]["source_hash"], "--install"]) == 0
    assert json.loads(capsys.readouterr().out)["mode"] == "semantic"
    assert main(prefix + ["init", "--mcp"]) == 0
    capsys.readouterr()
    assert main(prefix + ["doctor", "--mcp"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mcp_transport"]["tool_count"] == 12
    assert main(prefix + ["uninstall"]) == 0


def test_doctor_transport_failure_is_nonzero(project, capsys, monkeypatch):
    from skillstate import mcp_server
    from skillstate.hosts import install

    install(project, mcp=True)

    async def unavailable(project):
        raise TimeoutError("private detail")

    monkeypatch.setattr(mcp_server, "smoke_test", unavailable)
    assert main(["--project", str(project), "doctor", "--mcp"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["mcp_transport"] == {"ok": False, "error": "TimeoutError"}


@pytest.mark.parametrize(
    "response",
    [
        {"choices": []},
        {"choices": [{"message": {"content": None}}]},
        {"choices": [{"message": {"content": "not json"}}]},
    ],
)
def test_http_malformed_output_is_rejected(response):
    model = JSONChatModel(
        "https://example.invalid",
        "test",
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=response)),
    )
    with pytest.raises(ValidationError):
        asyncio.run(model({}))


def test_http_transport_failure_hides_sensitive_url():
    def fail(request):
        raise httpx.ConnectError("sensitive upstream detail", request=request)

    model = JSONChatModel("https://example.invalid", "test", transport=httpx.MockTransport(fail))
    with pytest.raises(ValidationError, match="ConnectError") as caught:
        asyncio.run(model({}))
    assert "sensitive" not in str(caught.value)
