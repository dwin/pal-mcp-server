"""Pydantic models for clink configuration and runtime structures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, PositiveInt, field_validator


class DynamicModelDiscoveryConfig(BaseModel):
    """Configuration for dynamic model discovery via CLI command."""

    command: str = Field(..., description="Command to list available models (e.g., 'agent --list-models')")
    parser: str = Field(
        default="line_per_model",
        description="Parser for command output: 'line_per_model' or 'json_array'",
    )
    cache_ttl_seconds: int = Field(default=3600, description="How long to cache discovered models")


class ModelConfig(BaseModel):
    """Model selection configuration for a CLI client."""

    flag: str = Field(..., description="CLI flag for model selection (e.g., '--model', '-m')")
    default: str | None = Field(default=None, description="Default model if not specified in request")
    models: list[str] | None = Field(default=None, description="Static list of available models")
    dynamic_discovery: DynamicModelDiscoveryConfig | None = Field(
        default=None,
        description="Configuration for dynamic model discovery via CLI command",
    )

    @field_validator("models", mode="before")
    @classmethod
    def _ensure_models_list(cls, value: Any) -> list[str] | None:
        if value is None:
            return None
        if isinstance(value, list):
            return [str(item) for item in value]
        raise TypeError("models must be a list of strings")


class OutputCaptureConfig(BaseModel):
    """Optional configuration for CLIs that write output to disk."""

    flag_template: str = Field(..., description="Template used to inject the output path, e.g. '--output {path}'.")
    cleanup: bool = Field(
        default=True,
        description="Whether the temporary file should be removed after reading.",
    )


class CLIRoleConfig(BaseModel):
    """Role-specific configuration loaded from JSON manifests."""

    prompt_path: str | None = Field(
        default=None,
        description="Path to the prompt file that seeds this role.",
    )
    role_args: list[str] = Field(default_factory=list)
    description: str | None = Field(default=None)

    @field_validator("role_args", mode="before")
    @classmethod
    def _ensure_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            return [value]
        raise TypeError("role_args must be a list of strings or a single string")


class CLIClientConfig(BaseModel):
    """Raw CLI client configuration before internal defaults are applied."""

    name: str
    command: str | None = None
    working_dir: str | None = None
    additional_args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: PositiveInt | None = Field(default=None)
    roles: dict[str, CLIRoleConfig] = Field(default_factory=dict)
    output_to_file: OutputCaptureConfig | None = None
    # Note: Using alias "model_config" for JSON compatibility while avoiding pydantic reserved name
    models_config: ModelConfig | None = Field(
        default=None,
        alias="model_config",
        description="Model selection configuration for this CLI",
    )

    @field_validator("additional_args", mode="before")
    @classmethod
    def _ensure_args_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, str):
            return [value]
        raise TypeError("additional_args must be a list of strings or a single string")


class ResolvedCLIRole(BaseModel):
    """Runtime representation of a CLI role with resolved prompt path."""

    name: str
    prompt_path: Path
    role_args: list[str] = Field(default_factory=list)
    description: str | None = None


class ResolvedCLIClient(BaseModel):
    """Runtime configuration after merging defaults and validating paths."""

    name: str
    executable: list[str]
    working_dir: Path | None
    internal_args: list[str] = Field(default_factory=list)
    config_args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int
    parser: str
    runner: str | None = None
    roles: dict[str, ResolvedCLIRole]
    output_to_file: OutputCaptureConfig | None = None
    models_config: ModelConfig | None = Field(
        default=None,
        description="Model selection configuration for this CLI",
    )

    def list_roles(self) -> list[str]:
        return list(self.roles.keys())

    def get_role(self, role_name: str | None) -> ResolvedCLIRole:
        key = role_name or "default"
        if key not in self.roles:
            available = ", ".join(sorted(self.roles.keys()))
            raise KeyError(f"Role '{role_name}' not configured for CLI '{self.name}'. Available roles: {available}")
        return self.roles[key]

    def get_static_models(self) -> list[str] | None:
        """Return statically configured models, or None if not configured."""
        if self.models_config is None:
            return None
        return self.models_config.models

    def get_default_model(self) -> str | None:
        """Return default model, or None if not configured."""
        if self.models_config is None:
            return None
        return self.models_config.default

    def get_model_flag(self) -> str | None:
        """Return the CLI flag for model selection, or None if not configured."""
        if self.models_config is None:
            return None
        return self.models_config.flag

    def supports_model_selection(self) -> bool:
        """Return True if this CLI supports model selection."""
        return self.models_config is not None
