"""
Base models for PAL MCP tools.

This module contains the shared Pydantic models used across all tools,
extracted to avoid circular imports and promote code reuse.

Key Models:
- ToolRequest: Base request model for all tools
- WorkflowRequest: Extended request model for workflow-based tools
- StandardWorkflowRequest: Common base for most workflow tool requests
- ConsolidatedFindings: Model for tracking workflow progress
"""

import logging
from typing import ClassVar, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)


# Shared field descriptions to avoid duplication
COMMON_FIELD_DESCRIPTIONS = {
    "model": "Model to run. Supply a name if requested by the user or stay in auto mode. When in auto mode, use `listmodels` tool for model discovery.",
    "temperature": "0 = deterministic · 1 = creative.",
    "thinking_mode": "Reasoning depth: minimal, low, medium, high, or max.",
    "continuation_id": (
        "Unique thread continuation ID for multi-turn conversations. Works across different tools. "
        "ALWAYS reuse the last continuation_id you were given—this preserves full conversation context, "
        "files, and findings so the agent can resume seamlessly."
    ),
    "images": "Optional absolute image paths or base64 blobs for visual context.",
    "absolute_file_paths": "Full paths to relevant code",
}

# Workflow-specific field descriptions
WORKFLOW_FIELD_DESCRIPTIONS = {
    "step": "Current work step content and findings from your overall work",
    "step_number": "Current step number in work sequence (starts at 1)",
    "total_steps": "Estimated total steps needed to complete work",
    "next_step_required": "Whether another work step is needed. When false, aim to reduce total_steps to match step_number to avoid mismatch.",
    "findings": "Important findings, evidence and insights discovered in this step",
    "files_checked": "List of files examined during this work step",
    "relevant_files": "Files identified as relevant to issue/goal (FULL absolute paths to real files/folders - DO NOT SHORTEN)",
    "relevant_context": "Methods/functions identified as involved in the issue",
    "issues_found": "Issues identified with severity levels during work",
    "confidence": (
        "Confidence level: exploring (just starting), low (early investigation), "
        "medium (some evidence), high (strong evidence), very_high (comprehensive understanding), "
        "almost_certain (near complete confidence), certain (100% confidence locally - no external validation needed)"
    ),
    "hypothesis": "Current theory about issue/goal based on work",
    "use_assistant_model": (
        "Use assistant model for expert analysis after workflow steps. "
        "False skips expert analysis, relies solely on your personal investigation. "
        "Defaults to True for comprehensive validation."
    ),
}


class ToolRequest(BaseModel):
    """
    Base request model for all PAL MCP tools.

    This model defines common fields that all tools accept, including
    model selection, temperature control, and conversation threading.
    Tool-specific request models should inherit from this class.
    """

    # Model configuration
    model: Optional[str] = Field(None, description=COMMON_FIELD_DESCRIPTIONS["model"])
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0, description=COMMON_FIELD_DESCRIPTIONS["temperature"])
    thinking_mode: Optional[str] = Field(None, description=COMMON_FIELD_DESCRIPTIONS["thinking_mode"])

    # Conversation support
    continuation_id: Optional[str] = Field(None, description=COMMON_FIELD_DESCRIPTIONS["continuation_id"])

    # Visual context
    images: Optional[list[str]] = Field(None, description=COMMON_FIELD_DESCRIPTIONS["images"])


class BaseWorkflowRequest(ToolRequest):
    """
    Minimal base request model for workflow tools.

    This provides only the essential fields that ALL workflow tools need,
    allowing for maximum flexibility in tool-specific implementations.
    """

    # Core workflow fields that ALL workflow tools need
    step: str = Field(..., description=WORKFLOW_FIELD_DESCRIPTIONS["step"])
    step_number: int = Field(..., ge=1, description=WORKFLOW_FIELD_DESCRIPTIONS["step_number"])
    total_steps: int = Field(..., ge=1, description=WORKFLOW_FIELD_DESCRIPTIONS["total_steps"])
    next_step_required: bool = Field(..., description=WORKFLOW_FIELD_DESCRIPTIONS["next_step_required"])


