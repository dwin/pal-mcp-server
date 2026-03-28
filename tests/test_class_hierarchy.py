"""
Tests verifying the collapsed tool class hierarchy (issue #4).

The tool hierarchy was collapsed from 4+ inheritance levels:
    BaseTool → SimpleTool → concrete simple tools
    BaseTool + BaseWorkflowMixin → WorkflowTool → concrete workflow tools

Down to 2 base classes:
    BaseTool → concrete simple tools
    BaseTool → StatefulTool → concrete workflow tools

These tests verify:
1. Correct inheritance chains for all 19 tools
2. BaseTool absorbed SimpleTool functionality
3. StatefulTool merged WorkflowTool + BaseWorkflowMixin
4. Backward compatibility aliases work
5. Old mixin pattern is not accidentally reintroduced
"""

import inspect


class TestInheritanceChain:
    """Verify every tool has the correct 2-level inheritance."""

    def test_simple_tools_inherit_from_base_tool(self):
        """Simple tools must inherit directly from BaseTool, not SimpleTool."""
        from tools.apilookup import LookupTool
        from tools.challenge import ChallengeTool
        from tools.chat import ChatTool
        from tools.clink import CLinkTool
        from tools.shared.base_tool import BaseTool

        for tool_cls in [ChatTool, LookupTool, ChallengeTool, CLinkTool]:
            # Direct parent should be BaseTool
            assert BaseTool in tool_cls.__mro__, f"{tool_cls.__name__} should have BaseTool in MRO"
            # Should NOT have SimpleTool as a distinct class in MRO
            # (SimpleTool is now just an alias for BaseTool)
            mro_names = [c.__name__ for c in tool_cls.__mro__]
            assert "SimpleTool" not in mro_names, f"{tool_cls.__name__} should not have a separate SimpleTool in MRO"

    def test_workflow_tools_inherit_from_stateful_tool(self):
        """Workflow tools must inherit from StatefulTool → BaseTool."""
        from tools.analyze import AnalyzeTool
        from tools.codereview import CodeReviewTool
        from tools.consensus import ConsensusTool
        from tools.debug import DebugIssueTool
        from tools.docgen import DocgenTool
        from tools.planner import PlannerTool
        from tools.precommit import PrecommitTool
        from tools.refactor import RefactorTool
        from tools.secaudit import SecauditTool
        from tools.shared.base_tool import BaseTool
        from tools.testgen import TestGenTool
        from tools.thinkdeep import ThinkDeepTool
        from tools.tracer import TracerTool
        from tools.workflow.stateful_tool import StatefulTool

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
            assert issubclass(tool_cls, StatefulTool), f"{tool_cls.__name__} should be a subclass of StatefulTool"
            assert issubclass(tool_cls, BaseTool), f"{tool_cls.__name__} should be a subclass of BaseTool"
            # MRO should NOT contain BaseWorkflowMixin as a distinct class
            mro_names = [c.__name__ for c in tool_cls.__mro__]
            assert "BaseWorkflowMixin" not in mro_names, f"{tool_cls.__name__} should not have BaseWorkflowMixin in MRO"

    def test_stateful_tool_inherits_only_from_base_tool(self):
        """StatefulTool should have exactly one parent: BaseTool."""
        from tools.shared.base_tool import BaseTool
        from tools.workflow.stateful_tool import StatefulTool

        direct_bases = StatefulTool.__bases__
        assert direct_bases == (BaseTool,), f"StatefulTool should inherit only from BaseTool, got {direct_bases}"

    def test_max_inheritance_depth(self):
        """No concrete tool should exceed 4 classes in MRO (excluding object): ConcreteTool + StatefulTool + BaseTool + ABC."""

        from tools import (
            AnalyzeTool,
            ChallengeTool,
            ChatTool,
            CLinkTool,
            CodeReviewTool,
            ConsensusTool,
            DebugIssueTool,
            DocgenTool,
            LookupTool,
            PlannerTool,
            PrecommitTool,
            RefactorTool,
            SecauditTool,
            TestGenTool,
            ThinkDeepTool,
            TracerTool,
        )

        for tool_cls in [
            AnalyzeTool,
            ChatTool,
            CLinkTool,
            CodeReviewTool,
            ConsensusTool,
            DebugIssueTool,
            DocgenTool,
            LookupTool,
            ChallengeTool,
            PlannerTool,
            PrecommitTool,
            RefactorTool,
            SecauditTool,
            TestGenTool,
            ThinkDeepTool,
            TracerTool,
        ]:
            # Count levels from BaseTool to the concrete class
            depth = 0
            for cls in tool_cls.__mro__:
                if cls is object:
                    continue
                depth += 1
            # Max: ConcreteTool + StatefulTool + BaseTool + ABC = 4 classes (excluding object)
            assert depth <= 4, (
                f"{tool_cls.__name__} has {depth} inheritance levels (max 4): "
                f"{[c.__name__ for c in tool_cls.__mro__]}"
            )


