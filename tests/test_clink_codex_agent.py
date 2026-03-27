import asyncio
import shutil
from pathlib import Path

import pytest

from clink.agents.base import CLIAgentError
from clink.agents.codex import CodexAgent
from clink.models import ResolvedCLIClient, ResolvedCLIRole


class DummyProcess:
    def __init__(self, *, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self, _input):
        return self._stdout, self._stderr


@pytest.fixture()
def codex_agent():
    prompt_path = Path("systemprompts/clink/codex_default.txt").resolve()
    role = ResolvedCLIRole(name="default", prompt_path=prompt_path, role_args=[])
    client = ResolvedCLIClient(
        name="codex",
        executable=["codex"],
        internal_args=["exec"],
        config_args=["--json", "--dangerously-bypass-approvals-and-sandbox"],
        env={},
        timeout_seconds=30,
        parser="codex_jsonl",
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )
    return CodexAgent(client), role


async def _run_agent_with_process(monkeypatch, agent, role, process):
    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return process

    def fake_which(executable_name):
        return f"/usr/bin/{executable_name}"

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(shutil, "which", fake_which)
    return await agent.run(role=role, prompt="do something", files=[], images=[])


@pytest.mark.asyncio
async def test_codex_agent_recovers_jsonl(monkeypatch, codex_agent):
    """Test Codex agent recovery with JSONL output (codex-cli 0.91.0 format)."""
    agent, role = codex_agent
    # Real output format from codex-cli 0.91.0
    stdout = b"""{"type":"thread.started","thread_id":"019c0cf5-ee41-7b41-8cfb-9669a8dedf99"}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"Hello from Codex"}}
{"type":"turn.completed","usage":{"input_tokens":21688,"cached_input_tokens":4608,"output_tokens":19}}
"""
    process = DummyProcess(stdout=stdout, returncode=124)
    result = await _run_agent_with_process(monkeypatch, agent, role, process)

    assert result.returncode == 124
    assert "Hello from Codex" in result.parsed.content
    assert result.parsed.metadata["usage"]["output_tokens"] == 19
    # Session ID should be extracted from thread_id
    assert result.parsed.metadata["session_id"] == "019c0cf5-ee41-7b41-8cfb-9669a8dedf99"


@pytest.mark.asyncio
async def test_codex_agent_propagates_invalid_json(monkeypatch, codex_agent):
    agent, role = codex_agent
    stdout = b"not json"
    process = DummyProcess(stdout=stdout, returncode=1)

    with pytest.raises(CLIAgentError):
        await _run_agent_with_process(monkeypatch, agent, role, process)
