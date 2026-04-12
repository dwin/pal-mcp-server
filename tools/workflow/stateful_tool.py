"""
Base class for stateful (multi-step workflow) MCP tools.

Stateful tools follow a multi-step pattern:
1. CLI calls tool with work step data
2. Tool tracks findings and progress
3. Tool forces the CLI to pause and investigate between steps
4. Once work is complete, tool calls external AI model for expert analysis
5. Tool returns structured response combining investigation + expert analysis

StatefulTool inherits from BaseTool and adds workflow orchestration,
step management, expert analysis integration, and conversation memory.
"""

import json
import logging
import os
import re
from abc import abstractmethod
from typing import Any, Optional

from mcp.types import TextContent

from config import MCP_PROMPT_SIZE_LIMIT
from tools.shared.base_models import ConsolidatedFindings, WorkflowRequest
from tools.shared.base_tool import BaseTool
from tools.shared.exceptions import ToolExecutionError
from utils.conversation_memory import add_turn, create_thread

from .schema_builders import WorkflowSchemaBuilder

logger = logging.getLogger(__name__)


class StatefulTool(BaseTool):
    """
    Base class for stateful (multi-step workflow) tools.

    Stateful tools perform systematic multi-step work with expert analysis.
    They benefit from:
    - Automatic workflow orchestration
    - Automatic schema generation using WorkflowSchemaBuilder
    - Inherited conversation handling and file processing from BaseTool
    - Progress tracking with ConsolidatedFindings
    - Expert analysis integration

    To create a stateful tool:
    1. Inherit from StatefulTool
    2. Implement get_name() and get_description()
    3. Implement get_required_actions() for step guidance
    4. Optionally override should_call_expert_analysis() for completion criteria
    5. Optionally override prepare_expert_analysis_context() for expert prompts
    6. Optionally implement get_tool_fields() for additional fields
    7. Optionally override workflow behavior methods
    """

    def __init__(self):
        super().__init__()
        self.work_history: list[dict[str, Any]] = []
        self.consolidated_findings: ConsolidatedFindings = ConsolidatedFindings()
        self.initial_request: Optional[str] = None

    # ================================================================================
    # Abstract Methods - Tool-Specific Implementation Required
    # ================================================================================

    @abstractmethod
    def get_required_actions(
        self, step_number: int, confidence: str, findings: str, total_steps: int, request=None
    ) -> list[str]:
        """Define required actions for each work phase.

        Args:
            step_number: Current step (1-based)
            confidence: Current confidence level (exploring, low, medium, high, certain)
            findings: Current findings text
            total_steps: Total estimated steps for this work
            request: Optional request object for continuation-aware decisions

        Returns:
            List of specific actions the CLI should take before calling tool again
        """
        pass

    # ================================================================================
    # Schema and Request Model Methods (from WorkflowTool)
    # ================================================================================

    def get_tool_fields(self) -> dict[str, dict[str, Any]]:
        """
        Return tool-specific field definitions beyond the standard workflow fields.

        Workflow tools automatically get all standard workflow fields.
        Override this method to add additional tool-specific fields.
        """
        return {}

    def get_required_fields(self) -> list[str]:
        """
        Return additional required fields beyond the standard workflow requirements.
        Override this to add additional required fields.
        """
        return []

    def get_annotations(self) -> Optional[dict[str, Any]]:
        """Workflow tools are read-only by default."""
        return {"readOnlyHint": True}

    def get_input_schema(self) -> dict[str, Any]:
        """Generate the complete input schema using WorkflowSchemaBuilder."""
        requires_model = self.requires_model()
        model_field_schema = self.get_model_field_schema() if requires_model else None
        auto_mode = self.is_effective_auto_mode() if requires_model else False
        return WorkflowSchemaBuilder.build_schema(
            tool_specific_fields=self.get_tool_fields(),
            required_fields=self.get_required_fields(),
            model_field_schema=model_field_schema,
            auto_mode=auto_mode,
            tool_name=self.get_name(),
            require_model=requires_model,
        )

    def get_workflow_request_model(self):
        """Return the workflow request model class. Override for custom request models."""
        return WorkflowRequest

    def get_work_steps(self, request) -> list[str]:
        """
        Default implementation - workflow tools typically don't need predefined steps.
        Override this if your tool needs specific step guidance.
        """
        return []

    # ================================================================================
    # Hook Methods - Default Implementations with Override Capability
    # ================================================================================

    def requires_expert_analysis(self) -> bool:
        """
        Override this to completely disable expert analysis for the tool.
        Returns True if the tool supports expert analysis (default).
        Returns False if the tool is self-contained (like planner).
        """
        return True

    def should_include_files_in_expert_prompt(self) -> bool:
        """Whether to include file content in the expert analysis prompt."""
        return False

    def should_embed_system_prompt(self) -> bool:
        """Whether to embed the system prompt in the main prompt."""
        return False

    def get_expert_thinking_mode(self) -> str:
        """Get the thinking mode for expert analysis."""
        return "high"

    def get_expert_analysis_instruction(self) -> str:
        """Get the instruction to append after the expert context."""
        return "Please provide expert analysis based on the investigation findings."

    def should_call_expert_analysis(self, consolidated_findings: ConsolidatedFindings, request=None) -> bool:
        """
        Decide when to call external model based on tool-specific criteria.
        Override this for tools that use expert analysis.
        """
        if not self.requires_expert_analysis():
            return False

        # Check if user requested to skip assistant model
        if request and not self.get_request_use_assistant_model(request):
            return False

        # Default logic for tools that support expert analysis
        return (
            len(consolidated_findings.relevant_files) > 0
            or len(consolidated_findings.findings) >= 2
            or len(consolidated_findings.issues_found) > 0
        )

    def prepare_expert_analysis_context(self, consolidated_findings: ConsolidatedFindings) -> str:
        """
        Prepare context for external model call.
        Override this for tools that use expert analysis.
        """
        if not self.requires_expert_analysis():
            return ""

        # Default context preparation
        context_parts = [
            f"=== {self.get_name().upper()} WORK SUMMARY ===",
            f"Total steps: {len(consolidated_findings.findings)}",
            f"Files examined: {len(consolidated_findings.files_checked)}",
            f"Relevant files: {len(consolidated_findings.relevant_files)}",
            "",
            "=== WORK PROGRESSION ===",
        ]

        for finding in consolidated_findings.findings:
            context_parts.append(finding)

        return "\n".join(context_parts)

    def wants_line_numbers_by_default(self) -> bool:
        """Whether this tool wants line numbers in file content by default."""
        return True

    def should_skip_expert_analysis(self, request, consolidated_findings) -> bool:
        """
        Determine if expert analysis should be skipped due to high certainty.
        Default: False. Override in tools like debug to check for "certain" confidence.
        """
        return False

    # ================================================================================
    # Request Field Access Methods (workflow-specific)
    # ================================================================================

    def get_request_temperature(self, request) -> float:
        """Get temperature from request. Override for custom temperature handling."""
        try:
            return request.temperature if request.temperature is not None else self.get_default_temperature()
        except AttributeError:
            return self.get_default_temperature()

    def get_validated_temperature(self, request, model_context: Any) -> tuple[float, list[str]]:
        """Get temperature from request and validate it against model constraints."""
        temperature = self.get_request_temperature(request)
        return self.validate_and_correct_temperature(temperature, model_context)

    def get_request_thinking_mode(self, request) -> str:
        """Get thinking mode from request. Override for custom thinking mode handling."""
        try:
            return request.thinking_mode if request.thinking_mode is not None else self.get_expert_thinking_mode()
        except AttributeError:
            return self.get_expert_thinking_mode()

    def get_request_use_assistant_model(self, request) -> bool:
        """Get use_assistant_model from request."""
        try:
            return request.use_assistant_model if request.use_assistant_model is not None else True
        except AttributeError:
            return True

    def get_request_confidence(self, request: Any) -> str:
        """Get confidence from request. Override for custom confidence handling."""
        try:
            return request.confidence or "low"
        except AttributeError:
            return "low"

    def get_request_relevant_context(self, request: Any) -> list[str]:
        """Get relevant context from request. Override for custom field mapping."""
        try:
            return request.relevant_context or []
        except AttributeError:
            return []

    def get_request_issues_found(self, request: Any) -> list[str]:
        """Get issues found from request. Override for custom field mapping."""
        try:
            return request.issues_found or []
        except AttributeError:
            return []

    def get_request_hypothesis(self, request: Any) -> Optional[str]:
        """Get hypothesis from request. Override for custom field mapping."""
        try:
            return request.hypothesis
        except AttributeError:
            return None

    def get_request_images(self, request: Any) -> list[str]:
        """Get images from request. Override for custom field mapping."""
        try:
            return request.images or []
        except AttributeError:
            return []

    def get_request_model_name(self, request: Any) -> str:
        """Get model name from request. Override for custom model handling."""
        try:
            return request.model or "flash"
        except AttributeError:
            return "flash"

    def get_request_continuation_id(self, request: Any) -> Optional[str]:
        """Get continuation ID from request."""
        try:
            return request.continuation_id
        except AttributeError:
            return None

    def get_request_next_step_required(self, request: Any) -> bool:
        """Get next step required from request."""
        try:
            return request.next_step_required
        except AttributeError:
            return True

    def get_request_step_number(self, request: Any) -> int:
        """Get step number from request."""
        try:
            return request.step_number or 1
        except AttributeError:
            return 1

    def get_request_relevant_files(self, request: Any) -> list[str]:
        """Get relevant files from request."""
        try:
            return request.relevant_files or []
        except AttributeError:
            return []

    def get_request_files_checked(self, request: Any) -> list[str]:
        """Get files checked from request."""
        try:
            return request.files_checked or []
        except AttributeError:
            return []

    # ================================================================================
    # State Access Methods
    # ================================================================================

    def get_embedded_file_content(self) -> str:
        """Get embedded file content. Returns empty string if not available."""
        try:
            return self._embedded_file_content or ""
        except AttributeError:
            return ""

    def get_file_reference_note(self) -> str:
        """Get file reference note. Returns empty string if not available."""
        try:
            return self._file_reference_note or ""
        except AttributeError:
            return ""

    def get_actually_processed_files(self) -> list[str]:
        """Get list of actually processed files. Returns empty list if not available."""
        try:
            return self._actually_processed_files or []
        except AttributeError:
            return []

    def get_current_model_context(self):
        """Get current model context. Returns None if not available."""
        try:
            return self._model_context
        except AttributeError:
            return None

    def get_current_arguments(self) -> dict[str, Any]:
        """Get current arguments. Returns empty dict if not available."""
        try:
            return self._current_arguments or {}
        except AttributeError:
            return {}

    def store_initial_issue(self, step_description: str):
        """Store initial issue description. Override for custom storage."""
        self.initial_issue = step_description

    def get_initial_request(self, fallback_step: str) -> str:
        """Get initial request description."""
        try:
            return self.initial_request or fallback_step
        except AttributeError:
            return fallback_step

    # ================================================================================
    # Completion and Guidance Hook Methods
    # ================================================================================

    def prepare_work_summary(self) -> str:
        """Prepare a summary of the work performed. Override for custom summaries."""
        try:
            return self._prepare_work_summary()
        except AttributeError:
            try:
                return f"Completed {len(self.work_history)} work steps"
            except AttributeError:
                return "Completed 0 work steps"

    def get_completion_status(self) -> str:
        """Get the status to use when completing without expert analysis."""
        return "high_confidence_completion"

    def get_completion_data_key(self) -> str:
        """Get the key name for completion data in the response."""
        return f"complete_{self.get_name()}"

    def get_final_analysis_from_request(self, request) -> Optional[str]:
        """Extract final analysis from request. Override for tool-specific extraction."""
        try:
            return request.hypothesis
        except AttributeError:
            return None

    def get_confidence_level(self, request) -> str:
        """Get confidence level from request. Override for tool-specific logic."""
        try:
            return request.confidence or "high"
        except AttributeError:
            return "high"

    def get_completion_message(self) -> str:
        """Get completion message. Override for tool-specific messaging."""
        return (
            f"{self.get_name().capitalize()} complete with high confidence. You have identified the exact "
            "analysis and solution. MANDATORY: Present the user with the results "
            "and proceed with implementing the solution without requiring further "
            "consultation. Focus on the precise, actionable steps needed."
        )

    def get_skip_reason(self) -> str:
        """Get reason for skipping expert analysis."""
        return f"{self.get_name()} completed with sufficient confidence"

    def get_skip_expert_analysis_status(self) -> str:
        """Get status for skipped expert analysis."""
        return "skipped_by_tool_design"

    def get_completion_next_steps_message(self, expert_analysis_used: bool = False) -> str:
        """Get the message to show when work is complete."""
        base_message = (
            f"{self.get_name().upper()} IS COMPLETE. You MUST now summarize and present ALL key findings, confirmed "
            "hypotheses, and exact recommended solutions. Clearly identify the most likely root cause and "
            "provide concrete, actionable implementation guidance. Highlight affected code paths and display "
            "reasoning that led to this conclusion—make it easy for a developer to understand exactly where "
            "the problem lies."
        )

        if expert_analysis_used:
            expert_guidance = self.get_expert_analysis_guidance()
            if expert_guidance:
                return f"{base_message}\n\n{expert_guidance}"

        return base_message

    def get_expert_analysis_guidance(self) -> str:
        """
        Get additional guidance for handling expert analysis results.
        Subclasses can override this to provide specific instructions.
        """
        return ""

    def get_step_guidance_message(self, request) -> str:
        """Get step guidance message. Override for tool-specific guidance."""
        required_actions = self.get_required_actions(
            request.step_number, self.get_request_confidence(request), request.findings, request.total_steps, request
        )

        next_step_number = request.step_number + 1
        return (
            f"MANDATORY: DO NOT call the {self.get_name()} tool again immediately. "
            f"You MUST first work using appropriate tools. "
            f"REQUIRED ACTIONS before calling {self.get_name()} step {next_step_number}:\n"
            + "\n".join(f"{i + 1}. {action}" for i, action in enumerate(required_actions))
            + f"\n\nOnly call {self.get_name()} again with step_number: {next_step_number} "
            f"AFTER completing this work."
        )

    def is_continuation_workflow(self, request) -> bool:
        """Check if this is a continuation workflow that should skip multi-step investigation."""
        continuation_id = self.get_request_continuation_id(request)
        return bool(continuation_id)

    # ================================================================================
    # Standard Helper Methods (from WorkflowTool)
    # ================================================================================

    def get_standard_required_actions(self, step_number: int, confidence: str, base_actions: list[str]) -> list[str]:
        """Helper method to generate standard required actions based on confidence and step."""
        if step_number == 1:
            return [
                "Search for code related to the reported issue or symptoms",
                "Examine relevant files and understand the current implementation",
                "Understand the project structure and locate relevant modules",
                "Identify how the affected functionality is supposed to work",
            ]
        elif confidence in ["exploring", "low"]:
            return base_actions + [
                "Trace method calls and data flow through the system",
                "Check for edge cases, boundary conditions, and assumptions in the code",
                "Look for related configuration, dependencies, or external factors",
            ]
        elif confidence in ["medium", "high"]:
            return base_actions + [
                "Examine the exact code sections where you believe the issue occurs",
                "Trace the execution path that leads to the failure",
                "Verify your hypothesis with concrete code evidence",
                "Check for any similar patterns elsewhere in the codebase",
            ]
        else:
            return base_actions + [
                "Continue examining the code paths identified in your hypothesis",
                "Gather more evidence using appropriate investigation tools",
                "Test edge cases and boundary conditions",
                "Look for patterns that confirm or refute your theory",
            ]

    def should_call_expert_analysis_default(self, consolidated_findings) -> bool:
        """Default implementation for expert analysis decision."""
        return (
            len(consolidated_findings.relevant_files) > 0
            or len(consolidated_findings.findings) >= 2
            or len(consolidated_findings.issues_found) > 0
        )

    def prepare_standard_expert_context(
        self, consolidated_findings, initial_description: str, context_sections: dict[str, str] = None
    ) -> str:
        """Helper method to prepare standard expert analysis context."""
        context_parts = [f"=== ISSUE DESCRIPTION ===\n{initial_description}\n=== END DESCRIPTION ==="]

        if consolidated_findings.findings:
            findings_text = "\n".join(consolidated_findings.findings)
            context_parts.append(f"\n=== INVESTIGATION FINDINGS ===\n{findings_text}\n=== END FINDINGS ===")

        if consolidated_findings.relevant_context:
            methods_text = "\n".join(f"- {method}" for method in consolidated_findings.relevant_context)
            context_parts.append(f"\n=== RELEVANT METHODS/FUNCTIONS ===\n{methods_text}\n=== END METHODS ===")

        if consolidated_findings.hypotheses:
            hypotheses_text = "\n".join(
                f"Step {h['step']} ({h['confidence']} confidence): {h['hypothesis']}"
                for h in consolidated_findings.hypotheses
            )
            context_parts.append(f"\n=== HYPOTHESIS EVOLUTION ===\n{hypotheses_text}\n=== END HYPOTHESES ===")

        if consolidated_findings.issues_found:
            issues_text = "\n".join(
                f"[{issue.get('severity', 'unknown').upper()}] {issue.get('description', 'No description')}"
                for issue in consolidated_findings.issues_found
            )
            context_parts.append(f"\n=== ISSUES IDENTIFIED ===\n{issues_text}\n=== END ISSUES ===")

        if context_sections:
            for section_title, section_content in context_sections.items():
                context_parts.append(
                    f"\n=== {section_title.upper()} ===\n{section_content}\n=== END {section_title.upper()} ==="
                )

        return "\n".join(context_parts)

    # ================================================================================
    # Context-Aware File Embedding
    # ================================================================================

    def _handle_workflow_file_context(self, request: Any, arguments: dict[str, Any]) -> None:
        """Handle file context appropriately based on workflow phase."""
        continuation_id = self.get_request_continuation_id(request)
        is_final_step = not self.get_request_next_step_required(request)
        step_number = self.get_request_step_number(request)

        # Only overwrite model context if provided in arguments (in-process tests);
        # otherwise keep the context already resolved in execute_workflow().
        model_context = arguments.get("_model_context")
        if model_context is not None:
            self._model_context = model_context

        self._embedded_file_content = ""
        self._file_reference_note = ""
        self._actually_processed_files = []

        should_embed_files = self._should_embed_files_in_workflow_step(step_number, continuation_id, is_final_step)

        if should_embed_files:
            logger.debug(f"[WORKFLOW_FILES] {self.get_name()}: Embedding files for final step/expert analysis")
            self._embed_workflow_files(request, arguments)
        else:
            logger.debug(f"[WORKFLOW_FILES] {self.get_name()}: Only referencing file names for intermediate step")
            self._reference_workflow_files(request)

    def _should_embed_files_in_workflow_step(
        self, step_number: int, continuation_id: Optional[str], is_final_step: bool
    ) -> bool:
        """Determine whether to embed file content based on workflow context."""
        if is_final_step:
            logger.debug("[WORKFLOW_FILES] Final step - will embed files for expert analysis")
            return True

        logger.debug("[WORKFLOW_FILES] Intermediate step (more work needed) - will only reference files")
        return False

    def _embed_workflow_files(self, request: Any, arguments: dict[str, Any]) -> None:
        """Embed full file content for final steps and expert analysis."""
        request_files = self.get_request_relevant_files(request)
        if not request_files:
            logger.debug(f"[WORKFLOW_FILES] {self.get_name()}: No relevant_files to embed")
            return

        try:
            current_model_context = self.get_current_model_context()
            if not current_model_context:
                try:
                    model_name, model_context = self._resolve_model_context(arguments, request)
                    self._model_context = model_context
                    self._current_model_name = model_name
                except Exception as e:
                    logger.error(f"[WORKFLOW_FILES] {self.get_name()}: Failed to resolve model context: {e}")
                    from utils.model_context import ModelContext

                    model_name = self.get_request_model_name(request)
                    self._model_context = ModelContext(model_name)
                    self._current_model_name = model_name

            continuation_id = self.get_request_continuation_id(request)
            remaining_tokens = arguments.get("_remaining_tokens")

            file_content, processed_files = self._prepare_file_content_for_prompt(
                request_files,
                continuation_id,
                "Workflow files for analysis",
                remaining_budget=remaining_tokens,
                arguments=arguments,
                model_context=self._model_context,
            )

            self._embedded_file_content = file_content
            self._actually_processed_files = processed_files

            logger.info(
                f"[WORKFLOW_FILES] {self.get_name()}: Embedded {len(processed_files)} relevant_files for final analysis"
            )

        except Exception as e:
            logger.error(f"[WORKFLOW_FILES] {self.get_name()}: Failed to embed files: {e}")
            self._embedded_file_content = ""
            self._actually_processed_files = []

    def _reference_workflow_files(self, request: Any) -> None:
        """Reference file names without embedding content for intermediate steps."""
        request_files = self.get_request_relevant_files(request)
        logger.debug(
            f"[WORKFLOW_FILES] {self.get_name()}: _reference_workflow_files called with {len(request_files)} relevant_files"
        )

        if not request_files:
            logger.debug(f"[WORKFLOW_FILES] {self.get_name()}: No files to reference, skipping")
            return

        self._referenced_files = request_files

        file_names = [os.path.basename(f) for f in request_files]
        reference_note = f"Files referenced in this step: {', '.join(file_names)}\n"

        self._file_reference_note = reference_note
        logger.debug(f"[WORKFLOW_FILES] {self.get_name()}: Set _file_reference_note: {self._file_reference_note}")

        logger.info(
            f"[WORKFLOW_FILES] {self.get_name()}: Referenced {len(request_files)} files without embedding content"
        )

    def _prepare_files_for_expert_analysis(self) -> str:
        """Prepare file content for expert analysis."""
        all_relevant_files = set()

        all_relevant_files.update(self.consolidated_findings.relevant_files)

        try:
            current_arguments = self.get_current_arguments()
            if current_arguments:
                continuation_id = current_arguments.get("continuation_id")

                if continuation_id:
                    from utils.conversation_memory import get_conversation_file_list, get_thread

                    thread_context = get_thread(continuation_id)
                    if thread_context:
                        conversation_files = get_conversation_file_list(thread_context)
                        all_relevant_files.update(conversation_files)
                        logger.debug(
                            f"[WORKFLOW_FILES] {self.get_name()}: Added {len(conversation_files)} files from conversation history"
                        )
        except Exception as e:
            logger.warning(f"[WORKFLOW_FILES] {self.get_name()}: Could not get conversation files: {e}")

        files_for_expert = [f for f in all_relevant_files if f and f.strip()]

        if not files_for_expert:
            logger.debug(f"[WORKFLOW_FILES] {self.get_name()}: No relevant files found for expert analysis")
            return ""

        try:
            file_content, processed_files = self._force_embed_files_for_expert_analysis(files_for_expert)

            logger.info(
                f"[WORKFLOW_FILES] {self.get_name()}: Prepared {len(processed_files)} unique relevant files for expert analysis "
                f"(from {len(self.consolidated_findings.relevant_files)} current relevant files)"
            )

            return file_content

        except Exception as e:
            logger.error(f"[WORKFLOW_FILES] {self.get_name()}: Failed to prepare files for expert analysis: {e}")
            return ""

    def _force_embed_files_for_expert_analysis(self, files: list[str]) -> tuple[str, list[str]]:
        """Force embed files for expert analysis, bypassing conversation history filtering."""
        from utils.file_utils import expand_paths, read_files

        current_model_context = self.get_current_model_context()
        if current_model_context:
            try:
                token_allocation = current_model_context.calculate_token_allocation()
                max_tokens = token_allocation.file_tokens
                logger.debug(
                    f"[WORKFLOW_FILES] {self.get_name()}: Using {max_tokens:,} tokens for expert analysis files"
                )
            except Exception as e:
                logger.warning(f"[WORKFLOW_FILES] {self.get_name()}: Failed to get token allocation: {e}")
                max_tokens = 100_000
        else:
            max_tokens = 100_000

        logger.debug(f"[WORKFLOW_FILES] {self.get_name()}: Force embedding {len(files)} files for expert analysis")
        file_content = read_files(
            files,
            max_tokens=max_tokens,
            reserve_tokens=1000,
            include_line_numbers=self.wants_line_numbers_by_default(),
        )

        processed_files = expand_paths(files)

        logger.debug(
            f"[WORKFLOW_FILES] {self.get_name()}: Expert analysis embedding: {len(processed_files)} files, "
            f"{len(file_content):,} characters"
        )

        return file_content, processed_files

    def _add_files_to_expert_context(self, expert_context: str, file_content: str) -> str:
        """Add file content to the expert context."""
        return f"{expert_context}\n\n=== ESSENTIAL FILES ===\n{file_content}\n=== END ESSENTIAL FILES ==="

    # ================================================================================
    # Main Workflow Orchestration
    # ================================================================================

    async def execute_workflow(self, arguments: dict[str, Any]) -> list[TextContent]:
        """
        Main workflow orchestration following debug tool pattern.

        Comprehensive workflow implementation that handles all common patterns:
        1. Request validation and step management
        2. Continuation and backtracking support
        3. Step data processing and consolidation
        4. Tool-specific field mapping and customization
        5. Completion logic with optional expert analysis
        6. Generic "certain confidence" handling
        7. Step guidance and required actions
        8. Conversation memory integration
        """
        try:
            # Store arguments for access by helper methods
            self._current_arguments = arguments

            # Validate request using tool-specific model
            request = self.get_workflow_request_model()(**arguments)

            # Validate step field size
            step_content = request.step
            if step_content and len(step_content) > MCP_PROMPT_SIZE_LIMIT:
                from tools.models import ToolOutput

                error_output = ToolOutput(
                    status="resend_prompt",
                    content="Step instructions are too long. Please use shorter instructions and provide detailed context via file paths instead.",
                    content_type="text",
                    metadata={"prompt_size": len(step_content), "limit": MCP_PROMPT_SIZE_LIMIT},
                )
                raise ValueError(f"MCP_SIZE_CHECK:{error_output.model_dump_json()}")

            # Validate file paths for security
            try:
                path_error = self.validate_file_paths(request)
                if path_error:
                    from tools.models import ToolOutput

                    error_output = ToolOutput(
                        status="error",
                        content=path_error,
                        content_type="text",
                    )
                    logger.error("Path validation failed for %s: %s", self.get_name(), path_error)
                    raise ToolExecutionError(error_output.model_dump_json())
            except AttributeError:
                pass

            # Try to validate model availability early
            try:
                model_name, model_context = self._resolve_model_context(arguments, request)
                self._current_model_name = model_name
                self._model_context = model_context
            except ValueError as e:
                logger.debug(f"Early model validation failed, deferring to later: {e}")
                self._current_model_name = None
                self._model_context = None

            # Handle continuation
            continuation_id = request.continuation_id

            # Restore workflow state on continuation
            if continuation_id:
                from utils.conversation_memory import get_thread

                thread = get_thread(continuation_id)
                if thread and thread.turns:
                    for turn in reversed(thread.turns):
                        if turn.role == "assistant" and turn.tool_name == self.get_name() and turn.model_metadata:
                            state = turn.model_metadata
                            if isinstance(state, dict) and "work_history" in state:
                                self.work_history = state.get("work_history", [])
                                self.initial_request = state.get("initial_request")
                                self._reprocess_consolidated_findings()
                                logger.debug(
                                    f"[{self.get_name()}] Restored workflow state with {len(self.work_history)} history items"
                                )
                                break

            # Adjust total steps if needed
            if request.step_number > request.total_steps:
                request.total_steps = request.step_number

            # Create thread for first step
            if not continuation_id and request.step_number == 1:
                clean_args = {k: v for k, v in arguments.items() if k not in ["_model_context", "_resolved_model_name"]}
                continuation_id = create_thread(self.get_name(), clean_args)
                self.initial_request = request.step
                self.store_initial_issue(request.step)

            # Process work step
            step_data = self.prepare_step_data(request)

            # Store in history
            self.work_history.append(step_data)

            # Update consolidated findings
            self._update_consolidated_findings(step_data)

            # Handle file context appropriately based on workflow phase
            self._handle_workflow_file_context(request, arguments)

            # Build response with tool-specific customization
            response_data = self.build_base_response(request, continuation_id)

            # If work is complete, handle completion logic
            if not request.next_step_required:
                response_data = await self.handle_work_completion(response_data, request, arguments)
            else:
                response_data = self.handle_work_continuation(response_data, request)

            # Allow tools to customize the final response
            response_data = self.customize_workflow_response(response_data, request)

            # Add metadata
            self._add_workflow_metadata(response_data, arguments)

            # Store in conversation memory
            if continuation_id:
                self.store_conversation_turn(continuation_id, response_data, request)

            return [TextContent(type="text", text=json.dumps(response_data, indent=2, ensure_ascii=False))]

        except ToolExecutionError:
            raise
        except Exception as e:
            if str(e).startswith("MCP_SIZE_CHECK:"):
                payload = str(e)[len("MCP_SIZE_CHECK:") :]
                raise ToolExecutionError(payload)

            logger.error(f"Error in {self.get_name()} work: {e}", exc_info=True)
            error_data = {
                "status": f"{self.get_name()}_failed",
                "error": str(e),
                "step_number": arguments.get("step_number", 0),
            }

            self._add_workflow_metadata(error_data, arguments)

            raise ToolExecutionError(json.dumps(error_data, indent=2, ensure_ascii=False)) from e

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        """Execute the stateful tool - validates arguments and delegates to execute_workflow."""
        try:
            if not arguments:
                error_data = {"status": "error", "content": "No arguments provided"}
                error_data["metadata"] = {"tool_name": self.get_name()}
                raise ToolExecutionError(json.dumps(error_data, ensure_ascii=False))

            return await self.execute_workflow(arguments)

        except ToolExecutionError:
            raise
        except Exception as e:
            logger.error(f"Error in {self.get_name()} tool execution: {e}", exc_info=True)
            error_data = {
                "status": "error",
                "content": f"Error in {self.get_name()}: {str(e)}",
            }
            self._add_workflow_metadata(error_data, arguments)
            raise ToolExecutionError(json.dumps(error_data, ensure_ascii=False)) from e

    # ================================================================================
    # Step Data and Response Building
    # ================================================================================

    def prepare_step_data(self, request) -> dict:
        """Prepare step data from request. Tools can override to customize field mapping."""
        step_data = {
            "step": request.step,
            "step_number": request.step_number,
            "findings": request.findings,
            "files_checked": self.get_request_files_checked(request),
            "relevant_files": self.get_request_relevant_files(request),
            "relevant_context": self.get_request_relevant_context(request),
            "issues_found": self.get_request_issues_found(request),
            "confidence": self.get_request_confidence(request),
            "hypothesis": self.get_request_hypothesis(request),
            "images": self.get_request_images(request),
        }
        return step_data

    def build_base_response(self, request, continuation_id: str = None) -> dict:
        """Build the base response structure. Tools can override for custom response fields."""
        response_data = {
            "status": f"{self.get_name()}_in_progress",
            "step_number": request.step_number,
            "total_steps": request.total_steps,
            "next_step_required": request.next_step_required,
            f"{self.get_name()}_status": {
                "files_checked": len(self.consolidated_findings.files_checked),
                "relevant_files": len(self.consolidated_findings.relevant_files),
                "relevant_context": len(self.consolidated_findings.relevant_context),
                "issues_found": len(self.consolidated_findings.issues_found),
                "images_collected": len(self.consolidated_findings.images),
                "current_confidence": self.get_request_confidence(request),
            },
        }

        if continuation_id:
            response_data["continuation_id"] = continuation_id

        embedded_content = self.get_embedded_file_content()
        reference_note = self.get_file_reference_note()
        processed_files = self.get_actually_processed_files()

        logger.debug(
            f"[WORKFLOW_FILES] {self.get_name()}: Building response - has embedded_content: {bool(embedded_content)}, has reference_note: {bool(reference_note)}"
        )

        if embedded_content:
            logger.debug(f"[WORKFLOW_FILES] {self.get_name()}: Adding fully_embedded file context")
            response_data["file_context"] = {
                "type": "fully_embedded",
                "files_embedded": len(processed_files),
                "context_optimization": "Full file content embedded for expert analysis",
            }
        elif reference_note:
            logger.debug(f"[WORKFLOW_FILES] {self.get_name()}: Adding reference_only file context")
            response_data["file_context"] = {
                "type": "reference_only",
                "note": reference_note,
                "context_optimization": "Files referenced but not embedded to preserve the context window",
            }

        return response_data

    async def handle_work_completion(self, response_data: dict, request, arguments: dict) -> dict:
        """Handle work completion logic - expert analysis decision and response building."""
        response_data[f"{self.get_name()}_complete"] = True

        if self.should_skip_expert_analysis(request, self.consolidated_findings):
            completion_response = self.handle_completion_without_expert_analysis(request, self.consolidated_findings)
            response_data.update(completion_response)
        elif self.requires_expert_analysis() and self.should_call_expert_analysis(self.consolidated_findings, request):
            response_data["status"] = "calling_expert_analysis"

            expert_analysis = await self._call_expert_analysis(arguments, request)
            response_data["expert_analysis"] = expert_analysis

            if isinstance(expert_analysis, dict) and expert_analysis.get("status") in [
                "files_required_to_continue",
                "investigation_paused",
                "refactoring_paused",
            ]:
                special_status = expert_analysis["status"]
                response_data["status"] = special_status
                response_data["content"] = expert_analysis.get(
                    "raw_analysis", json.dumps(expert_analysis, ensure_ascii=False)
                )
                del response_data["expert_analysis"]

                if special_status == "files_required_to_continue":
                    response_data["next_steps"] = "Provide the requested files and continue the analysis."
                else:
                    response_data["next_steps"] = expert_analysis.get(
                        "next_steps", "Continue based on expert analysis."
                    )
            elif isinstance(expert_analysis, dict) and expert_analysis.get("status") == "analysis_error":
                response_data["status"] = "error"
                response_data["content"] = expert_analysis.get("error", "Expert analysis failed")
                response_data["content_type"] = "text"
                del response_data["expert_analysis"]
            else:
                response_data["next_steps"] = self.get_completion_next_steps_message(expert_analysis_used=True)

                expert_guidance = self.get_expert_analysis_guidance()
                if expert_guidance:
                    response_data["important_considerations"] = expert_guidance

            work_summary = self._prepare_work_summary()
            response_data[f"complete_{self.get_name()}"] = {
                "initial_request": self.get_initial_request(request.step),
                "steps_taken": len(self.work_history),
                "files_examined": list(self.consolidated_findings.files_checked),
                "relevant_files": list(self.consolidated_findings.relevant_files),
                "relevant_context": list(self.consolidated_findings.relevant_context),
                "issues_found": self.consolidated_findings.issues_found,
                "work_summary": work_summary,
            }
        else:
            if not self.requires_expert_analysis():
                response_data["status"] = f"{self.get_name()}_complete"
                response_data["next_steps"] = (
                    f"{self.get_name().capitalize()} work complete. Present results to the user."
                )
            else:
                response_data["status"] = "local_work_complete"
                response_data["next_steps"] = (
                    f"Local {self.get_name()} complete with sufficient confidence. Present findings "
                    "and recommendations to the user based on the work results."
                )

        return response_data

    def handle_work_continuation(self, response_data: dict, request) -> dict:
        """Handle work continuation - force pause and provide guidance."""
        response_data["status"] = f"pause_for_{self.get_name()}"
        response_data[f"{self.get_name()}_required"] = True

        required_actions = self.get_required_actions(
            request.step_number, self.get_request_confidence(request), request.findings, request.total_steps, request
        )
        response_data["required_actions"] = required_actions

        response_data["next_steps"] = self.get_step_guidance_message(request)

        return response_data

    def handle_completion_without_expert_analysis(self, request, consolidated_findings) -> dict:
        """Handle completion when skipping expert analysis."""
        work_summary = self.prepare_work_summary()
        continuation_id = self.get_request_continuation_id(request)

        response_data = {
            "status": self.get_completion_status(),
            f"complete_{self.get_name()}": {
                "initial_request": self.get_initial_request(request.step),
                "steps_taken": len(consolidated_findings.findings),
                "files_examined": list(consolidated_findings.files_checked),
                "relevant_files": list(consolidated_findings.relevant_files),
                "relevant_context": list(consolidated_findings.relevant_context),
                "work_summary": work_summary,
                "final_analysis": self.get_final_analysis_from_request(request),
                "confidence_level": self.get_confidence_level(request),
            },
            "next_steps": self.get_completion_message(),
            "skip_expert_analysis": True,
            "expert_analysis": {
                "status": self.get_skip_expert_analysis_status(),
                "reason": self.get_skip_reason(),
            },
        }

        if continuation_id:
            response_data["continuation_id"] = continuation_id

        return response_data

    def customize_workflow_response(self, response_data: dict, request) -> dict:
        """Allow tools to customize the workflow response before returning."""
        if not response_data.get("file_context"):
            embedded_content = self.get_embedded_file_content()
            reference_note = self.get_file_reference_note()
            processed_files = self.get_actually_processed_files()

            if embedded_content:
                response_data["file_context"] = {
                    "type": "fully_embedded",
                    "files_embedded": len(processed_files),
                    "context_optimization": "Full file content embedded for expert analysis",
                }
            elif reference_note:
                response_data["file_context"] = {
                    "type": "reference_only",
                    "note": reference_note,
                    "context_optimization": "Files referenced but not embedded to preserve the context window",
                }

        return response_data

    # ================================================================================
    # Conversation Memory and Metadata
    # ================================================================================

    def store_conversation_turn(self, continuation_id: str, response_data: dict, request):
        """Store the conversation turn. Tools can override for custom memory storage."""
        clean_content = self._extract_clean_workflow_content_for_history(response_data)

        workflow_state = {"work_history": self.work_history, "initial_request": getattr(self, "initial_request", None)}

        add_turn(
            thread_id=continuation_id,
            role="assistant",
            content=clean_content,
            tool_name=self.get_name(),
            files=self.get_request_relevant_files(request),
            images=self.get_request_images(request),
            model_metadata=workflow_state,
        )

    def _add_workflow_metadata(self, response_data: dict, arguments: dict[str, Any]) -> None:
        """Add metadata (provider_used and model_used) to workflow response."""
        try:
            resolved_model_name = arguments.get("_resolved_model_name")
            model_context = arguments.get("_model_context")

            if resolved_model_name and model_context:
                provider = model_context.provider
                provider_name = provider.get_provider_type().value if provider else "unknown"

                metadata = {
                    "tool_name": self.get_name(),
                    "model_used": resolved_model_name,
                    "provider_used": provider_name,
                }

                if "metadata" not in response_data:
                    response_data["metadata"] = {}
                response_data["metadata"].update(metadata)

                logger.debug(
                    f"[WORKFLOW_METADATA] {self.get_name()}: Added metadata - "
                    f"model: {resolved_model_name}, provider: {provider_name}"
                )
            else:
                request = self.get_workflow_request_model()(**arguments)
                model_name = self.get_request_model_name(request)

                metadata = {
                    "tool_name": self.get_name(),
                    "model_used": model_name,
                    "provider_used": "unknown",
                }

                if "metadata" not in response_data:
                    response_data["metadata"] = {}
                response_data["metadata"].update(metadata)

                logger.debug(
                    f"[WORKFLOW_METADATA] {self.get_name()}: Added fallback metadata - "
                    f"model: {model_name}, provider: unknown"
                )

        except Exception as e:
            logger.warning(f"[WORKFLOW_METADATA] {self.get_name()}: Failed to add metadata: {e}")
            response_data["metadata"] = {"tool_name": self.get_name()}

    def _extract_clean_workflow_content_for_history(self, response_data: dict) -> str:
        """Extract clean content from workflow response suitable for conversation history."""
        clean_data = {}

        if "content" in response_data:
            clean_data["content"] = response_data["content"]

        if "expert_analysis" in response_data:
            expert_analysis = response_data["expert_analysis"]
            if isinstance(expert_analysis, dict):
                clean_expert = {}
                if "raw_analysis" in expert_analysis:
                    clean_expert["analysis"] = expert_analysis["raw_analysis"]
                elif "content" in expert_analysis:
                    clean_expert["analysis"] = expert_analysis["content"]
                if clean_expert:
                    clean_data["expert_analysis"] = clean_expert

        if "complete_analysis" in response_data:
            complete_analysis = response_data["complete_analysis"]
            if isinstance(complete_analysis, dict):
                clean_complete = {}
                for key in ["findings", "issues_found", "relevant_context", "insights"]:
                    if key in complete_analysis:
                        clean_complete[key] = complete_analysis[key]
                if clean_complete:
                    clean_data["analysis_summary"] = clean_complete

        if "step_number" in response_data:
            clean_data["step_info"] = {
                "step": response_data.get("step", ""),
                "step_number": response_data.get("step_number", 1),
                "total_steps": response_data.get("total_steps", 1),
            }

        return json.dumps(clean_data, indent=2, ensure_ascii=False)

    # ================================================================================
    # Internal State Management
    # ================================================================================

    def _update_consolidated_findings(self, step_data: dict):
        """Update consolidated findings with new step data."""
        self.consolidated_findings.files_checked.update(step_data.get("files_checked", []))
        self.consolidated_findings.relevant_files.update(step_data.get("relevant_files", []))
        self.consolidated_findings.relevant_context.update(step_data.get("relevant_context", []))
        self.consolidated_findings.findings.append(f"Step {step_data['step_number']}: {step_data['findings']}")
        if step_data.get("hypothesis"):
            self.consolidated_findings.hypotheses.append(
                {
                    "step": step_data["step_number"],
                    "hypothesis": step_data["hypothesis"],
                    "confidence": step_data["confidence"],
                }
            )
        if step_data.get("issues_found"):
            self.consolidated_findings.issues_found.extend(step_data["issues_found"])
        if step_data.get("images"):
            self.consolidated_findings.images.extend(step_data["images"])
        if step_data.get("confidence"):
            self.consolidated_findings.confidence = step_data["confidence"]

    def _reprocess_consolidated_findings(self):
        """Reprocess consolidated findings after backtracking."""
        self.consolidated_findings = ConsolidatedFindings()
        for step in self.work_history:
            self._update_consolidated_findings(step)

    def _prepare_work_summary(self) -> str:
        """Prepare a comprehensive summary of the work."""
        summary_parts = [
            f"=== {self.get_name().upper()} WORK SUMMARY ===",
            f"Total steps: {len(self.work_history)}",
            f"Files examined: {len(self.consolidated_findings.files_checked)}",
            f"Relevant files identified: {len(self.consolidated_findings.relevant_files)}",
            f"Methods/functions involved: {len(self.consolidated_findings.relevant_context)}",
            f"Issues found: {len(self.consolidated_findings.issues_found)}",
            "",
            "=== WORK PROGRESSION ===",
        ]

        for finding in self.consolidated_findings.findings:
            summary_parts.append(finding)

        if self.consolidated_findings.hypotheses:
            summary_parts.extend(
                [
                    "",
                    "=== HYPOTHESIS EVOLUTION ===",
                ]
            )
            for hyp in self.consolidated_findings.hypotheses:
                summary_parts.append(f"Step {hyp['step']} ({hyp['confidence']} confidence): {hyp['hypothesis']}")

        if self.consolidated_findings.issues_found:
            summary_parts.extend(
                [
                    "",
                    "=== ISSUES IDENTIFIED ===",
                ]
            )
            for issue in self.consolidated_findings.issues_found:
                severity = issue.get("severity", "unknown")
                description = issue.get("description", "No description")
                summary_parts.append(f"[{severity.upper()}] {description}")

        return "\n".join(summary_parts)

    def _process_work_step(self, step_data: dict):
        """Process a single work step and update internal state."""
        self.work_history.append(step_data)
        self._update_consolidated_findings(step_data)

    # ================================================================================
    # Expert Analysis
    # ================================================================================

    async def _call_expert_analysis(self, arguments: dict, request) -> dict:
        """Call external model for expert analysis."""
        try:
            if not self._model_context:
                try:
                    model_name, model_context = self._resolve_model_context(arguments, request)
                    self._model_context = model_context
                    self._current_model_name = model_name
                except Exception as e:
                    logger.error(f"Failed to resolve model context for expert analysis: {e}")
                    model_name = self.get_request_model_name(request)
                    from utils.model_context import ModelContext

                    model_context = ModelContext(model_name)
                    self._model_context = model_context
                    self._current_model_name = model_name
            else:
                model_name = self._current_model_name

            provider = self._model_context.provider

            expert_context = self.prepare_expert_analysis_context(self.consolidated_findings)

            if self.should_include_files_in_expert_prompt():
                file_content = self._prepare_files_for_expert_analysis()
                if file_content:
                    expert_context = self._add_files_to_expert_context(expert_context, file_content)

            base_system_prompt = self.get_system_prompt()
            capability_augmented_prompt = self._augment_system_prompt_with_capabilities(
                base_system_prompt, getattr(self._model_context, "capabilities", None)
            )
            language_instruction = self.get_language_instruction()
            system_prompt = language_instruction + capability_augmented_prompt

            if self.should_embed_system_prompt():
                prompt = f"{system_prompt}\n\n{expert_context}\n\n{self.get_expert_analysis_instruction()}"
                system_prompt = ""
            else:
                prompt = expert_context

            validated_temperature, temp_warnings = self.get_validated_temperature(request, self._model_context)

            for warning in temp_warnings:
                logger.warning(warning)

            model_response = provider.generate_content(
                prompt=prompt,
                model_name=model_name,
                system_prompt=system_prompt,
                temperature=validated_temperature,
                thinking_mode=self.get_request_thinking_mode(request),
                images=list(set(self.consolidated_findings.images)) if self.consolidated_findings.images else None,
            )

            if model_response.content:
                content = model_response.content.strip()

                if "```json" in content or "```" in content:
                    json_match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
                    if json_match:
                        content = json_match.group(1).strip()

                try:
                    analysis_result = json.loads(content)
                    return analysis_result
                except json.JSONDecodeError as e:
                    logger.info(
                        f"[{self.get_name()}] Expert analysis returned non-JSON response (this is OK for smaller models). "
                        f"Parse error: {str(e)}. Response length: {len(model_response.content)} chars."
                    )
                    logger.debug(f"First 500 chars of response: {model_response.content[:500]!r}")

                    return {
                        "status": "analysis_complete",
                        "raw_analysis": model_response.content,
                        "format": "text",
                        "note": "Analysis provided in plain text format",
                    }
            else:
                return {"error": "No response from model", "status": "empty_response"}

        except Exception as e:
            logger.error(f"Error calling expert analysis: {e}", exc_info=True)
            return {"error": str(e), "status": "analysis_error"}

    # ================================================================================
    # Default implementations for BaseTool abstract methods
    # ================================================================================

    async def prepare_prompt(self, request) -> str:
        """Workflow tools handle their prompts internally during workflow execution."""
        return ""

    def format_response(self, response: str, request, model_info=None):
        """Workflow tools handle their own response formatting."""
        return response
