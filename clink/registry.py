"""Configuration registry for clink CLI integrations."""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
import time
from collections.abc import Iterable
from pathlib import Path
from typing import ClassVar

from clink.constants import (
    CONFIG_DIR,
    DEFAULT_TIMEOUT_SECONDS,
    INTERNAL_DEFAULTS,
    PROJECT_ROOT,
    USER_CONFIG_DIR,
    CLIInternalDefaults,
)
from clink.models import (
    CLIClientConfig,
    CLIRoleConfig,
    DynamicModelDiscoveryConfig,
    ResolvedCLIClient,
    ResolvedCLIRole,
)
from utils.env import get_env
from utils.file_utils import read_json_file

logger = logging.getLogger("clink.registry")

CONFIG_ENV_VAR = "CLI_CLIENTS_CONFIG_PATH"


class RegistryLoadError(RuntimeError):
    """Raised when configuration files are invalid or missing critical data."""


class ClinkRegistry:
    """Loads CLI client definitions and exposes them for schema generation/runtime use."""

    # Class-level cache for dynamically discovered models: {cli_name: (models, timestamp)}
    _model_cache: ClassVar[dict[str, tuple[list[str], float]]] = {}

    def __init__(self) -> None:
        self._clients: dict[str, ResolvedCLIClient] = {}
        self._load()

    def _load(self) -> None:
        self._clients.clear()
        for config_path in self._iter_config_files():
            try:
                data = read_json_file(str(config_path))
            except json.JSONDecodeError as exc:
                raise RegistryLoadError(f"Invalid JSON in {config_path}: {exc}") from exc

            if not data:
                logger.debug("Skipping empty configuration file: %s", config_path)
                continue

            config = CLIClientConfig.model_validate(data)
            resolved = self._resolve_config(config, source_path=config_path)
            key = resolved.name.lower()
            if key in self._clients:
                logger.info("Overriding CLI configuration for '%s' from %s", resolved.name, config_path)
            else:
                logger.debug("Loaded CLI configuration for '%s' from %s", resolved.name, config_path)
            self._clients[key] = resolved

        if not self._clients:
            raise RegistryLoadError(
                "No CLI clients configured. Ensure conf/cli_clients contains at least one definition or set "
                f"{CONFIG_ENV_VAR}."
            )

    def reload(self) -> None:
        """Reload configurations from disk."""
        self._load()

    def list_clients(self) -> list[str]:
        return sorted(client.name for client in self._clients.values())

    def list_roles(self, cli_name: str) -> list[str]:
        config = self.get_client(cli_name)
        return sorted(config.roles.keys())

    def get_client(self, cli_name: str) -> ResolvedCLIClient:
        key = cli_name.lower()
        if key not in self._clients:
            available = ", ".join(self.list_clients())
            raise KeyError(f"CLI '{cli_name}' is not configured. Available clients: {available}")
        return self._clients[key]

    def list_models(self, cli_name: str) -> list[str] | None:
        """Return available models for a CLI client.

        Returns static models if configured, otherwise attempts dynamic discovery.
        Returns None if model selection is not configured for this CLI.
        """
        client = self.get_client(cli_name)
        if client.models_config is None:
            return None

        # Static models take precedence
        if client.models_config.models:
            return client.models_config.models

        # Dynamic discovery
        if client.models_config.dynamic_discovery:
            return self._discover_models(cli_name, client.models_config.dynamic_discovery)

        return None

    def _discover_models(
        self,
        cli_name: str,
        config: DynamicModelDiscoveryConfig,
    ) -> list[str] | None:
        """Execute discovery command and parse results with caching."""
        cache_key = cli_name.lower()
        now = time.time()

        # Check cache
        if cache_key in self._model_cache:
            models, timestamp = self._model_cache[cache_key]
            if now - timestamp < config.cache_ttl_seconds:
                logger.debug("Using cached models for CLI '%s' (age: %.0fs)", cli_name, now - timestamp)
                return models

        # Execute discovery command
        try:
            logger.debug("Discovering models for CLI '%s' via: %s", cli_name, config.command)
            result = subprocess.run(
                shlex.split(config.command),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                logger.warning(
                    "Model discovery failed for CLI '%s' (exit %d): %s",
                    cli_name,
                    result.returncode,
                    result.stderr.strip(),
                )
                return None

            models = self._parse_model_output(result.stdout, config.parser)
            self._model_cache[cache_key] = (models, now)
            logger.debug("Discovered %d models for CLI '%s': %s", len(models), cli_name, models)
            return models
        except subprocess.TimeoutExpired:
            logger.warning("Model discovery timed out for CLI '%s'", cli_name)
            return None
        except Exception as exc:
            logger.warning("Model discovery error for CLI '%s': %s", cli_name, exc)
            return None

    def _parse_model_output(self, output: str, parser: str) -> list[str]:
        """Parse model list output based on parser type."""
        import re

        if parser == "line_per_model":
            return [line.strip() for line in output.splitlines() if line.strip()]
        elif parser == "json_array":
            import json as json_module

            return json_module.loads(output)
        elif parser == "cursor_models":
            # Parse cursor agent --list-models output format:
            # "model-id - Model Description"
            # Skip lines with ANSI codes, headers, and tips
            models = []
            # Remove ANSI escape codes first
            ansi_escape = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
            clean_output = ansi_escape.sub("", output)

            for line in clean_output.splitlines():
                line = line.strip()
                # Skip empty lines, headers, and tips
                if not line or line.startswith("Tip:") or line.startswith("Available") or line.startswith("Loading"):
                    continue
                # Extract model ID from "model-id - Description" format
                if " - " in line:
                    model_id = line.split(" - ", 1)[0].strip()
                    if model_id and not model_id.startswith("["):
                        models.append(model_id)
            return models
        else:
            raise ValueError(f"Unknown model parser: {parser}")

    def clear_model_cache(self, cli_name: str | None = None) -> None:
        """Clear cached model discovery results.

        Args:
            cli_name: Clear cache for a specific CLI, or all if None.
        """
        if cli_name is None:
            self._model_cache.clear()
            logger.debug("Cleared all model discovery caches")
        else:
            key = cli_name.lower()
            if key in self._model_cache:
                del self._model_cache[key]
                logger.debug("Cleared model discovery cache for CLI '%s'", cli_name)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _iter_config_files(self) -> Iterable[Path]:
        search_paths: list[Path] = []

        # 1. Built-in configs
        search_paths.append(CONFIG_DIR)

        # 2. CLI_CLIENTS_CONFIG_PATH environment override (file or directory)
        env_path_raw = get_env(CONFIG_ENV_VAR)
        if env_path_raw:
            env_path = Path(env_path_raw).expanduser()
            search_paths.append(env_path)

        # 3. User overrides in ~/.pal/cli_clients
        search_paths.append(USER_CONFIG_DIR)

        seen: set[Path] = set()

        for base in search_paths:
            if not base:
                continue
            if base in seen:
                continue
            seen.add(base)

            if base.is_file() and base.suffix.lower() == ".json":
                yield base
                continue

            if base.is_dir():
                for path in sorted(base.glob("*.json")):
                    if path.is_file():
                        yield path
            else:
                logger.debug("Configuration path does not exist: %s", base)

    def _resolve_config(self, raw: CLIClientConfig, *, source_path: Path) -> ResolvedCLIClient:
        if not raw.name:
            raise RegistryLoadError(f"CLI configuration at {source_path} is missing a 'name' field")

        normalized_name = raw.name.strip()
        internal_defaults = INTERNAL_DEFAULTS.get(normalized_name.lower())
        if internal_defaults is None:
            raise RegistryLoadError(f"CLI '{raw.name}' is not supported by clink")

        executable = self._resolve_executable(raw, internal_defaults, source_path)

        internal_args = list(internal_defaults.additional_args) if internal_defaults else []
        config_args = list(raw.additional_args)

        # If models_config is defined, strip any hardcoded model flags from config_args
        # This allows models_config to take control of model selection
        models_config = raw.models_config
        if models_config and models_config.flag:
            config_args = self._strip_model_args(config_args, models_config.flag)

        timeout_seconds = raw.timeout_seconds or (
            internal_defaults.timeout_seconds if internal_defaults else DEFAULT_TIMEOUT_SECONDS
        )

        parser_name = internal_defaults.parser
        if not parser_name:
            raise RegistryLoadError(
                f"CLI '{raw.name}' must define a parser either in configuration or internal defaults"
            )

        runner_name = internal_defaults.runner if internal_defaults else None

        env = self._merge_env(raw, internal_defaults)
        working_dir = self._resolve_optional_path(raw.working_dir, source_path.parent)
        roles = self._resolve_roles(raw, internal_defaults, source_path)

        output_to_file = raw.output_to_file

        return ResolvedCLIClient(
            name=normalized_name,
            executable=executable,
            internal_args=internal_args,
            config_args=config_args,
            env=env,
            timeout_seconds=int(timeout_seconds),
            parser=parser_name,
            runner=runner_name,
            roles=roles,
            output_to_file=output_to_file,
            working_dir=working_dir,
            models_config=models_config,
        )

    def _resolve_executable(
        self,
        raw: CLIClientConfig,
        internal_defaults: CLIInternalDefaults | None,
        source_path: Path,
    ) -> list[str]:
        command = raw.command
        if not command:
            raise RegistryLoadError(f"CLI '{raw.name}' must specify a 'command' in configuration")
        return shlex.split(command)

    def _merge_env(
        self,
        raw: CLIClientConfig,
        internal_defaults: CLIInternalDefaults | None,
    ) -> dict[str, str]:
        merged: dict[str, str] = {}
        if internal_defaults and internal_defaults.env:
            merged.update(internal_defaults.env)
        merged.update(raw.env)
        return merged

    def _strip_model_args(self, args: list[str], flag: str) -> list[str]:
        """Remove existing model flag and its value from args list.

        Handles both "--flag value" and "--flag=value" formats.
        """
        result = []
        skip_next = False
        for arg in args:
            if skip_next:
                skip_next = False
                continue
            if arg == flag:
                # Next arg is the value, skip it too
                skip_next = True
                continue
            if arg.startswith(f"{flag}="):
                # Combined format like --model=opus
                continue
            result.append(arg)
        return result

    def _resolve_roles(
        self,
        raw: CLIClientConfig,
        internal_defaults: CLIInternalDefaults | None,
        source_path: Path,
    ) -> dict[str, ResolvedCLIRole]:
        roles: dict[str, CLIRoleConfig] = dict(raw.roles)

        default_role_prompt = internal_defaults.default_role_prompt if internal_defaults else None
        if "default" not in roles:
            roles["default"] = CLIRoleConfig(prompt_path=default_role_prompt)
        elif roles["default"].prompt_path is None and default_role_prompt:
            roles["default"].prompt_path = default_role_prompt

        resolved: dict[str, ResolvedCLIRole] = {}
        for role_name, role_config in roles.items():
            prompt_path_str = role_config.prompt_path or default_role_prompt
            if not prompt_path_str:
                raise RegistryLoadError(f"Role '{role_name}' for CLI '{raw.name}' must define a prompt_path")
            prompt_path = self._resolve_prompt_path(prompt_path_str, source_path.parent)
            resolved[role_name] = ResolvedCLIRole(
                name=role_name,
                prompt_path=prompt_path,
                role_args=list(role_config.role_args),
                description=role_config.description,
            )
        return resolved

    def _resolve_prompt_path(self, prompt_path: str, base_dir: Path) -> Path:
        resolved = self._resolve_path(prompt_path, base_dir)
        if not resolved.exists():
            raise RegistryLoadError(f"Prompt file not found: {resolved}")
        return resolved

    def _resolve_optional_path(self, candidate: str | None, base_dir: Path) -> Path | None:
        if not candidate:
            return None
        return self._resolve_path(candidate, base_dir)

    def _resolve_path(self, candidate: str, base_dir: Path) -> Path:
        path = Path(candidate)
        if path.is_absolute():
            return path

        candidate_path = (base_dir / path).resolve()
        if candidate_path.exists():
            return candidate_path

        project_relative = (PROJECT_ROOT / path).resolve()
        return project_relative


_REGISTRY: ClinkRegistry | None = None


def get_registry() -> ClinkRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = ClinkRegistry()
    return _REGISTRY
