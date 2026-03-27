"""
Base models for PAL MCP tools.

This module contains the shared Pydantic models used across all tools,
extracted to avoid circular imports and promote code reuse.

Key Models:
- ToolRequest: Base request model for all tools
- WorkflowRequest: Extended request model for workflow-based tools
- ConsolidatedFindings: Model for tracking workflow progress
"""

import logging
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from typing_extensions import NotRequired, TypedDict

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


class ToolRequest(TypedDict, total=False):
    """
    Base request model for all PAL MCP tools.

    Converted from Pydantic BaseModel to TypedDict in v10. The MCP JSON Schema
    handles input validation at the transport boundary, so runtime Pydantic
    validation is unnecessary for tools that don't use model_validator.

    Tool-specific request models that need cross-field validation should use
    Pydantic. Simple tools should use TypedDict.
    """

    model: NotRequired[Optional[str]]
    temperature: NotRequired[Optional[float]]
    thinking_mode: NotRequired[Optional[str]]
    continuation_id: NotRequired[Optional[str]]
    images: NotRequired[Optional[list[str]]]


class BaseWorkflowRequest(BaseModel):
    """
    Minimal base request model for workflow tools.

    This provides only the essential fields that ALL workflow tools need,
    allowing for maximum flexibility in tool-specific implementations.
    Remains Pydantic because workflow requests use field validators.
    """

    # Common fields (replicated from ToolRequest TypedDict for Pydantic compatibility)
    model: Optional[str] = Field(None, description=COMMON_FIELD_DESCRIPTIONS["model"])
    temperature: Optional[float] = Field(None, ge=0.0, le=1.0, description=COMMON_FIELD_DESCRIPTIONS["temperature"])
    thinking_mode: Optional[str] = Field(None, description=COMMON_FIELD_DESCRIPTIONS["thinking_mode"])
    continuation_id: Optional[str] = Field(None, description=COMMON_FIELD_DESCRIPTIONS["continuation_id"])
    images: Optional[list[str]] = Field(None, description=COMMON_FIELD_DESCRIPTIONS["images"])

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


# Tool-specific field descriptions are now declared in each tool file
# This keeps concerns separated and makes each tool self-contained
