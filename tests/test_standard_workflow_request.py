"""
Tests for StandardWorkflowRequest base class and build_workflow_descriptions factory.

Validates the shared infrastructure added to reduce duplication across workflow tools.
"""

import pytest
from pydantic import ValidationError

from tools.shared.base_models import (
    StandardWorkflowRequest,
    WorkflowRequest,
    build_workflow_descriptions,
)


class TestBuildWorkflowDescriptions:
    """Tests for the build_workflow_descriptions factory function."""

    def test_returns_all_expected_keys(self):
        """The factory should return descriptions for all standard workflow fields."""
        descs = build_workflow_descriptions("review")
        expected_keys = {
            "step_number",
            "total_steps",
            "next_step_required",
            "findings",
            "files_checked",
            "relevant_files",
            "relevant_context",
            "issues_found",
            "confidence",
            "images",
        }
        assert set(descs.keys()) == expected_keys

    def test_activity_name_parameterised(self):
        """The activity name should appear in parameterised descriptions."""
        descs = build_workflow_descriptions("security audit")
        assert "security audit" in descs["step_number"]
        assert "security audit" in descs["total_steps"]
        assert "security audit" in descs["next_step_required"]
        assert "security audit" in descs["findings"]

    def test_static_descriptions_unchanged(self):
        """Fields like files_checked that don't use activity should be consistent."""
        descs_a = build_workflow_descriptions("review")
        descs_b = build_workflow_descriptions("investigation")
        assert descs_a["files_checked"] == descs_b["files_checked"]
        assert descs_a["relevant_context"] == descs_b["relevant_context"]
        assert descs_a["images"] == descs_b["images"]

    def test_merge_with_tool_specific(self):
        """Tool-specific descriptions should override factory defaults."""
        tool_descs = {
            **build_workflow_descriptions("review"),
            "step": "Custom step description for reviews.",
            "findings": "Custom findings for reviews.",
        }
        assert tool_descs["step"] == "Custom step description for reviews."
        assert tool_descs["findings"] == "Custom findings for reviews."
        # Non-overridden keys should still come from the factory
        assert "review" in tool_descs["step_number"]


class TestStandardWorkflowRequest:
    """Tests for the StandardWorkflowRequest base class."""

    def test_inherits_from_workflow_request(self):
        """StandardWorkflowRequest should be a subclass of WorkflowRequest."""
        assert issubclass(StandardWorkflowRequest, WorkflowRequest)

    def test_temperature_excluded_from_serialization(self):
        """temperature should be excluded from model_dump by default."""
        req = StandardWorkflowRequest(
            step="Test",
            step_number=1,
            total_steps=1,
            next_step_required=False,
            findings="Test",
            temperature=0.5,
        )
        dumped = req.model_dump()
        assert "temperature" not in dumped

    def test_thinking_mode_excluded_from_serialization(self):
        """thinking_mode should be excluded from model_dump by default."""
        req = StandardWorkflowRequest(
            step="Test",
            step_number=1,
            total_steps=1,
            next_step_required=False,
            findings="Test",
            thinking_mode="high",
        )
        dumped = req.model_dump()
        assert "thinking_mode" not in dumped

    def test_basic_validation_passes(self):
        """A valid request should parse without errors."""
        req = StandardWorkflowRequest(
            step="Investigating the issue",
            step_number=1,
            total_steps=3,
            next_step_required=True,
            findings="Found a potential issue",
        )
        assert req.step == "Investigating the issue"
        assert req.step_number == 1

    def test_no_step_one_validation_by_default(self):
        """Without _step_one_required_field, step 1 should not require extra fields."""
        req = StandardWorkflowRequest(
            step="Start",
            step_number=1,
            total_steps=2,
            next_step_required=True,
            findings="Initial",
        )
        assert req.step_number == 1


class TestStandardWorkflowRequestStepOneValidation:
    """Tests for the step-1 required-field validation mechanism."""

    def _make_subclass(self, field_name, error_msg=None):
        """Create a test subclass with step-1 validation."""

        class TestRequest(StandardWorkflowRequest):
            _step_one_required_field = field_name
            _step_one_error_message = error_msg

        return TestRequest

    def test_step_one_missing_required_field_raises(self):
        """Step 1 should raise when the required field is empty."""
        TestRequest = self._make_subclass(
            "relevant_files",
            "Step 1 requires 'relevant_files'",
        )
        with pytest.raises(ValidationError, match="Step 1 requires 'relevant_files'"):
            TestRequest(
                step="Start",
                step_number=1,
                total_steps=2,
                next_step_required=True,
                findings="Initial",
                relevant_files=[],
            )

    def test_step_one_with_required_field_passes(self):
        """Step 1 should pass when the required field is populated."""
        TestRequest = self._make_subclass(
            "relevant_files",
            "Step 1 requires 'relevant_files'",
        )
        req = TestRequest(
            step="Start",
            step_number=1,
            total_steps=2,
            next_step_required=True,
            findings="Initial",
            relevant_files=["/path/to/file.py"],
        )
        assert req.relevant_files == ["/path/to/file.py"]

    def test_step_two_does_not_require_field(self):
        """Step 2+ should not enforce the step-1 requirement."""
        TestRequest = self._make_subclass("relevant_files", "Step 1 requires files")
        req = TestRequest(
            step="Continue",
            step_number=2,
            total_steps=3,
            next_step_required=True,
            findings="More findings",
            relevant_files=[],
        )
        assert req.step_number == 2

    def test_default_error_message(self):
        """When no custom error message is provided, a default should be used."""
        TestRequest = self._make_subclass("relevant_files")
        with pytest.raises(ValidationError, match="Step 1 requires 'relevant_files' field"):
            TestRequest(
                step="Start",
                step_number=1,
                total_steps=1,
                next_step_required=False,
                findings="None",
            )


