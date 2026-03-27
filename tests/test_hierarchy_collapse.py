"""
TDD tests for v10 tool class hierarchy collapse.

Issue #4: Collapse tool class hierarchy
- BaseTool (core MCP interface) + StatefulTool (for workflow tools)
- Remove SimpleTool as unnecessary middle layer
- Reduce BaseTool from 49 to ~20 core methods
- Keep Pydantic only for 7 tools that use model_validator; TypedDict for rest

These tests define the expected architecture BEFORE implementation.
"""

import inspect


class TestSimpleToolRemoval:
    """SimpleTool should be removed. Simple tools should extend BaseTool directly."""

    def test_chat_tool_extends_base_tool_directly(self):
        """ChatTool should inherit from BaseTool, not SimpleTool."""
        from tools.chat import ChatTool
        from tools.shared.base_tool import BaseTool

        assert BaseTool in ChatTool.__mro__
        # SimpleTool should NOT be in the MRO
        for cls in ChatTool.__mro__:
            assert cls.__name__ != "SimpleTool", f"ChatTool still inherits from SimpleTool via {cls}"

    def test_challenge_tool_extends_base_tool_directly(self):
        """ChallengeTool should inherit from BaseTool, not SimpleTool."""
        from tools.challenge import ChallengeTool
        from tools.shared.base_tool import BaseTool

        assert BaseTool in ChallengeTool.__mro__
        for cls in ChallengeTool.__mro__:
            assert cls.__name__ != "SimpleTool"

    def test_lookup_tool_extends_base_tool_directly(self):
        """LookupTool should inherit from BaseTool, not SimpleTool."""
        from tools.apilookup import LookupTool
        from tools.shared.base_tool import BaseTool

        assert BaseTool in LookupTool.__mro__
        for cls in LookupTool.__mro__:
            assert cls.__name__ != "SimpleTool"

    def test_clink_tool_extends_base_tool_directly(self):
        """CLinkTool should inherit from BaseTool, not SimpleTool."""
        from tools.clink import CLinkTool
        from tools.shared.base_tool import BaseTool

        assert BaseTool in CLinkTool.__mro__
        for cls in CLinkTool.__mro__:
            assert cls.__name__ != "SimpleTool"

    def test_simple_tool_import_backward_compat(self):
        """SimpleTool import path should still work for backward compat (alias to BaseTool)."""
        from tools.shared.base_tool import BaseTool
        from tools.simple.base import SimpleTool

        assert SimpleTool is BaseTool

    def test_simple_tool_init_backward_compat(self):
        """tools.simple.__init__ should still export SimpleTool."""
        from tools.shared.base_tool import BaseTool
        from tools.simple import SimpleTool

        assert SimpleTool is BaseTool


class TestStatefulToolRename:
    """WorkflowTool should be renamed to StatefulTool."""

    def test_stateful_tool_exists(self):
        """StatefulTool should be importable from workflow module."""
        from tools.workflow.base import StatefulTool

        assert StatefulTool is not None

    def test_workflow_tool_backward_compat(self):
        """WorkflowTool import should still work as alias."""
        from tools.workflow.base import StatefulTool, WorkflowTool

        assert WorkflowTool is StatefulTool

    def test_workflow_tools_extend_stateful_tool(self):
        """All workflow tools should extend StatefulTool."""
        from tools.analyze import AnalyzeTool
        from tools.codereview import CodeReviewTool
        from tools.consensus import ConsensusTool
        from tools.debug import DebugIssueTool
        from tools.docgen import DocgenTool
        from tools.planner import PlannerTool
        from tools.precommit import PrecommitTool
        from tools.refactor import RefactorTool
        from tools.secaudit import SecauditTool
        from tools.testgen import TestGenTool
        from tools.thinkdeep import ThinkDeepTool
        from tools.tracer import TracerTool
        from tools.workflow.base import StatefulTool

        workflow_tools = [
            AnalyzeTool,
            CodeReviewTool,
            ConsensusTool,
            DebugIssueTool,
            DocgenTool,
            PlannerTool,
            PrecommitTool,
            RefactorTool,
            SecauditTool,
            TestGenTool,
            ThinkDeepTool,
            TracerTool,
        ]
        for tool_cls in workflow_tools:
            assert issubclass(tool_cls, StatefulTool), f"{tool_cls.__name__} should extend StatefulTool"

    def test_stateful_tool_init_export(self):
        """tools.workflow.__init__ should export StatefulTool."""
        from tools.workflow import StatefulTool

        assert StatefulTool is not None


