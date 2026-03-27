"""Tests for Gemini CLI agent (gemini-cli 0.26.0)."""

import asyncio
import shutil
from pathlib import Path

import pytest

from clink.agents.base import CLIAgentError
from clink.agents.gemini import GeminiAgent
from clink.models import ResolvedCLIClient, ResolvedCLIRole


class DummyProcess:
    def __init__(self, *, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self, _input):
        return self._stdout, self._stderr


def _build_stream_json_output(content: str, session_id: str, model: str = "gemini-3-flash-preview") -> bytes:
    """Build stream-json output matching gemini-cli 0.26.0 format."""
    lines = [
        f'{{"type":"init","timestamp":"2026-01-30T04:28:26.132Z","session_id":"{session_id}","model":"{model}"}}',
        '{"type":"message","timestamp":"2026-01-30T04:28:26.132Z","role":"user","content":"do something"}',
        f'{{"type":"message","timestamp":"2026-01-30T04:28:30.825Z","role":"assistant","content":"{content}","delta":true}}',
        '{"type":"result","timestamp":"2026-01-30T04:28:30.837Z","status":"success","stats":{"total_tokens":11785,"input_tokens":11598,"output_tokens":69,"duration_ms":4705}}',
    ]
    return "\n".join(lines).encode()


@pytest.fixture()
def gemini_agent():
    prompt_path = Path("systemprompts/clink/default.txt").resolve()
    role = ResolvedCLIRole(name="default", prompt_path=prompt_path, role_args=[])
    client = ResolvedCLIClient(
        name="gemini",
        executable=["gemini"],
        internal_args=["--output-format", "stream-json"],
        config_args=[],
        env={},
        timeout_seconds=30,
        parser="gemini_stream_json",
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )
    return GeminiAgent(client), role


async def _run_agent_with_process(monkeypatch, agent, role, process):
    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return process

    def fake_which(executable_name):
        return f"/usr/bin/{executable_name}"

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(shutil, "which", fake_which)
    return await agent.run(role=role, prompt="do something", files=[], images=[])


@pytest.mark.asyncio
async def test_gemini_agent_parses_stream_json_output(monkeypatch, gemini_agent):
    """Test Gemini agent parsing stream-json output (gemini-cli 0.26.0 format)."""
    agent, role = gemini_agent
    stdout_payload = _build_stream_json_output(
        content="Hello! How can I help you today?",
        session_id="7bffa130-8c69-4cf8-ac8a-0d36b2d99f53",
    )
    process = DummyProcess(stdout=stdout_payload)

    result = await _run_agent_with_process(monkeypatch, agent, role, process)

    assert result.returncode == 0
    assert "Hello" in result.parsed.content
    assert result.parsed.metadata["session_id"] == "7bffa130-8c69-4cf8-ac8a-0d36b2d99f53"
    assert result.parsed.metadata["model_used"] == "gemini-3-flash-preview"
    assert result.parsed.metadata["latency_ms"] == 4705


@pytest.mark.asyncio
async def test_gemini_agent_recovers_tool_error(monkeypatch, gemini_agent):
    """Test Gemini agent recovers from tool execution errors."""
    agent, role = gemini_agent
    error_json = """{
  "error": {
    "type": "FatalToolExecutionError",
    "message": "Error executing tool replace: Failed to edit",
    "code": "edit_expected_occurrence_mismatch"
  }
}"""
    stderr = ("Error: Failed to edit, expected 1 occurrence but found 2.\n" + error_json).encode()
    process = DummyProcess(stderr=stderr, returncode=54)

    result = await _run_agent_with_process(monkeypatch, agent, role, process)

    assert result.returncode == 54
    assert result.parsed.metadata["cli_error_recovered"] is True
    assert result.parsed.metadata["cli_error_code"] == "edit_expected_occurrence_mismatch"
    assert "Gemini CLI reported a tool failure" in result.parsed.content


@pytest.mark.asyncio
async def test_gemini_agent_propagates_unrecoverable_error(monkeypatch, gemini_agent):
    """Test Gemini agent raises error for unrecoverable failures."""
    agent, role = gemini_agent
    stderr = b"Plain failure without structured payload"
    process = DummyProcess(stderr=stderr, returncode=54)

    with pytest.raises(CLIAgentError):
        await _run_agent_with_process(monkeypatch, agent, role, process)
