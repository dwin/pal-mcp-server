"""Tests for Claude CLI agent (claude 2.1.25)."""

import asyncio
import shutil
from pathlib import Path

import pytest

from clink.agents.base import CLIAgentError
from clink.agents.claude import ClaudeAgent
from clink.models import ResolvedCLIClient, ResolvedCLIRole


class DummyProcess:
    def __init__(self, *, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.stdin_data: bytes | None = None

    async def communicate(self, input_data):
        self.stdin_data = input_data
        return self._stdout, self._stderr


def _build_stream_json_output(
    result: str, session_id: str, is_error: bool = False, model: str = "claude-opus-4-5-20251101"
) -> bytes:
    """Build stream-json output matching claude 2.1.25 format."""
    lines = [
        f'{{"type":"system","subtype":"init","cwd":"/Users/test/project","session_id":"{session_id}","model":"{model}"}}',
        f'{{"type":"assistant","message":{{"role":"assistant","content":[{{"type":"text","text":"{result}"}}],"usage":{{"input_tokens":2,"output_tokens":45}}}},"session_id":"{session_id}"}}',
        f'{{"type":"result","subtype":"success","is_error":{str(is_error).lower()},"duration_ms":5259,"duration_api_ms":4193,"result":"{result}","session_id":"{session_id}","total_cost_usd":0.252285,"usage":{{"input_tokens":2,"output_tokens":45}},"modelUsage":{{"{model}":{{"inputTokens":2,"outputTokens":45}}}},"uuid":"040767a8-2e27-4eee-a816-2d278640f4cb"}}',
    ]
    return "\n".join(lines).encode()


@pytest.fixture()
def claude_agent():
    prompt_path = Path("systemprompts/clink/default.txt").resolve()
    role = ResolvedCLIRole(name="default", prompt_path=prompt_path, role_args=[])
    client = ResolvedCLIClient(
        name="claude",
        executable=["claude"],
        internal_args=["--print", "--output-format", "stream-json", "--verbose"],
        config_args=["--permission-mode", "acceptEdits"],
        env={},
        timeout_seconds=30,
        parser="claude_stream_json",
        runner="claude",
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )
    return ClaudeAgent(client), role


async def _run_agent_with_process(monkeypatch, agent, role, process, *, system_prompt="System prompt"):
    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return process

    def fake_which(executable_name):
        return f"/usr/bin/{executable_name}"

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(shutil, "which", fake_which)

    return await agent.run(
        role=role,
        prompt="Respond with 42",
        system_prompt=system_prompt,
        files=[],
        images=[],
    )


@pytest.mark.asyncio
async def test_claude_agent_injects_system_prompt(monkeypatch, claude_agent):
    """Test Claude agent with system prompt injection (claude 2.1.25 stream-json format)."""
    agent, role = claude_agent
    stdout_payload = _build_stream_json_output(
        result="42",
        session_id="a7d3f253-2065-498f-8546-7aa348a65903",
    )
    process = DummyProcess(stdout=stdout_payload)

    result = await _run_agent_with_process(monkeypatch, agent, role, process)

    assert "--append-system-prompt" in result.sanitized_command
    idx = result.sanitized_command.index("--append-system-prompt")
    assert result.sanitized_command[idx + 1] == "System prompt"
    assert process.stdin_data.decode().startswith("Respond with 42")
    # Session ID should be extracted
    assert result.parsed.metadata["session_id"] == "a7d3f253-2065-498f-8546-7aa348a65903"
    assert result.parsed.metadata["model_used"] == "claude-opus-4-5-20251101"


@pytest.mark.asyncio
async def test_claude_agent_recovers_error_payload(monkeypatch, claude_agent):
    """Test Claude agent recovery from non-zero exit with valid stream-json."""
    agent, role = claude_agent
    stdout_payload = _build_stream_json_output(
        result="API Error",
        session_id="abc-123",
        is_error=True,
    )
    process = DummyProcess(stdout=stdout_payload, returncode=2)

    result = await _run_agent_with_process(monkeypatch, agent, role, process)

    assert result.returncode == 2
    assert result.parsed.content == "API Error"
    assert result.parsed.metadata["is_error"] is True
    assert result.parsed.metadata["session_id"] == "abc-123"


@pytest.mark.asyncio
async def test_claude_agent_propagates_unparseable_output(monkeypatch, claude_agent):
    """Test Claude agent raises error for invalid output."""
    agent, role = claude_agent
    process = DummyProcess(stdout=b"", returncode=1)

    with pytest.raises(CLIAgentError):
        await _run_agent_with_process(monkeypatch, agent, role, process)


@pytest.mark.asyncio
async def test_claude_agent_extracts_metrics(monkeypatch, claude_agent):
    """Test Claude agent extracts duration and cost metrics."""
    agent, role = claude_agent
    stdout_payload = _build_stream_json_output(
        result="Hello",
        session_id="test-session",
    )
    process = DummyProcess(stdout=stdout_payload)

    result = await _run_agent_with_process(monkeypatch, agent, role, process)

    assert result.parsed.metadata["duration_ms"] == 5259
    assert result.parsed.metadata["duration_api_ms"] == 4193
    assert result.parsed.metadata["total_cost_usd"] == 0.252285
    assert result.parsed.metadata["uuid"] == "040767a8-2e27-4eee-a816-2d278640f4cb"