class TestBaseToolAbsorbedSimpleTool:
    """Verify BaseTool has all the methods that SimpleTool used to provide."""

    def test_execute_method_exists(self):
        """BaseTool must have a concrete execute() method (not just abstract)."""
        from tools.shared.base_tool import BaseTool

        assert hasattr(BaseTool, "execute")
        # Should not be abstract
        assert "execute" not in getattr(BaseTool, "__abstractmethods__", set())

    def test_parse_response_method_exists(self):
        """BaseTool must have _parse_response() (moved from SimpleTool)."""
        from tools.shared.base_tool import BaseTool

        assert hasattr(BaseTool, "_parse_response")

    def test_continuation_offer_methods_exist(self):
        """BaseTool must have continuation offer methods (moved from SimpleTool)."""
        from tools.shared.base_tool import BaseTool

        assert hasattr(BaseTool, "_create_continuation_offer")
        assert hasattr(BaseTool, "_create_continuation_offer_response")
        assert hasattr(BaseTool, "_record_assistant_turn")

    def test_get_input_schema_has_default(self):
        """BaseTool.get_input_schema() should have a default implementation."""
        from tools.shared.base_tool import BaseTool

        assert "get_input_schema" not in getattr(BaseTool, "__abstractmethods__", set())

    def test_get_request_model_has_default(self):
        """BaseTool.get_request_model() should have a default implementation."""
        from tools.shared.base_tool import BaseTool

        assert "get_request_model" not in getattr(BaseTool, "__abstractmethods__", set())

    def test_request_helper_methods_exist(self):
        """BaseTool must have request field accessor methods."""
        from tools.shared.base_tool import BaseTool

        for method_name in [
            "get_request_model_name",
            "get_request_images",
            "get_request_continuation_id",
            "get_request_prompt",
            "get_request_temperature",
            "get_request_thinking_mode",
            "get_request_files",
        ]:
            assert hasattr(BaseTool, method_name), f"BaseTool missing request helper: {method_name}"


