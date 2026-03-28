"""Tests for hardened temporary file handling in CLI agents (issue #13).

Verifies that TOCTOU vulnerabilities are eliminated and temp files are always
cleaned up, even when the subprocess fails or times out.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

import pytest

from clink.agents.base import BaseCLIAgent, CLIAgentError
from clink.agents.cursor import CursorAgent
from clink.models import OutputCaptureConfig, ResolvedCLIClient, ResolvedCLIRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class DummyProcess:
    """Fake asyncio subprocess that records how it was invoked."""

    def __init__(self, *, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self, input_data=None):
        return self._stdout, self._stderr

    def kill(self):
        pass


def _claude_stream_json_output(text: str = "ok", session_id: str = "test-sess") -> bytes:
    """Return bytes parseable by the claude_stream_json parser."""
    lines = [
        f'{{"type":"system","subtype":"init","cwd":"/home/test","session_id":"{session_id}","model":"test-model"}}',
        f'{{"type":"assistant","message":{{"role":"assistant","content":[{{"type":"text","text":"{text}"}}],"usage":{{"input_tokens":1,"output_tokens":1}}}},"session_id":"{session_id}"}}',
        f'{{"type":"result","subtype":"success","is_error":false,"duration_ms":100,"duration_api_ms":100,"result":"{text}","session_id":"{session_id}","total_cost_usd":0.01,"usage":{{"input_tokens":1,"output_tokens":1}},"modelUsage":{{"test-model":{{"inputTokens":1,"outputTokens":1}}}},"uuid":"test-uuid"}}',
    ]
    return "\n".join(lines).encode()


def _cursor_stream_json_output(text: str = "ok") -> bytes:
    lines = [
        '{"type":"system","subtype":"init","session_id":"s1","model":"test"}',
        f'{{"type":"assistant","message":{{"role":"assistant","content":[{{"type":"text","text":"{text}"}}]}}}}',
        f'{{"type":"result","subtype":"success","duration_ms":100,"duration_api_ms":100,"is_error":false,"result":"{text}","session_id":"s1","request_id":"r1"}}',
    ]
    return "\n".join(lines).encode()


def _make_client(*, name: str = "test-cli", output_to_file: OutputCaptureConfig | None = None) -> ResolvedCLIClient:
    prompt_path = Path("systemprompts/clink/default.txt").resolve()
    role = ResolvedCLIRole(name="default", prompt_path=prompt_path, role_args=[])
    return ResolvedCLIClient(
        name=name,
        executable=["test-cli"],
        internal_args=[],
        config_args=[],
        env={},
        timeout_seconds=2,
        parser="claude_stream_json",
        roles={"default": role},
        output_to_file=output_to_file,
        working_dir=None,
    )


def _make_cursor_client(*, output_to_file: OutputCaptureConfig | None = None) -> ResolvedCLIClient:
    prompt_path = Path("systemprompts/clink/default.txt").resolve()
    role = ResolvedCLIRole(name="default", prompt_path=prompt_path, role_args=[])
    return ResolvedCLIClient(
        name="cursor",
        executable=["agent"],
        internal_args=["--print", "--output-format", "stream-json"],
        config_args=[],
        env={},
        timeout_seconds=2,
        parser="cursor_stream_json",
        runner="cursor",
        roles={"default": role},
        output_to_file=output_to_file,
        working_dir=None,
    )


def _extract_output_path_from_command(sanitized_command: list[str], flag: str = "--output") -> Path:
    """Extract the temp file path from the sanitized command list."""
    idx = sanitized_command.index(flag)
    return Path(sanitized_command[idx + 1])


async def _run_base_agent(monkeypatch, client, process):
    role = client.roles["default"]
    agent = BaseCLIAgent(client)

    async def fake_create(*_a, **_kw):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")

    return await agent.run(
        role=role,
        prompt="test prompt",
        system_prompt=None,
        files=[],
        images=[],
    )


async def _run_cursor_agent(monkeypatch, client, process):
    role = client.roles["default"]
    agent = CursorAgent(client)

    async def fake_create(*_a, **_kw):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")

    return await agent.run(
        role=role,
        prompt="test prompt",
        system_prompt=None,
        files=[],
        images=[],
    )


def _make_hanging_process_factory():
    """Create a process factory that hangs on first communicate, returns on second."""
    call_count = 0

    class HangingProcess:
        returncode = -9

        def kill(self):
            pass

        async def communicate(self, input_data=None):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                return b"", b""
            await asyncio.sleep(999)

    async def factory(*_a, **_kw):
        return HangingProcess()

    return factory


# ---------------------------------------------------------------------------
# Tests: BaseCLIAgent temp file hardening
# ---------------------------------------------------------------------------


class TestBaseCLIAgentTempFileHardening:
    """Verify BaseCLIAgent no longer has TOCTOU temp file vulnerability."""

    @pytest.mark.asyncio
    async def test_no_mkstemp_followed_by_close(self, monkeypatch):
        """Ensure mkstemp+os.close pattern is NOT used (TOCTOU vulnerability)."""
        import clink.agents.base as base_mod

        mkstemp_called = False
        real_mkstemp = tempfile.mkstemp

        def tracking_mkstemp(*args, **kwargs):
            nonlocal mkstemp_called
            mkstemp_called = True
            return real_mkstemp(*args, **kwargs)

        monkeypatch.setattr(base_mod.tempfile, "mkstemp", tracking_mkstemp)

        output_config = OutputCaptureConfig(flag_template="--output {path}", cleanup=True)
        client = _make_client(output_to_file=output_config)
        process = DummyProcess(stdout=_claude_stream_json_output())

        await _run_base_agent(monkeypatch, client, process)

        assert not mkstemp_called, "mkstemp should not be used; use NamedTemporaryFile instead"

    @pytest.mark.asyncio
    async def test_tempfile_cleaned_up_on_success(self, monkeypatch):
        """Temp file should be removed after successful execution when cleanup=True."""
        output_config = OutputCaptureConfig(flag_template="--output {path}", cleanup=True)
        client = _make_client(output_to_file=output_config)
        process = DummyProcess(stdout=_claude_stream_json_output())

        result = await _run_base_agent(monkeypatch, client, process)

        tmp_path = _extract_output_path_from_command(result.sanitized_command)
        assert not tmp_path.exists(), "Temp file should be cleaned up after success"

    @pytest.mark.asyncio
    async def test_tempfile_cleaned_up_on_subprocess_error(self, monkeypatch):
        """Temp file should be removed even when subprocess returns non-zero."""
        created_paths: list[Path] = []
        import clink.agents.base as base_mod

        real_ntf = tempfile.NamedTemporaryFile

        def tracking_ntf(*args, **kwargs):
            f = real_ntf(*args, **kwargs)
            created_paths.append(Path(f.name))
            return f

        monkeypatch.setattr(base_mod.tempfile, "NamedTemporaryFile", tracking_ntf)

        output_config = OutputCaptureConfig(flag_template="--output {path}", cleanup=True)
        client = _make_client(output_to_file=output_config)
        process = DummyProcess(stdout=b"", stderr=b"error", returncode=1)

        with pytest.raises(CLIAgentError):
            await _run_base_agent(monkeypatch, client, process)

        assert len(created_paths) == 1
        assert not created_paths[0].exists(), "Temp file should be cleaned up after error"

    @pytest.mark.asyncio
    async def test_tempfile_cleaned_up_on_timeout(self, monkeypatch):
        """Temp file should be removed even when subprocess times out."""
        created_paths: list[Path] = []
        import clink.agents.base as base_mod

        real_ntf = tempfile.NamedTemporaryFile

        def tracking_ntf(*args, **kwargs):
            f = real_ntf(*args, **kwargs)
            created_paths.append(Path(f.name))
            return f

        monkeypatch.setattr(base_mod.tempfile, "NamedTemporaryFile", tracking_ntf)

        output_config = OutputCaptureConfig(flag_template="--output {path}", cleanup=True)
        client = _make_client(output_to_file=output_config)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _make_hanging_process_factory())
        monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")

        role = client.roles["default"]
        agent = BaseCLIAgent(client)

        with pytest.raises(CLIAgentError, match="timed out"):
            await agent.run(role=role, prompt="test", system_prompt=None, files=[], images=[])

        assert len(created_paths) == 1
        assert not created_paths[0].exists(), "Temp file should be cleaned up after timeout"

    @pytest.mark.asyncio
    async def test_tempfile_preserved_when_cleanup_false(self, monkeypatch):
        """Temp file should NOT be removed when cleanup=False."""
        output_config = OutputCaptureConfig(flag_template="--output {path}", cleanup=False)
        client = _make_client(output_to_file=output_config)
        process = DummyProcess(stdout=_claude_stream_json_output())

        result = await _run_base_agent(monkeypatch, client, process)

        tmp_path = _extract_output_path_from_command(result.sanitized_command)
        try:
            assert tmp_path.exists(), "Temp file should be preserved when cleanup=False"
        finally:
            tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Tests: CursorAgent temp file hardening
# ---------------------------------------------------------------------------


class TestCursorAgentTempFileHardening:
    """Verify CursorAgent no longer has TOCTOU temp file vulnerability."""

    @pytest.mark.asyncio
    async def test_no_mkstemp_used(self, monkeypatch):
        """CursorAgent should not use mkstemp (TOCTOU vulnerability)."""
        import clink.agents.cursor as cursor_mod

        mkstemp_called = False
        real_mkstemp = tempfile.mkstemp

        def tracking_mkstemp(*args, **kwargs):
            nonlocal mkstemp_called
            mkstemp_called = True
            return real_mkstemp(*args, **kwargs)

        monkeypatch.setattr(cursor_mod.tempfile, "mkstemp", tracking_mkstemp)

        output_config = OutputCaptureConfig(flag_template="--output {path}", cleanup=True)
        client = _make_cursor_client(output_to_file=output_config)
        process = DummyProcess(stdout=_cursor_stream_json_output())

        await _run_cursor_agent(monkeypatch, client, process)

        assert not mkstemp_called, "mkstemp should not be used; use NamedTemporaryFile instead"

    @pytest.mark.asyncio
    async def test_tempfile_cleaned_up_on_success(self, monkeypatch):
        """CursorAgent temp file should be removed after success."""
        created_paths: list[Path] = []
        import clink.agents.cursor as cursor_mod

        real_ntf = tempfile.NamedTemporaryFile

        def tracking_ntf(*args, **kwargs):
            f = real_ntf(*args, **kwargs)
            created_paths.append(Path(f.name))
            return f

        monkeypatch.setattr(cursor_mod.tempfile, "NamedTemporaryFile", tracking_ntf)

        output_config = OutputCaptureConfig(flag_template="--output={path}", cleanup=True)
        client = _make_cursor_client(output_to_file=output_config)
        process = DummyProcess(stdout=_cursor_stream_json_output())

        await _run_cursor_agent(monkeypatch, client, process)

        assert len(created_paths) == 1
        assert not created_paths[0].exists(), "Temp file should be cleaned up after success"

    @pytest.mark.asyncio
    async def test_tempfile_cleaned_up_on_error(self, monkeypatch):
        """CursorAgent temp file should be removed even on subprocess error."""
        created_paths: list[Path] = []
        import clink.agents.cursor as cursor_mod

        real_ntf = tempfile.NamedTemporaryFile

        def tracking_ntf(*args, **kwargs):
            f = real_ntf(*args, **kwargs)
            created_paths.append(Path(f.name))
            return f

        monkeypatch.setattr(cursor_mod.tempfile, "NamedTemporaryFile", tracking_ntf)

        output_config = OutputCaptureConfig(flag_template="--output={path}", cleanup=True)
        client = _make_cursor_client(output_to_file=output_config)
        process = DummyProcess(stdout=b"", returncode=1)

        with pytest.raises(CLIAgentError):
            await _run_cursor_agent(monkeypatch, client, process)

        assert len(created_paths) == 1
        assert not created_paths[0].exists(), "Temp file should be cleaned up after error"

    @pytest.mark.asyncio
    async def test_tempfile_cleaned_up_on_timeout(self, monkeypatch):
        """CursorAgent temp file should be removed even on timeout."""
        created_paths: list[Path] = []
        import clink.agents.cursor as cursor_mod

        real_ntf = tempfile.NamedTemporaryFile

        def tracking_ntf(*args, **kwargs):
            f = real_ntf(*args, **kwargs)
            created_paths.append(Path(f.name))
            return f

        monkeypatch.setattr(cursor_mod.tempfile, "NamedTemporaryFile", tracking_ntf)

        output_config = OutputCaptureConfig(flag_template="--output={path}", cleanup=True)
        client = _make_cursor_client(output_to_file=output_config)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _make_hanging_process_factory())
        monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")

        role = client.roles["default"]
        agent = CursorAgent(client)

        with pytest.raises(CLIAgentError, match="timed out"):
            await agent.run(role=role, prompt="test", system_prompt=None, files=[], images=[])

        assert len(created_paths) == 1
        assert not created_paths[0].exists(), "Temp file should be cleaned up after timeout"

    @pytest.mark.asyncio
    async def test_tempfile_preserved_when_cleanup_false(self, monkeypatch):
        """CursorAgent temp file should NOT be removed when cleanup=False."""
        created_paths: list[Path] = []
        import clink.agents.cursor as cursor_mod

        real_ntf = tempfile.NamedTemporaryFile

        def tracking_ntf(*args, **kwargs):
            f = real_ntf(*args, **kwargs)
            created_paths.append(Path(f.name))
            return f

        monkeypatch.setattr(cursor_mod.tempfile, "NamedTemporaryFile", tracking_ntf)

        output_config = OutputCaptureConfig(flag_template="--output={path}", cleanup=False)
        client = _make_cursor_client(output_to_file=output_config)
        process = DummyProcess(stdout=_cursor_stream_json_output())

        await _run_cursor_agent(monkeypatch, client, process)

        assert len(created_paths) == 1
        try:
            assert created_paths[0].exists(), "Temp file should be preserved when cleanup=False"
        finally:
            created_paths[0].unlink(missing_ok=True)
