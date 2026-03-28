"""Cursor-specific CLI agent hooks."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path

from clink.models import ResolvedCLIRole
from clink.parsers.base import ParserError

from .base import AgentOutput, BaseCLIAgent, CLIAgentError


class CursorAgent(BaseCLIAgent):
    """Cursor CLI agent with custom prompt delivery via CLI argument.

    Unlike other clink agents (Claude, Codex, Gemini), cursor-agent does not
    accept prompts via stdin. The prompt must be passed as a positional
    command-line argument.
    """

    async def run(
        self,
        *,
        role: ResolvedCLIRole,
        prompt: str,
        system_prompt: str | None = None,
        files: Sequence[str],
        images: Sequence[str],
        cli_session_id: str | None = None,
        model: str | None = None,
    ) -> AgentOutput:
        """Execute cursor-agent with prompt as CLI argument instead of stdin."""

        # Files and images are already embedded into the prompt by the tool; they are
        # accepted here only to keep parity with SimpleTool callers.
        _ = (files, images, system_prompt)

        # Build the command with prompt as a positional argument
        command = self._build_command(role=role, prompt=prompt, cli_session_id=cli_session_id, model=model)
        env = self._build_environment()

        # Resolve executable path for cross-platform compatibility
        executable_name = command[0]
        resolved_executable = shutil.which(executable_name)
        if resolved_executable is None:
            raise CLIAgentError(
                f"Executable '{executable_name}' not found in PATH for CLI '{self.client.name}'. "
                f"Ensure the command is installed and accessible."
            )
        command[0] = resolved_executable

        sanitized_command = list(command)

        cwd = str(self.client.working_dir) if self.client.working_dir else None
        limit = 10 * 1024 * 1024  # DEFAULT_STREAM_LIMIT

        stdout_text = ""
        stderr_text = ""
        output_file_content: str | None = None
        start_time = time.monotonic()

        output_file_path: Path | None = None
        command_with_output_flag = list(command)

        if self.client.output_to_file:
            tmp = tempfile.NamedTemporaryFile(prefix="clink-", suffix=".json", delete=False)
            tmp.close()
            output_file_path = Path(tmp.name)
            flag_template = self.client.output_to_file.flag_template
            try:
                rendered_flag = flag_template.format(path=str(output_file_path))
            except KeyError as exc:  # pragma: no cover - defensive
                output_file_path.unlink(missing_ok=True)
                raise CLIAgentError(f"Invalid output flag template '{flag_template}': missing placeholder {exc}")
            # Note: For cursor-agent, we cannot use shlex.split here since the output flag
            # comes before the prompt argument
            command_with_output_flag.append(rendered_flag)
            sanitized_command = list(command_with_output_flag)

        self._logger.debug("Executing CLI command: %s", " ".join(sanitized_command))
        if cwd:
            self._logger.debug("Working directory: %s", cwd)

        try:
            try:
                process = await asyncio.create_subprocess_exec(
                    *command_with_output_flag,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                    limit=limit,
                    env=env,
                )
            except FileNotFoundError as exc:
                raise CLIAgentError(f"Executable not found for CLI '{self.client.name}': {exc}") from exc

            try:
                # cursor-agent does not accept stdin, so communicate without input
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.client.timeout_seconds,
                )
            except asyncio.TimeoutError as exc:
                process.kill()
                await process.communicate()
                raise CLIAgentError(
                    f"CLI '{self.client.name}' timed out after {self.client.timeout_seconds} seconds",
                    returncode=None,
                ) from exc

            duration = time.monotonic() - start_time
            return_code = process.returncode
            stdout_text = stdout_bytes.decode("utf-8", errors="replace")
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")

            if output_file_path and output_file_path.exists():
                output_file_content = output_file_path.read_text(encoding="utf-8", errors="replace")

                if output_file_content and not stdout_text.strip():
                    stdout_text = output_file_content

            if return_code != 0:
                recovered = self._recover_from_error(
                    returncode=return_code,
                    stdout=stdout_text,
                    stderr=stderr_text,
                    sanitized_command=sanitized_command,
                    duration_seconds=duration,
                    output_file_content=output_file_content,
                )
                if recovered is not None:
                    return recovered

            if return_code != 0:
                raise CLIAgentError(
                    f"CLI '{self.client.name}' exited with status {return_code}",
                    returncode=return_code,
                    stdout=stdout_text,
                    stderr=stderr_text,
                )

            try:
                parsed = self._parser.parse(stdout_text, stderr_text)
            except ParserError as exc:
                raise CLIAgentError(
                    f"Failed to parse output from CLI '{self.client.name}': {exc}",
                    returncode=return_code,
                    stdout=stdout_text,
                    stderr=stderr_text,
                ) from exc

            return AgentOutput(
                parsed=parsed,
                sanitized_command=sanitized_command,
                returncode=return_code,
                stdout=stdout_text,
                stderr=stderr_text,
                duration_seconds=duration,
                parser_name=self._parser.name,
                output_file_content=output_file_content,
            )
        finally:
            if output_file_path is not None and self.client.output_to_file and self.client.output_to_file.cleanup:
                output_file_path.unlink(missing_ok=True)

    def _build_command(
        self,
        *,
        role: ResolvedCLIRole,
        prompt: str,
        cli_session_id: str | None = None,
        model: str | None = None,
    ) -> list[str]:
        """Build cursor-agent command with prompt as positional argument."""

        command = list(self.client.executable)
        command.extend(self.client.internal_args)
        command.extend(self.client.config_args)

        # Inject model flag if specified or use default from models_config
        effective_model = model
        if effective_model is None and self.client.models_config:
            effective_model = self.client.models_config.default

        if effective_model and self.client.models_config:
            command.extend([self.client.models_config.flag, effective_model])

        command.extend(role.role_args)

        # Add resume flag if session ID provided (before the prompt)
        if cli_session_id:
            from clink.constants import RESUME_CONFIG

            runner_name = (self.client.runner or self.client.name).lower()
            resume_config = RESUME_CONFIG.get(runner_name)

            if resume_config and resume_config.style == "flag":
                command.extend([resume_config.flag, cli_session_id])

        # cursor-agent takes the prompt as a positional argument (must be last)
        command.append(prompt)

        return command

    def _build_environment(self) -> dict[str, str]:
        """Build environment variables for the process."""

        env = os.environ.copy()
        env.update(self.client.env)
        return env

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
        """Attempt to recover from errors by parsing valid JSON responses.

        cursor-agent may return valid JSON even on non-zero exit codes,
        similar to Claude agent behavior.
        """

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