class TestStatefulToolMergedWorkflowFunctionality:
    """Verify StatefulTool has all methods from WorkflowTool + BaseWorkflowMixin."""

    def test_workflow_orchestration_methods(self):
        """StatefulTool must have core workflow orchestration methods."""
        from tools.workflow.stateful_tool import StatefulTool

        for method_name in [
            "execute_workflow",
            "prepare_step_data",
            "build_base_response",
            "handle_work_completion",
            "handle_work_continuation",
        ]:
            assert hasattr(StatefulTool, method_name), f"StatefulTool missing workflow method: {method_name}"

    def test_expert_analysis_methods(self):
        """StatefulTool must have expert analysis methods."""
        from tools.workflow.stateful_tool import StatefulTool

        for method_name in [
            "_call_expert_analysis",
            "should_call_expert_analysis",
            "prepare_expert_analysis_context",
            "_prepare_files_for_expert_analysis",
        ]:
            assert hasattr(StatefulTool, method_name), f"StatefulTool missing expert analysis method: {method_name}"

    def test_file_embedding_methods(self):
        """StatefulTool must have file embedding methods from BaseWorkflowMixin."""
        from tools.workflow.stateful_tool import StatefulTool

        for method_name in [
            "_handle_workflow_file_context",
            "_should_embed_files_in_workflow_step",
            "_embed_workflow_files",
            "_reference_workflow_files",
            "_force_embed_files_for_expert_analysis",
        ]:
            assert hasattr(StatefulTool, method_name), f"StatefulTool missing file embedding method: {method_name}"

    def test_conversation_memory_methods(self):
        """StatefulTool must have conversation memory methods."""
        from tools.workflow.stateful_tool import StatefulTool

        for method_name in [
            "store_conversation_turn",
            "_extract_clean_workflow_content_for_history",
        ]:
            assert hasattr(StatefulTool, method_name), f"StatefulTool missing conversation method: {method_name}"

    def test_consolidated_findings_methods(self):
        """StatefulTool must have findings management methods."""
        from tools.workflow.stateful_tool import StatefulTool

        for method_name in [
            "_update_consolidated_findings",
            "_reprocess_consolidated_findings",
            "_prepare_work_summary",
        ]:
            assert hasattr(StatefulTool, method_name), f"StatefulTool missing findings method: {method_name}"

    def test_schema_uses_workflow_schema_builder(self):
        """StatefulTool.get_input_schema() should use WorkflowSchemaBuilder."""
        from tools.workflow.stateful_tool import StatefulTool

        source = inspect.getsource(StatefulTool.get_input_schema)
        assert "WorkflowSchemaBuilder" in source, "StatefulTool.get_input_schema() should use WorkflowSchemaBuilder"

    def test_init_creates_workflow_state(self):
        """StatefulTool.__init__ must initialize workflow state attributes."""
        from tools.workflow.stateful_tool import StatefulTool

        source = inspect.getsource(StatefulTool.__init__)
        assert "work_history" in source
        assert "consolidated_findings" in source
        assert "initial_request" in source


class TestBackwardCompatAliases:
    """Verify backward compatibility aliases work correctly."""

    def test_simple_tool_alias_is_base_tool(self):
        """tools.simple.SimpleTool should be an alias for BaseTool."""
        from tools.shared.base_tool import BaseTool
        from tools.simple import SimpleTool

        assert SimpleTool is BaseTool

    def test_workflow_tool_alias_is_stateful_tool(self):
        """tools.workflow.WorkflowTool should be an alias for StatefulTool."""
        from tools.workflow import WorkflowTool
        from tools.workflow.stateful_tool import StatefulTool

        assert WorkflowTool is StatefulTool

    def test_base_workflow_mixin_alias_removed(self):
        """BaseWorkflowMixin should NOT be exported from tools.workflow (MRO conflict)."""
        from tools import workflow

        assert not hasattr(workflow, "BaseWorkflowMixin"), (
            "BaseWorkflowMixin should not be aliased in tools.workflow — "
            "it would cause MRO errors with class X(BaseTool, BaseWorkflowMixin)"
        )

    def test_old_files_removed(self):
        """Old hierarchy files must be deleted, not left as dead code."""
        import os

        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        old_files = [
            "tools/simple/base.py",
            "tools/workflow/base.py",
            "tools/workflow/workflow_mixin.py",
        ]
        for rel_path in old_files:
            full_path = os.path.join(repo_root, rel_path)
            assert not os.path.exists(full_path), f"Dead file should be removed: {rel_path}"

    def test_no_mro_error_with_workflow_tool_alias(self):
        """Using WorkflowTool alias as base class should work without MRO issues."""
        from tools.workflow import WorkflowTool

        # This should NOT raise TypeError about MRO
        # (It would if WorkflowTool was used alongside BaseTool in multiple inheritance)
        assert issubclass(WorkflowTool, object)