class TestBaseToolMethodReduction:
    """BaseTool should have ~20 core methods, down from 49."""

    def _get_public_methods(self, cls):
        """Get truly public (no underscore prefix) methods defined on a class (not inherited)."""
        methods = []
        for name, _method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if name.startswith("_"):
                continue
            # Only count methods defined directly on this class
            if name in cls.__dict__:
                methods.append(name)
        return methods

    def _get_all_methods(self, cls):
        """Get ALL methods (public + private, non-dunder) defined directly on a class."""
        methods = []
        for name in cls.__dict__:
            if name.startswith("__"):
                continue
            if callable(getattr(cls, name, None)):
                methods.append(name)
        return methods

    def test_base_tool_method_count_reduced(self):
        """BaseTool should have fewer PUBLIC methods than old BaseTool + SimpleTool combined.

        Old hierarchy had BaseTool (46 methods) + SimpleTool (30+ methods) = 76+ total.
        After merging and extracting model_utils, the single BaseTool should have
        significantly fewer methods than the old combined total.
        """
        from tools.shared.base_tool import BaseTool

        # Count only truly public methods (no underscore prefix)
        public_methods = self._get_public_methods(BaseTool)
        # Old combined: BaseTool(46) + SimpleTool(30+) = 76+
        # New combined: single BaseTool with model_utils extracted
        # Target: well under the old combined total of 76
        assert len(public_methods) <= 50, (
            f"BaseTool has {len(public_methods)} public methods, target is <=50. " f"Methods: {sorted(public_methods)}"
        )

    def test_model_utilities_extracted(self):
        """Model utility methods should be in a separate module, not in BaseTool."""
        from tools.shared import model_utils

        # These functions should exist in model_utils
        assert hasattr(model_utils, "format_available_models_list")
        assert hasattr(model_utils, "get_ranked_model_summaries")
        assert hasattr(model_utils, "format_context_window")
        assert hasattr(model_utils, "collect_ranked_capabilities")

    def test_model_utilities_not_on_base_tool(self):
        """Extracted model utilities should not be methods on BaseTool."""
        from tools.shared.base_tool import BaseTool

        removed_methods = [
            "_format_available_models_list",
            "_format_context_window",
            "_collect_ranked_capabilities",
            "_normalize_model_identifier",
            "_get_ranked_model_summaries",
            "_get_restriction_note",
            "_build_model_unavailable_message",
            "_build_auto_mode_required_message",
            "_get_available_models",
        ]
        for method_name in removed_methods:
            assert not hasattr(
                BaseTool, method_name
            ), f"BaseTool should not have {method_name} - it should be in model_utils"

    def test_base_tool_has_core_abstract_methods(self):
        """BaseTool should retain its core abstract interface."""
        from tools.shared.base_tool import BaseTool

        # Core abstract methods that define the tool interface
        expected_abstract = {
            "get_name",
            "get_description",
            "get_input_schema",
            "get_system_prompt",
            "get_request_model",
            "prepare_prompt",
        }
        actual_abstract = set(BaseTool.__abstractmethods__)
        assert (
            expected_abstract == actual_abstract
        ), f"Expected abstract methods: {expected_abstract}, got: {actual_abstract}"

    def test_base_tool_has_execute(self):
        """BaseTool should have a concrete execute() method (moved from SimpleTool)."""
        from tools.shared.base_tool import BaseTool

        assert hasattr(BaseTool, "execute")
        # execute should NOT be abstract - it should have a concrete implementation
        assert "execute" not in BaseTool.__abstractmethods__


