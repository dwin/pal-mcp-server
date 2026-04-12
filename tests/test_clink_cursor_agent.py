"""Tests for Cursor CLI agent (agent 2026.01.28-fd13201)."""

import asyncio
import shutil
from pathlib import Path

import pytest

from clink.agents.base import CLIAgentError
from clink.agents.cursor import CursorAgent
from clink.models import ResolvedCLIClient, ResolvedCLIRole


class DummyProcess:
    def __init__(self, *, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self, input_data=None):
        return self._stdout, self._stderr


def _build_stream_json_output(result: str, session_id: str, is_error: bool = False) -> bytes:
    """Build stream-json output matching cursor-agent 2026.01.28-fd13201 format."""
    lines = [
        f'{{"type":"system","subtype":"init","session_id":"{session_id}","model":"Claude 4.5 Opus"}}',
        f'{{"type":"assistant","message":{{"role":"assistant","content":[{{"type":"text","text":"{result}"}}]}}}}',
        f'{{"type":"result","subtype":"success","duration_ms":4259,"duration_api_ms":4259,"is_error":{str(is_error).lower()},"result":"{result}","session_id":"{session_id}","request_id":"test-request-id"}}',
    ]
    return "\n".join(lines).encode()


@pytest.fixture()
def cursor_agent():
    prompt_path = Path("systemprompts/clink/default.txt").resolve()
    role = ResolvedCLIRole(name="default", prompt_path=prompt_path, role_args=[])
    client = ResolvedCLIClient(
        name="cursor",
        executable=["agent"],
        internal_args=["--print", "--output-format", "stream-json"],
        config_args=[],
        env={},
        timeout_seconds=30,
        parser="cursor_stream_json",
        runner="cursor",
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )
    return CursorAgent(client), role


async def _run_agent_with_process(monkeypatch, agent, role, process):
    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return process

    def fake_which(executable_name):
        return f"/usr/local/bin/{executable_name}"

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(shutil, "which", fake_which)

    return await agent.run(
        role=role,
        prompt="Respond with hello",
        system_prompt=None,
        files=[],
        images=[],
    )


@pytest.mark.asyncio
async def test_cursor_agent_parses_stream_json_output(monkeypatch, cursor_agent):
    """Test Cursor agent parsing stream-json output (agent 2026.01.28 format)."""
    agent, role = cursor_agent
    stdout_payload = _build_stream_json_output(
        result="Hello! I'm ready to help you.",
        session_id="1de65ac7-bd7d-4058-bc98-15d781ecfff7",
    )
    process = DummyProcess(stdout=stdout_payload)

    result = await _run_agent_with_process(monkeypatch, agent, role, process)

    assert result.returncode == 0
    assert "Hello" in result.parsed.content
    # Session ID should be extracted
    assert result.parsed.metadata["session_id"] == "1de65ac7-bd7d-4058-bc98-15d781ecfff7"
    assert result.parsed.metadata["request_id"] == "test-request-id"
    assert result.parsed.metadata["duration_ms"] == 4259
    assert result.parsed.metadata["model_used"] == "Claude 4.5 Opus"


@pytest.mark.asyncio
async def test_cursor_agent_recovers_error_payload(monkeypatch, cursor_agent):
    """Test Cursor agent recovery from non-zero exit with valid stream-json."""
    agent, role = cursor_agent
    stdout_payload = _build_stream_json_output(
        result="API Error occurred",
        session_id="abc-123",
        is_error=True,
    )
    process = DummyProcess(stdout=stdout_payload, returncode=2)

    result = await _run_agent_with_process(monkeypatch, agent, role, process)

    assert result.returncode == 2
    assert result.parsed.content == "API Error occurred"
    assert result.parsed.metadata["is_error"] is True
    assert result.parsed.metadata["session_id"] == "abc-123"


@pytest.mark.asyncio
async def test_cursor_agent_propagates_unparseable_output(monkeypatch, cursor_agent):
    """Test Cursor agent raises error for invalid output."""
    agent, role = cursor_agent
    process = DummyProcess(stdout=b"", returncode=1)

    with pytest.raises(CLIAgentError):
        await _run_agent_with_process(monkeypatch, agent, role, process)


@pytest.mark.asyncio
async def test_cursor_agent_passes_prompt_as_argument(monkeypatch, cursor_agent):
    """Test that Cursor agent passes prompt as CLI argument, not stdin."""
    agent, role = cursor_agent
    stdout_payload = _build_stream_json_output(
        result="Hello",
        session_id="test-session",
    )
    process = DummyProcess(stdout=stdout_payload)

    result = await _run_agent_with_process(monkeypatch, agent, role, process)

    # Prompt should be in the command line, not stdin
    assert "Respond with hello" in result.sanitized_command
