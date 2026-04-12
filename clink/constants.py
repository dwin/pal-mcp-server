"""Internal defaults and constants for clink."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

DEFAULT_TIMEOUT_SECONDS = 1800
DEFAULT_STREAM_LIMIT = 10 * 1024 * 1024  # 10MB per stream

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BUILTIN_PROMPTS_DIR = PROJECT_ROOT / "systemprompts" / "clink"
CONFIG_DIR = PROJECT_ROOT / "conf" / "cli_clients"
USER_CONFIG_DIR = Path.home() / ".pal" / "cli_clients"


@dataclass(frozen=True)
class CLIInternalDefaults:
    """Internal defaults applied to a CLI client during registry load."""

    parser: str
    additional_args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    default_role_prompt: str | None = None
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    runner: str | None = None


INTERNAL_DEFAULTS: dict[str, CLIInternalDefaults] = {
    "gemini": CLIInternalDefaults(
        parser="gemini_stream_json",
        additional_args=["--output-format", "stream-json"],
        default_role_prompt="systemprompts/clink/default.txt",
        runner="gemini",
    ),
    "codex": CLIInternalDefaults(
        parser="codex_jsonl",
        additional_args=["exec"],
        default_role_prompt="systemprompts/clink/default.txt",
        runner="codex",
    ),
    "claude": CLIInternalDefaults(
        parser="claude_stream_json",
        additional_args=["--print", "--output-format", "stream-json", "--verbose"],
        default_role_prompt="systemprompts/clink/default.txt",
        runner="claude",
    ),
    "cursor": CLIInternalDefaults(
        parser="cursor_stream_json",
        additional_args=["--print", "--output-format", "stream-json"],
        default_role_prompt="systemprompts/clink/default.txt",
        runner="cursor",
    ),
}


@dataclass(frozen=True)
class CLIResumeConfig:
    """Configuration for CLI session resumption.

    Attributes:
        flag: The resume flag or subcommand (e.g., "--resume" or "resume").
        style: How to apply the resume - "flag" appends --resume <id>,
               "subcommand" inserts resume <id> at a specific position.
        insert_position: For subcommand style, where to insert (e.g., "after:exec").
    """

    flag: str
    style: Literal["flag", "subcommand"]
    insert_position: str = "append"


RESUME_CONFIG: dict[str, CLIResumeConfig] = {
    "claude": CLIResumeConfig(flag="--resume", style="flag"),
    "gemini": CLIResumeConfig(flag="--resume", style="flag"),
    "cursor": CLIResumeConfig(flag="--resume", style="flag"),
    "codex": CLIResumeConfig(flag="resume", style="subcommand", insert_position="after:exec"),
}