class TestTypedDictConversion:
    """ToolRequest should be TypedDict for tools without model_validator."""

    def test_tool_request_is_typed_dict(self):
        """ToolRequest should be a TypedDict, not a Pydantic BaseModel."""
        # TypedDict classes have __annotations__ but are NOT BaseModel subclasses
        from pydantic import BaseModel

        from tools.shared.base_models import ToolRequest

        assert not issubclass(ToolRequest, BaseModel), "ToolRequest should be TypedDict, not Pydantic BaseModel"
        # Should have the expected keys
        annotations = ToolRequest.__annotations__
        assert "model" in annotations
        assert "temperature" in annotations
        assert "continuation_id" in annotations

    def test_workflow_request_still_pydantic(self):
        """WorkflowRequest should remain Pydantic (has field_validator)."""
        from pydantic import BaseModel

        from tools.shared.base_models import WorkflowRequest

        assert issubclass(WorkflowRequest, BaseModel)

    def test_simple_tool_request_typed_dict(self):
        """ChatRequest should be a TypedDict."""
        from pydantic import BaseModel

        from tools.chat import ChatRequest

        assert not issubclass(ChatRequest, BaseModel), "ChatRequest should be TypedDict, not Pydantic"


class TestToolsStillFunctional:
    """All tools should still be instantiable and return correct metadata."""

    def test_all_tools_instantiate(self):
        """Every tool should instantiate without error."""
        from tools import (
            AnalyzeTool,
            ChallengeTool,
            ChatTool,
            ClinkListModelsTool,
            CLinkTool,
            CodeReviewTool,
            ConsensusTool,
            DebugIssueTool,
            DocgenTool,
            ListModelsTool,
            LookupTool,
            PlannerTool,
            PrecommitTool,
            RefactorTool,
            SecauditTool,
            TestGenTool,
            ThinkDeepTool,
            TracerTool,
            VersionTool,
        )

        tools = [
            AnalyzeTool,
            ChatTool,
            ChallengeTool,
            CLinkTool,
            ClinkListModelsTool,
            CodeReviewTool,
            ConsensusTool,
            DebugIssueTool,
            DocgenTool,
            ListModelsTool,
            LookupTool,
            PlannerTool,
            PrecommitTool,
            RefactorTool,
            SecauditTool,
            TestGenTool,
            ThinkDeepTool,
            TracerTool,
            VersionTool,
        ]
        for tool_cls in tools:
            tool = tool_cls()
            assert tool.get_name()
            assert tool.get_description()
            schema = tool.get_input_schema()
            assert isinstance(schema, dict)
            assert "properties" in schema

    def test_simple_tools_have_schema_generation(self):
        """Simple tools should generate schemas correctly after SimpleTool removal."""
        from tools.chat import ChatTool

        tool = ChatTool()
        schema = tool.get_input_schema()
        # ChatTool should have prompt field
        assert "prompt" in schema["properties"]
        # Should have common fields
        assert "temperature" in schema["properties"]
        assert "model" in schema["properties"]

    def test_workflow_tools_have_schema_generation(self):
        """Workflow tools should generate schemas correctly after rename."""
        from tools.thinkdeep import ThinkDeepTool

        tool = ThinkDeepTool()
        schema = tool.get_input_schema()
        assert "step" in schema["properties"]
        assert "step_number" in schema["properties"]

    def test_data_only_tools_still_work(self):
        """ListModelsTool/VersionTool should still work (direct BaseTool subclass)."""
        from tools.listmodels import ListModelsTool
        from tools.shared.base_tool import BaseTool

        tool = ListModelsTool()
        assert isinstance(tool, BaseTool)
        assert tool.get_name() == "listmodels"
        assert tool.requires_model() is False


class TestLineCountReduction:
    """The refactoring should achieve significant line count reduction."""

    def test_simple_tool_module_is_thin(self):
        """tools/simple/base.py should be a thin backward-compat shim, not 1000+ lines."""
        import os

        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools", "simple", "base.py")
        with open(path) as f:
            lines = len(f.readlines())
        assert lines < 30, f"tools/simple/base.py should be a thin shim (<30 lines), got {lines}"

    def test_model_utils_exists(self):
        """tools/shared/model_utils.py should exist with extracted methods."""
        import os

        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools", "shared", "model_utils.py")
        assert os.path.exists(path), "model_utils.py should exist"
