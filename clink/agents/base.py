"""Execute configured CLI agents for the clink tool and parse output."""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import shutil
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from clink.constants import DEFAULT_STREAM_LIMIT
from clink.models import ResolvedCLIClient, ResolvedCLIRole
from clink.parsers import BaseParser, ParsedCLIResponse, ParserError, get_parser

logger = logging.getLogger("clink.agent")


@dataclass
class AgentOutput:
    """Container returned by CLI agents after successful execution."""

    parsed: ParsedCLIResponse
    sanitized_command: list[str]
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    parser_name: str
    output_file_content: str | None = None


class CLIAgentError(RuntimeError):
    """Raised when a CLI agent fails (non-zero exit, timeout, parse errors)."""

    def __init__(self, message: str, *, returncode: int | None = None, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class BaseCLIAgent:
    """Execute a configured CLI command and parse its output."""

    def __init__(self, client: ResolvedCLIClient):
        self.client = client
        self._parser: BaseParser = get_parser(client.parser)
        self._logger = logging.getLogger(f"clink.runner.{client.name}")

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
        # Files and images are already embedded into the prompt by the tool; they are
        # accepted here only to keep parity with SimpleTool callers.
        _ = (files, images)
        # The runner simply executes the configured CLI command for the selected role.
        command = self._build_command(
            role=role, system_prompt=system_prompt, cli_session_id=cli_session_id, model=model
        )
        env = self._build_environment()

        # Resolve executable path for cross-platform compatibility (especially Windows)
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
        limit = DEFAULT_STREAM_LIMIT

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
            command_with_output_flag.extend(shlex.split(rendered_flag))
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
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(prompt.encode("utf-8")),
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
        system_prompt: str | None,
        cli_session_id: str | None = None,
        model: str | None = None,
    ) -> list[str]:
        base = list(self.client.executable)
        base.extend(self.client.internal_args)
        base.extend(self.client.config_args)

        # Inject model flag if specified or use default from models_config
        effective_model = model
        if effective_model is None and self.client.models_config:
            effective_model = self.client.models_config.default

        if effective_model and self.client.models_config:
            base.extend([self.client.models_config.flag, effective_model])

        base.extend(role.role_args)

        # Add resume flag if session ID provided
        if cli_session_id:
            from clink.constants import RESUME_CONFIG

            runner_name = (self.client.runner or self.client.name).lower()
            resume_config = RESUME_CONFIG.get(runner_name)

            if resume_config:
                if resume_config.style == "flag":
                    # Standard flag style: --resume <id>
                    base.extend([resume_config.flag, cli_session_id])
                elif resume_config.style == "subcommand":
                    # Subcommand style: insert "resume <id>" after a specific arg
                    if resume_config.insert_position.startswith("after:"):
                        after_arg = resume_config.insert_position.split(":", 1)[1]
                        try:
                            idx = base.index(after_arg) + 1
                            base.insert(idx, resume_config.flag)
                            base.insert(idx + 1, cli_session_id)
                        except ValueError:
                            # Arg not found, append instead
                            self._logger.warning(
                                "Resume insert position '%s' not found in command, appending",
                                after_arg,
                            )
                            base.extend([resume_config.flag, cli_session_id])
                    else:
                        base.extend([resume_config.flag, cli_session_id])

        return base

    def _build_environment(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(self.client.env)
        return env

    # ------------------------------------------------------------------
    # Error recovery hooks
    # ------------------------------------------------------------------

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
        """Hook for subclasses to convert CLI errors into successful outputs.

        Return an AgentOutput to treat the failure as success, or None to signal
        that normal error handling should proceed.
        """

        return None
