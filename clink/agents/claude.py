"""Claude-specific CLI agent hooks."""

from __future__ import annotations

from clink.models import ResolvedCLIRole
from clink.parsers.base import ParserError

from .base import AgentOutput, BaseCLIAgent


class ClaudeAgent(BaseCLIAgent):
    """Claude CLI agent with system-prompt injection support."""

    def _build_command(
        self,
        *,
        role: ResolvedCLIRole,
        system_prompt: str | None,
        cli_session_id: str | None = None,
        model: str | None = None,
    ) -> list[str]:
        command = list(self.client.executable)
        command.extend(self.client.internal_args)
        command.extend(self.client.config_args)

        # Inject model flag if specified or use default from models_config
        effective_model = model
        if effective_model is None and self.client.models_config:
            effective_model = self.client.models_config.default

        if effective_model and self.client.models_config:
            command.extend([self.client.models_config.flag, effective_model])

        if system_prompt and "--append-system-prompt" not in self.client.config_args:
            command.extend(["--append-system-prompt", system_prompt])

        command.extend(role.role_args)

        # Add resume flag if session ID provided
        if cli_session_id:
            from clink.constants import RESUME_CONFIG

            runner_name = (self.client.runner or self.client.name).lower()
            resume_config = RESUME_CONFIG.get(runner_name)

            if resume_config and resume_config.style == "flag":
                command.extend([resume_config.flag, cli_session_id])

        return command

    def _recover_from_error(
        self,
        *,
        returncode: int,
        stdout: str,
        stderr: str,
        sanitized_command: list[str],
        duration_seconds: float,
        output_file_content: str | None,
    ) -> AgentOutput | None:
        try:
            parsed = self._parser.parse(stdout, stderr)
        except ParserError:
            return None

        return AgentOutput(
            parsed=parsed,
            sanitized_command=sanitized_command,
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            duration_seconds=duration_seconds,
            parser_name=self._parser.name,
            output_file_content=output_file_content,
        )