class WorkflowRequest(BaseWorkflowRequest):
    """
    Extended request model for workflow-based tools.

    This model extends ToolRequest with fields specific to the workflow
    pattern, where tools perform multi-step work with forced pauses between steps.

    Used by: debug, precommit, codereview, refactor, thinkdeep, analyze
    """

    # Required workflow fields
    step: str = Field(..., description=WORKFLOW_FIELD_DESCRIPTIONS["step"])
    step_number: int = Field(..., ge=1, description=WORKFLOW_FIELD_DESCRIPTIONS["step_number"])
    total_steps: int = Field(..., ge=1, description=WORKFLOW_FIELD_DESCRIPTIONS["total_steps"])
    next_step_required: bool = Field(..., description=WORKFLOW_FIELD_DESCRIPTIONS["next_step_required"])

    # Work tracking fields
    findings: str = Field(..., description=WORKFLOW_FIELD_DESCRIPTIONS["findings"])
    files_checked: list[str] = Field(default_factory=list, description=WORKFLOW_FIELD_DESCRIPTIONS["files_checked"])
    relevant_files: list[str] = Field(default_factory=list, description=WORKFLOW_FIELD_DESCRIPTIONS["relevant_files"])
    relevant_context: list[str] = Field(
        default_factory=list, description=WORKFLOW_FIELD_DESCRIPTIONS["relevant_context"]
    )
    issues_found: list[dict] = Field(default_factory=list, description=WORKFLOW_FIELD_DESCRIPTIONS["issues_found"])
    confidence: str = Field("low", description=WORKFLOW_FIELD_DESCRIPTIONS["confidence"])

    # Optional workflow fields
    hypothesis: Optional[str] = Field(None, description=WORKFLOW_FIELD_DESCRIPTIONS["hypothesis"])
    use_assistant_model: Optional[bool] = Field(True, description=WORKFLOW_FIELD_DESCRIPTIONS["use_assistant_model"])

    @field_validator("files_checked", "relevant_files", "relevant_context", mode="before")
    @classmethod
    def convert_string_to_list(cls, v):
        """Convert string inputs to empty lists to handle malformed inputs gracefully."""
        if isinstance(v, str):
            logger.warning(f"Field received string '{v}' instead of list, converting to empty list")
            return []
        return v


class ConsolidatedFindings(BaseModel):
    """
    Model for tracking consolidated findings across workflow steps.

    This model accumulates findings, files, methods, and issues
    discovered during multi-step work. It's used by
    BaseWorkflowMixin to track progress across workflow steps.
    """

    files_checked: set[str] = Field(default_factory=set, description="All files examined across all steps")
    relevant_files: set[str] = Field(
        default_factory=set,
        description="Subset of files_checked identified as relevant for work at hand",
    )
    relevant_context: set[str] = Field(
        default_factory=set, description="All methods/functions identified during overall work"
    )
    findings: list[str] = Field(default_factory=list, description="Chronological findings from each work step")
    hypotheses: list[dict] = Field(default_factory=list, description="Evolution of hypotheses across steps")
    issues_found: list[dict] = Field(default_factory=list, description="All issues with severity levels")
    images: list[str] = Field(default_factory=list, description="Images collected during work")
    confidence: str = Field("low", description="Latest confidence level from steps")


def build_workflow_descriptions(activity: str) -> dict[str, str]:
    """Build standard workflow field descriptions parameterized by activity name.

    Generates a dictionary of field descriptions for the common workflow fields,
    customised with the tool's activity name. Tools merge this with their own
    tool-specific entries and may override any shared key.

    Args:
        activity: The tool's primary activity (e.g., "review", "investigation",
                  "analysis", "tracing", "audit").

    Returns:
        Dictionary mapping field names to description strings.
    """
    return {
        "step_number": f"Current {activity} step (starts at 1). Each step should build on the last.",
        "total_steps": f"Estimated total {activity} steps needed. Adjust as new findings emerge.",
        "next_step_required": (
            f"True if another {activity} step follows; False when {activity} is complete "
            f"and ready for expert validation."
        ),
        "findings": f"Capture findings from this {activity} step; update prior findings as needed.",
        "files_checked": "Absolute paths of every file examined, including those ruled out.",
        "relevant_files": (
            "Files directly relevant to findings (absolute paths). " "Must be absolute full non-abbreviated paths."
        ),
        "relevant_context": ("Key functions/methods central to findings " "(e.g. 'Class.method' or 'function_name')."),
        "issues_found": "Issues with severity (critical/high/medium/low) and descriptions.",
        "confidence": (
            "Confidence: exploring/low/medium/high/very_high/almost_certain/certain. "
            "CRITICAL: 'certain' PREVENTS external validation—use only when 100% complete."
        ),
        "images": "Optional absolute paths to diagrams or screenshots for additional context.",
    }


class StandardWorkflowRequest(WorkflowRequest):
    """Common base for most workflow tool request models.

    Provides two shared patterns that nearly every workflow tool repeats:

    1. **Excluded fields** – ``temperature`` and ``thinking_mode`` are excluded
       from the JSON schema by default (most workflow tools don't expose them).
    2. **Step-1 validation** – subclasses can set ``_step_one_required_field``
       and ``_step_one_error_message`` class variables to automatically validate
       that a specific field is present on the first step, eliminating
       per-tool ``validate_step_one_requirements`` boilerplate.

    Example::

        class MyToolRequest(StandardWorkflowRequest):
            _step_one_required_field = "relevant_files"
            _step_one_error_message = "Step 1 requires files to analyse"
            # ... tool-specific fields only ...
    """

    _step_one_required_field: ClassVar[Optional[str]] = None
    _step_one_error_message: ClassVar[Optional[str]] = None

    # Most workflow tools exclude these from the schema
    temperature: Optional[float] = Field(default=None, exclude=True)
    thinking_mode: Optional[str] = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def validate_step_one_requirements(self):
        """Validate that the required field is present on step 1."""
        field = self._step_one_required_field
        if field and self.step_number == 1:
            value = getattr(self, field, None)
            if not value:
                raise ValueError(self._step_one_error_message or f"Step 1 requires '{field}' field")
        return self
