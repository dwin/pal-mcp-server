"""Focused tests for the collapsed simple-tool hierarchy."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from tools.apilookup import LookupTool
from tools.challenge import ChallengeTool
from tools.chat import ChatTool
from tools.clink import CLinkTool
from tools.shared.base_models import ToolRequest
from tools.shared.base_tool import BaseTool
from tools.simple.base import SimpleTool


class ExampleRequest(ToolRequest):
    """Minimal request model for exercising BaseTool defaults directly."""

    prompt: str = Field(..., description="Example prompt.")
    absolute_file_paths: list[str] = Field(default_factory=list, description="Absolute file paths.")


class ExampleBaseTool(BaseTool):
    """Direct BaseTool subclass that relies on the simple-tool default behavior."""

    def get_name(self) -> str:
        return "example"

    def get_description(self) -> str:
        return "Example simple tool."

    def get_system_prompt(self) -> str:
        return "System prompt"

    def get_request_model(self):
        return ExampleRequest

    def get_tool_fields(self) -> dict[str, dict[str, Any]]:
        return {
            "prompt": {"type": "string", "description": "Example prompt."},
            "absolute_file_paths": BaseTool.FILES_FIELD,
        }

    def get_required_fields(self) -> list[str]:
        return ["prompt"]

    async def prepare_prompt(self, request: ExampleRequest) -> str:
        return self.prepare_chat_style_prompt(request)


class ExampleLegacySimpleTool(SimpleTool):
    """Compatibility-shim subclass that still uses the shared BaseTool behavior."""

    def get_name(self) -> str:
        return "legacy-example"

    def get_description(self) -> str:
        return "Legacy example simple tool."

    def get_system_prompt(self) -> str:
        return ""

    def get_request_model(self):
        return ExampleRequest

    def get_tool_fields(self) -> dict[str, dict[str, Any]]:
        return {"prompt": {"type": "string", "description": "Example prompt."}}

    def get_required_fields(self) -> list[str]:
        return ["prompt"]

    async def prepare_prompt(self, request: ExampleRequest) -> str:
        return request.prompt


def test_concrete_simple_tools_inherit_base_tool_directly() -> None:
    """Concrete request/response tools should no longer keep SimpleTool in their MRO."""

    assert ChatTool.__bases__ == (BaseTool,)
    assert ChallengeTool.__bases__ == (BaseTool,)
    assert LookupTool.__bases__ == (BaseTool,)
    assert CLinkTool.__bases__ == (BaseTool,)


def test_base_tool_provides_simple_schema_defaults() -> None:
    """BaseTool now exposes the default simple-tool schema hooks directly."""

    tool = ExampleBaseTool()

    assert tool.supports_custom_request_model() is True
    assert BaseTool.FILES_FIELD["description"] == SimpleTool.FILES_FIELD["description"]

    schema = tool.get_input_schema()
    assert "prompt" in schema["required"]
    assert schema["properties"]["prompt"]["description"] == "Example prompt."
    assert schema["properties"]["absolute_file_paths"]["description"] == BaseTool.FILES_FIELD["description"]


def test_simple_tool_compatibility_shim_still_works() -> None:
    """Legacy imports should still expose the same default behavior."""

    tool = ExampleLegacySimpleTool()
    schema = tool.get_input_schema()

    assert issubclass(SimpleTool, BaseTool)
    assert "prompt" in schema["required"]
    assert schema["properties"]["prompt"]["description"] == "Example prompt."