class TestToolRequestsUseStandardWorkflow:
    """Verify that actual tool request models correctly inherit from StandardWorkflowRequest."""

    def test_codereview_inherits(self):
        from tools.codereview import CodeReviewRequest

        assert issubclass(CodeReviewRequest, StandardWorkflowRequest)

    def test_refactor_inherits(self):
        from tools.refactor import RefactorRequest

        assert issubclass(RefactorRequest, StandardWorkflowRequest)

    def test_debug_inherits(self):
        from tools.debug import DebugInvestigationRequest

        assert issubclass(DebugInvestigationRequest, StandardWorkflowRequest)

    def test_precommit_inherits(self):
        from tools.precommit import PrecommitRequest

        assert issubclass(PrecommitRequest, StandardWorkflowRequest)

    def test_analyze_inherits(self):
        from tools.analyze import AnalyzeWorkflowRequest

        assert issubclass(AnalyzeWorkflowRequest, StandardWorkflowRequest)

    def test_docgen_inherits(self):
        from tools.docgen import DocgenRequest

        assert issubclass(DocgenRequest, StandardWorkflowRequest)

    def test_secaudit_inherits(self):
        from tools.secaudit import SecauditRequest

        assert issubclass(SecauditRequest, StandardWorkflowRequest)

    def test_testgen_inherits(self):
        from tools.testgen import TestGenRequest

        assert issubclass(TestGenRequest, StandardWorkflowRequest)

    def test_tracer_inherits(self):
        from tools.tracer import TracerRequest

        assert issubclass(TracerRequest, StandardWorkflowRequest)

    def test_thinkdeep_inherits(self):
        from tools.thinkdeep import ThinkDeepWorkflowRequest

        assert issubclass(ThinkDeepWorkflowRequest, StandardWorkflowRequest)

    def test_consensus_inherits(self):
        from tools.consensus import ConsensusRequest

        assert issubclass(ConsensusRequest, StandardWorkflowRequest)

    def test_planner_inherits(self):
        from tools.planner import PlannerRequest

        assert issubclass(PlannerRequest, StandardWorkflowRequest)


class TestToolStepOneValidation:
    """Verify that step-1 validation works correctly for actual tool request models."""

    def test_codereview_requires_relevant_files_step_1(self):
        from tools.codereview import CodeReviewRequest

        with pytest.raises(ValidationError, match="relevant_files"):
            CodeReviewRequest(
                step="Start review",
                step_number=1,
                total_steps=2,
                next_step_required=True,
                findings="None",
                relevant_files=[],
            )

    def test_refactor_requires_relevant_files_step_1(self):
        from tools.refactor import RefactorRequest

        with pytest.raises(ValidationError, match="relevant_files"):
            RefactorRequest(
                step="Start refactoring",
                step_number=1,
                total_steps=2,
                next_step_required=True,
                findings="None",
                relevant_files=[],
            )

    def test_analyze_requires_relevant_files_step_1(self):
        from tools.analyze import AnalyzeWorkflowRequest

        with pytest.raises(ValidationError, match="relevant_files"):
            AnalyzeWorkflowRequest(
                step="Start analysis",
                step_number=1,
                total_steps=2,
                next_step_required=True,
                findings="None",
                relevant_files=[],
            )

    def test_testgen_requires_relevant_files_step_1(self):
        from tools.testgen import TestGenRequest

        with pytest.raises(ValidationError, match="relevant_files"):
            TestGenRequest(
                step="Start test gen",
                step_number=1,
                total_steps=2,
                next_step_required=True,
                findings="None",
                relevant_files=[],
            )

    def test_precommit_requires_path_step_1(self):
        from tools.precommit import PrecommitRequest

        with pytest.raises(ValidationError, match="path"):
            PrecommitRequest(
                step="Start validation",
                step_number=1,
                total_steps=2,
                next_step_required=True,
                findings="None",
            )

    def test_consensus_requires_models_step_1(self):
        from tools.consensus import ConsensusRequest

        with pytest.raises(ValidationError, match="models"):
            ConsensusRequest(
                step="Start consensus",
                step_number=1,
                total_steps=3,
                next_step_required=True,
                findings="Analysis",
            )


class TestWorkflowToolBaseClassDefaults:
    """Verify that WorkflowTool base class sets initial_request and tool_config."""

    def test_workflow_tool_has_initial_request(self):
        from tools.codereview import CodeReviewTool

        tool = CodeReviewTool()
        assert hasattr(tool, "initial_request")
        assert tool.initial_request is None

    def test_workflow_tool_has_tool_config(self):
        from tools.codereview import CodeReviewTool

        tool = CodeReviewTool()
        assert hasattr(tool, "tool_config")
        assert tool.tool_config == {}