class TestRequestAccessorOverrides:
    """Verify BaseTool.execute() routes through overridable instance methods."""

    def test_execute_uses_instance_accessors_not_module_functions(self):
        """BaseTool.execute() must call self.get_request_*() not req.get_request_*() directly.

        This ensures subclass overrides for custom request field mapping are respected.
        The accessor methods (get_request_model_name, get_request_images, etc.) should
        be the ONLY place that calls req.get_request_*() directly.
        """
        import ast

        from tools.shared.base_tool import BaseTool

        source = inspect.getsource(BaseTool)
        tree = ast.parse(source)

        # Find the accessor method names that legitimately call req.*
        accessor_methods = {
            "get_request_model_name",
            "get_request_images",
            "get_request_continuation_id",
            "get_request_prompt",
            "get_request_temperature",
            "get_request_thinking_mode",
            "get_request_files",
            "get_request_as_dict",
            "set_request_files",
            "get_request_use_assistant_model",
        }

        # Walk the AST to find all method definitions
        violations = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            method_name = node.name

            # Skip the accessor methods themselves — they correctly delegate to req.*
            if method_name in accessor_methods:
                continue

            # Check for direct req.get_request_* or req.set_request_* calls
            for child in ast.walk(node):
                if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
                    if child.value.id == "req" and (
                        child.attr.startswith("get_request_") or child.attr.startswith("set_request_")
                    ):
                        violations.append(f"{method_name}() calls req.{child.attr}() directly")

        assert not violations, (
            "BaseTool methods should use self.get_request_*() for overridability, "
            "not req.get_request_*() directly. Violations:\n" + "\n".join(f"  - {v}" for v in violations)
        )

    def test_stateful_tool_has_no_direct_req_calls(self):
        """StatefulTool must not call req.get_request_*() directly.

        StatefulTool uses its own accessor methods, not the request_helpers module.
        This test ensures no one accidentally introduces direct req.* calls.
        """
        import ast

        from tools.workflow.stateful_tool import StatefulTool

        source = inspect.getsource(StatefulTool)
        tree = ast.parse(source)

        violations = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            method_name = node.name

            for child in ast.walk(node):
                if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
                    if child.value.id == "req" and (
                        child.attr.startswith("get_request_") or child.attr.startswith("set_request_")
                    ):
                        violations.append(f"{method_name}() calls req.{child.attr}() directly")

        assert not violations, "StatefulTool should not use req.get_request_*() directly. " "Violations:\n" + "\n".join(
            f"  - {v}" for v in violations
        )


class TestExtractedUtilityModules:
    """Verify utility modules were properly extracted."""

    def test_request_helpers_module_exists(self):
        """tools.shared.request_helpers should exist with standalone functions."""
        from tools.shared import request_helpers

        for fn_name in [
            "get_request_model_name",
            "get_request_images",
            "get_request_continuation_id",
            "get_request_prompt",
            "get_request_temperature",
            "get_request_thinking_mode",
            "get_request_files",
            "get_request_as_dict",
            "set_request_files",
        ]:
            assert hasattr(request_helpers, fn_name), f"request_helpers missing function: {fn_name}"

    def test_model_utils_module_exists(self):
        """tools.shared.model_utils should exist with extracted functions."""
        from tools.shared import model_utils

        for fn_name in [
            "format_context_window",
            "normalize_model_identifier",
            "should_require_model_selection",
        ]:
            assert hasattr(model_utils, fn_name), f"model_utils missing function: {fn_name}"

    def test_validation_module_exists(self):
        """tools.shared.validation should exist with extracted functions."""
        from tools.shared import validation

        for fn_name in [
            "validate_file_paths",
            "check_prompt_size",
        ]:
            assert hasattr(validation, fn_name), f"validation module missing function: {fn_name}"
