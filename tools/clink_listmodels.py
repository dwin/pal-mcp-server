"""
Clink List Models Tool - Display available models for configured CLI clients

This tool provides a view of available models for each CLI client configured
in clink (e.g., Claude, Gemini, Cursor, Codex). It shows both statically
configured models and dynamically discovered models.
"""

import logging
from typing import Any, Optional

from mcp.types import TextContent

from clink import get_registry
from tools.models import ToolModelCategory, ToolOutput
from tools.shared.base_models import ToolRequest
from tools.shared.base_tool import BaseTool

logger = logging.getLogger(__name__)


class ClinkListModelsRequest(ToolRequest):
    """Request model for clink_listmodels tool."""

    cli_name: str | None = None


class ClinkListModelsTool(BaseTool):
    """
    Tool for listing available models for clink CLI clients.

    This tool helps users understand:
    - Which CLI clients are configured
    - What models are available for each CLI
    - Default models for each CLI
    - Whether models are statically configured or dynamically discovered
    """

    def get_name(self) -> str:
        return "clink_listmodels"

    def get_description(self) -> str:
        return "Lists available models for configured clink CLI clients (Claude, Gemini, Cursor, Codex, etc.)."

    def get_input_schema(self) -> dict[str, Any]:
        """Return the JSON schema for the tool's input"""
        registry = get_registry()
        cli_names = registry.list_clients()

        return {
            "type": "object",
            "properties": {
                "cli_name": {
                    "type": "string",
                    "enum": cli_names if cli_names else None,
                    "description": "Optional: List models for a specific CLI only. If omitted, shows all CLIs.",
                },
            },
            "required": [],
            "additionalProperties": False,
        }

    def get_annotations(self) -> Optional[dict[str, Any]]:
        """Return tool annotations indicating this is a read-only tool"""
        return {"readOnlyHint": True}

    def get_system_prompt(self) -> str:
        """No AI model needed for this tool"""
        return ""

    def get_request_model(self):
        """Return the Pydantic model for request validation."""
        return ClinkListModelsRequest

    def requires_model(self) -> bool:
        return False

    async def prepare_prompt(self, request: ClinkListModelsRequest) -> str:
        """Not used for this utility tool"""
        return ""

    def format_response(self, response: str, request: ClinkListModelsRequest, model_info: Optional[dict] = None) -> str:
        """Not used for this utility tool"""
        return response

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        """
        List available models for clink CLI clients.

        Args:
            arguments: Tool arguments (optional cli_name)

        Returns:
            Formatted list of models by CLI client
        """
        request = self.get_request_model()(**arguments)
        registry = get_registry()
        cli_names = registry.list_clients()

        output_lines = ["# Clink CLI Models\n"]

        # Filter to specific CLI if requested
        if request.cli_name:
            if request.cli_name not in [name.lower() for name in cli_names]:
                available = ", ".join(cli_names)
                return [
                    TextContent(
                        type="text",
                        text=ToolOutput(
                            status="error",
                            content=f"CLI '{request.cli_name}' is not configured. Available CLIs: {available}",
                            content_type="text",
                        ).model_dump_json(),
                    )
                ]
            cli_names = [name for name in cli_names if name.lower() == request.cli_name.lower()]

        total_models = 0

        for cli_name in cli_names:
            try:
                client = registry.get_client(cli_name)
            except KeyError:
                continue

            output_lines.append(f"## {cli_name}")

            if not client.supports_model_selection():
                output_lines.append("**Model selection**: Not configured")
                output_lines.append("*This CLI does not have models_config defined.*\n")
                continue

            models_config = client.models_config
            if models_config is None:
                output_lines.append("**Model selection**: Not configured\n")
                continue

            # Show model flag
            output_lines.append(f"**Model flag**: `{models_config.flag}`")

            # Show default model
            default_model = models_config.default
            if default_model:
                output_lines.append(f"**Default model**: `{default_model}`")
            else:
                output_lines.append("**Default model**: None (must specify)")

            # Get available models
            models = registry.list_models(cli_name)

            if models_config.dynamic_discovery:
                discovery = models_config.dynamic_discovery
                output_lines.append(f"**Discovery**: Dynamic via `{discovery.command}`")
                output_lines.append(f"**Cache TTL**: {discovery.cache_ttl_seconds}s")
            elif models_config.models:
                output_lines.append("**Discovery**: Static (configured in JSON)")

            if models:
                output_lines.append(f"\n**Available models** ({len(models)}):")
                for model in sorted(models):
                    is_default = model == default_model
                    suffix = " *(default)*" if is_default else ""
                    output_lines.append(f"- `{model}`{suffix}")
                total_models += len(models)
            else:
                output_lines.append("\n**Available models**: None discovered")

            output_lines.append("")

        # Summary
        output_lines.append("## Summary")
        output_lines.append(f"**CLI clients**: {len(cli_names)}")
        output_lines.append(f"**Total models**: {total_models}")

        output_lines.append("\n**Usage**:")
        output_lines.append("Use the `model` parameter in clink to specify a model:")
        output_lines.append("```")
        output_lines.append('clink(cli_name="claude", model="sonnet", prompt="...")')
        output_lines.append("```")

        content = "\n".join(output_lines)

        tool_output = ToolOutput(
            status="success",
            content=content,
            content_type="text",
            metadata={
                "tool_name": self.name,
                "cli_count": len(cli_names),
                "total_models": total_models,
            },
        )

        return [TextContent(type="text", text=tool_output.model_dump_json())]

    def get_model_category(self) -> ToolModelCategory:
        """Return the model category for this tool."""
        return ToolModelCategory.FAST_RESPONSE  # Simple listing, no AI needed
