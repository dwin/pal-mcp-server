"""Tests for clink CLI session resumption functionality."""

import pytest

from clink.constants import RESUME_CONFIG


class TestCLIResumeConfig:
    """Tests for CLIResumeConfig dataclass."""

    def test_resume_config_exists_for_all_supported_clis(self):
        """Verify resume configuration exists for all supported CLIs."""
        expected_clis = {"claude", "gemini", "cursor", "codex"}
        assert set(RESUME_CONFIG.keys()) == expected_clis

    def test_claude_uses_flag_style(self):
        """Test Claude uses --resume flag style."""
        config = RESUME_CONFIG["claude"]
        assert config.flag == "--resume"
        assert config.style == "flag"

    def test_gemini_uses_flag_style(self):
        """Test Gemini uses --resume flag style."""
        config = RESUME_CONFIG["gemini"]
        assert config.flag == "--resume"
        assert config.style == "flag"

    def test_cursor_uses_flag_style(self):
        """Test Cursor uses --resume flag style."""
        config = RESUME_CONFIG["cursor"]
        assert config.flag == "--resume"
        assert config.style == "flag"

    def test_codex_uses_subcommand_style(self):
        """Test Codex uses subcommand style (exec resume <id>)."""
        config = RESUME_CONFIG["codex"]
        assert config.flag == "resume"
        assert config.style == "subcommand"
        assert config.insert_position == "after:exec"


class TestBuildCommandWithResume:
    """Tests for _build_command with cli_session_id."""

    @pytest.fixture
    def mock_client_claude(self):
        """Create a mock Claude client configuration."""
        from pathlib import Path

        from clink.models import ResolvedCLIClient, ResolvedCLIRole

        role = ResolvedCLIRole(
            name="default",
            prompt_path=Path("systemprompts/clink/default.txt"),
            role_args=[],
        )
        return ResolvedCLIClient(
            name="claude",
            executable=["claude"],
            internal_args=["--print", "--output-format", "stream-json", "--verbose"],
            config_args=[],
            env={},
            timeout_seconds=30,
            parser="claude_stream_json",
            roles={"default": role},
            output_to_file=None,
            working_dir=None,
            runner="claude",
        )

    @pytest.fixture
    def mock_client_codex(self):
        """Create a mock Codex client configuration."""
        from pathlib import Path

        from clink.models import ResolvedCLIClient, ResolvedCLIRole

        role = ResolvedCLIRole(
            name="default",
            prompt_path=Path("systemprompts/clink/default.txt"),
            role_args=[],
        )
        return ResolvedCLIClient(
            name="codex",
            executable=["codex"],
            internal_args=["exec"],
            config_args=[],
            env={},
            timeout_seconds=30,
            parser="codex_jsonl",
            roles={"default": role},
            output_to_file=None,
            working_dir=None,
            runner="codex",
        )

    def test_build_command_without_session_id(self, mock_client_claude):
        """Test command building without session ID (no resume flag added)."""
        from clink.agents.base import BaseCLIAgent

        agent = BaseCLIAgent(mock_client_claude)
        role = mock_client_claude.roles["default"]

        command = agent._build_command(role=role, system_prompt=None, cli_session_id=None)

        assert "--resume" not in command
        assert command == ["claude", "--print", "--output-format", "stream-json", "--verbose"]

    def test_build_command_with_flag_style_resume(self, mock_client_claude):
        """Test command building with flag-style resume (Claude/Gemini/Cursor)."""
        from clink.agents.base import BaseCLIAgent

        agent = BaseCLIAgent(mock_client_claude)
        role = mock_client_claude.roles["default"]
        session_id = "abc-123-def-456"

        command = agent._build_command(role=role, system_prompt=None, cli_session_id=session_id)

        assert "--resume" in command
        assert session_id in command
        # Resume should be appended at the end
        assert command[-2:] == ["--resume", session_id]

    def test_build_command_with_subcommand_style_resume(self, mock_client_codex):
        """Test command building with subcommand-style resume (Codex)."""
        from clink.agents.base import BaseCLIAgent

        agent = BaseCLIAgent(mock_client_codex)
        role = mock_client_codex.roles["default"]
        session_id = "019c0cf5-ee41-7b41-8cfb-9669a8dedf99"

        command = agent._build_command(role=role, system_prompt=None, cli_session_id=session_id)

        # Should be: codex exec resume <id>
        assert command == ["codex", "exec", "resume", session_id]

    def test_build_command_empty_session_id_ignored(self, mock_client_claude):
        """Test that empty string session ID is treated as None."""
        from clink.agents.base import BaseCLIAgent

        agent = BaseCLIAgent(mock_client_claude)
        role = mock_client_claude.roles["default"]

        # Empty string should not add resume flag
        command = agent._build_command(role=role, system_prompt=None, cli_session_id="")

        assert "--resume" not in command


class TestCLinkRequestWithSessionId:
    """Tests for CLinkRequest model with cli_session_id field."""

    def test_request_accepts_cli_session_id(self):
        """Test CLinkRequest accepts cli_session_id field."""
        from tools.clink import CLinkRequest

        request = CLinkRequest(
            prompt="Test prompt",
            cli_name="gemini",
            cli_session_id="test-session-123",
        )

        assert request.cli_session_id == "test-session-123"

    def test_request_cli_session_id_optional(self):
        """Test cli_session_id is optional and defaults to None."""
        from tools.clink import CLinkRequest

        request = CLinkRequest(
            prompt="Test prompt",
            cli_name="gemini",
        )

        assert request.cli_session_id is None

    def test_request_accepts_both_continuation_and_session_id(self):
        """Test request can have both continuation_id and cli_session_id."""
        from tools.clink import CLinkRequest

        request = CLinkRequest(
            prompt="Test prompt",
            cli_name="gemini",
            continuation_id="pal-thread-abc",
            cli_session_id="cli-session-xyz",
        )

        assert request.continuation_id == "pal-thread-abc"
        assert request.cli_session_id == "cli-session-xyz"
