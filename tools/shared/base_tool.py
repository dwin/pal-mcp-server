"""
Core Tool Infrastructure for PAL MCP Tools

This module provides the fundamental base class for all tools:
- BaseTool: Abstract base class defining the tool interface

The BaseTool class defines the core contract that tools must implement and provides
common functionality for request validation, error handling, model management,
conversation handling, file processing, and response formatting.
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Optional

from mcp.types import TextContent

if TYPE_CHECKING:
    from providers.shared import ModelCapabilities

from config import MCP_PROMPT_SIZE_LIMIT
from providers import ModelProvider, ModelProviderRegistry
from shared_types import ToolModelCategory
from tools.shared import request_helpers as req
from tools.shared.exceptions import ToolExecutionError
from utils import estimate_tokens
from utils.conversation_memory import (
    ConversationTurn,
    get_conversation_file_list,
    get_thread,
)
from utils.env import get_env
from utils.file_utils import read_file_content, read_files

# Import models from tools.models for compatibility
try:
    from tools.models import SPECIAL_STATUS_MODELS, ContinuationOffer, ToolOutput
except ImportError:
    # Fallback in case models haven't been set up yet
    SPECIAL_STATUS_MODELS = {}
    ContinuationOffer = None
    ToolOutput = None

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """
    Abstract base class for all PAL MCP tools.

    This class defines the interface that all tools must implement and provides
    common functionality for request handling, model creation, and response formatting.

    CONVERSATION-AWARE FILE PROCESSING:
    This base class implements the sophisticated dual prioritization strategy for
    conversation-aware file handling across all tools:

    1. FILE DEDUPLICATION WITH NEWEST-FIRST PRIORITY:
       - When same file appears in multiple conversation turns, newest reference wins
       - Prevents redundant file embedding while preserving most recent file state
       - Cross-tool file tracking ensures consistent behavior across analyze → codereview → debug

    2. CONVERSATION CONTEXT INTEGRATION:
       - All tools receive enhanced prompts with conversation history via reconstruct_thread_context()
       - File references from previous turns are preserved and accessible
       - Cross-tool knowledge transfer maintains full context without manual file re-specification

    3. TOKEN-AWARE FILE EMBEDDING:
       - Respects model-specific token allocation budgets from ModelContext
       - Prioritizes conversation history, then newest files, then remaining content
       - Graceful degradation when token limits are approached

    4. STATELESS-TO-STATEFUL BRIDGING:
       - Tools operate on stateless MCP requests but access full conversation state
       - Conversation memory automatically injected via continuation_id parameter
       - Enables natural AI-to-AI collaboration across tool boundaries

    To create a new tool:
    1. Create a new class that inherits from BaseTool
    2. Implement all abstract methods
    3. Define a request model that inherits from ToolRequest
    4. Register the tool in server.py's TOOLS dictionary
    """

    # Common field definitions that tools can reuse.
    # These are defined as a _ClassProperty so they work with both
    # BaseTool.FILES_FIELD (class-level) and self.FILES_FIELD (instance-level)
    # while avoiding circular imports via lazy evaluation.
    class _ClassProperty:
        """Descriptor that works as a property on both the class and instances."""

        def __init__(self, func):
            self._func = func

        def __get__(self, obj, objtype=None):
            return self._func()

    @_ClassProperty
    def FILES_FIELD():
        from tools.shared.schema_builders import SchemaBuilder

        return SchemaBuilder.SIMPLE_FIELD_SCHEMAS["absolute_file_paths"]

    @_ClassProperty
    def IMAGES_FIELD():
        from tools.shared.schema_builders import SchemaBuilder

        return SchemaBuilder.COMMON_FIELD_SCHEMAS["images"]

    # Class-level cache for OpenRouter registry to avoid multiple loads
    _openrouter_registry_cache = None
    _custom_registry_cache = None

    @classmethod
    def _get_openrouter_registry(cls):
        """Get cached OpenRouter registry instance, creating if needed."""
        # Use BaseTool class directly to ensure cache is shared across all subclasses
        if BaseTool._openrouter_registry_cache is None:
            from providers.registries.openrouter import OpenRouterModelRegistry

            BaseTool._openrouter_registry_cache = OpenRouterModelRegistry()
            logger.debug("Created cached OpenRouter registry instance")
        return BaseTool._openrouter_registry_cache

    @classmethod
    def _get_custom_registry(cls):
        """Get cached custom-endpoint registry instance."""
        if BaseTool._custom_registry_cache is None:
            from providers.registries.custom import CustomEndpointModelRegistry

            BaseTool._custom_registry_cache = CustomEndpointModelRegistry()
            logger.debug("Created cached Custom registry instance")
        return BaseTool._custom_registry_cache

    def __init__(self):
        # Cache tool metadata at initialization to avoid repeated calls
        self.name = self.get_name()
        self.description = self.get_description()
        self.default_temperature = self.get_default_temperature()
        # Tool initialization complete

    @abstractmethod
    def get_name(self) -> str:
        """
        Return the unique name identifier for this tool.

        This name is used by MCP clients to invoke the tool and must be
        unique across all registered tools.

        Returns:
            str: The tool's unique name (e.g., "review_code", "analyze")
        """
        pass

    @abstractmethod
    def get_description(self) -> str:
        """
        Return a detailed description of what this tool does.

        This description is shown to MCP clients (like Claude / Codex / Gemini) to help them
        understand when and how to use the tool. It should be comprehensive
        and include trigger phrases.

        Returns:
            str: Detailed tool description with usage examples
        """
        pass

    def get_input_schema(self) -> dict[str, Any]:
        """
        Return the JSON Schema that defines this tool's parameters.

        This schema is used by MCP clients to validate inputs before
        sending requests. It should match the tool's request model.

        The default implementation uses SchemaBuilder to combine tool-specific
        fields from get_tool_fields() with common fields. Workflow tools
        typically override this method entirely.

        Returns:
            Dict[str, Any]: JSON Schema object defining required and optional parameters
        """
        from tools.shared.schema_builders import SchemaBuilder

        required_fields = list(self.get_required_fields())
        return SchemaBuilder.build_schema(
            tool_specific_fields=self.get_tool_fields(),
            required_fields=required_fields,
            model_field_schema=self.get_model_field_schema(),
            auto_mode=self.is_effective_auto_mode(),
        )

    @abstractmethod
    def get_system_prompt(self) -> str:
        """
        Return the system prompt that configures the AI model's behavior.

        This prompt sets the context and instructions for how the model
        should approach the task. It's prepended to the user's request.

        Returns:
            str: System prompt with role definition and instructions
        """
        pass

    def get_capability_system_prompts(self, capabilities: Optional["ModelCapabilities"]) -> list[str]:
        """Return additional system prompt snippets gated on model capabilities.

        Subclasses can override this hook to append capability-specific
        instructions (for example, enabling code-generation exports when a
        model advertises support). The default implementation returns an empty
        list so no extra instructions are appended.

        Args:
            capabilities: The resolved capabilities for the active model.

        Returns:
            List of prompt fragments to append after the base system prompt.
        """

        return []

    def _augment_system_prompt_with_capabilities(
        self, base_prompt: str, capabilities: Optional["ModelCapabilities"]
    ) -> str:
        """Merge capability-driven prompt addenda with the base system prompt."""

        additions: list[str] = []
        if capabilities is not None:
            additions = [fragment.strip() for fragment in self.get_capability_system_prompts(capabilities) if fragment]

        if not additions:
            return base_prompt

        addition_text = "\n\n".join(additions)
        if not base_prompt:
            return addition_text

        suffix = "" if base_prompt.endswith("\n\n") else "\n\n"
        return f"{base_prompt}{suffix}{addition_text}"

    def get_annotations(self) -> Optional[dict[str, Any]]:
        """
        Return optional annotations for this tool.

        Annotations provide hints about tool behavior without being security-critical.
        They help MCP clients make better decisions about tool usage.

        All tools are read-only by default. They may call external AI models for
        analysis or conversation, but they don't write files or make system changes.
        Override this method if your tool needs different annotations.

        Returns:
            Optional[dict]: Dictionary with annotation fields like readOnlyHint, destructiveHint, etc.
        """
        return {"readOnlyHint": True}

    def requires_model(self) -> bool:
        """
        Return whether this tool requires AI model access.

        Tools that override execute() to do pure data processing (like planner)
        should return False to skip model resolution at the MCP boundary.

        Returns:
            bool: True if tool needs AI model access (default), False for data-only tools
        """
        return True

    def is_effective_auto_mode(self) -> bool:
        """
        Check if we're in effective auto mode for schema generation.

        This determines whether the model parameter should be required in the tool schema.
        Used at initialization time when schemas are generated.

        Returns:
            bool: True if model parameter should be required in the schema
        """
        from config import DEFAULT_MODEL
        from providers.registry import ModelProviderRegistry

        # Case 1: Explicit auto mode
        if DEFAULT_MODEL.lower() == "auto":
            return True

        # Case 2: Model not available (fallback to auto mode)
        if DEFAULT_MODEL.lower() != "auto":
            provider = ModelProviderRegistry.get_provider_for_model(DEFAULT_MODEL)
            if not provider:
                return True

        return False

    def _format_available_models_list(self) -> str:
        """Return a human-friendly list of available models or guidance when none found."""

        summaries, total, has_restrictions = self._get_ranked_model_summaries()
        if not summaries:
            return (
                "No models detected. Configure provider credentials or set DEFAULT_MODEL to a valid option. "
                "If the user requested a specific model, respond with this notice instead of substituting another model."
            )
        display = "; ".join(summaries)
        remainder = total - len(summaries)
        if remainder > 0:
            display = f"{display}; +{remainder} more (use the `listmodels` tool for the full roster)"
        return display

    @staticmethod
    def _format_context_window(tokens: int) -> Optional[str]:
        """Convert a raw context window into a short display string."""

        if not tokens or tokens <= 0:
            return None

        if tokens >= 1_000_000:
            if tokens % 1_000_000 == 0:
                return f"{tokens // 1_000_000}M ctx"
            return f"{tokens / 1_000_000:.1f}M ctx"

        if tokens >= 1_000:
            if tokens % 1_000 == 0:
                return f"{tokens // 1_000}K ctx"
            return f"{tokens / 1_000:.1f}K ctx"

        return f"{tokens} ctx"

    def _collect_ranked_capabilities(self) -> list[tuple[int, str, Any]]:
        """Gather available model capabilities sorted by capability rank."""

        from providers.registry import ModelProviderRegistry

        ranked: list[tuple[int, str, Any]] = []
        available = ModelProviderRegistry.get_available_models(respect_restrictions=True)

        for model_name, provider_type in available.items():
            provider = ModelProviderRegistry.get_provider(provider_type)
            if not provider:
                continue

            try:
                capabilities = provider.get_capabilities(model_name)
            except ValueError:
                continue

            rank = capabilities.get_effective_capability_rank()
            ranked.append((rank, model_name, capabilities))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        return ranked

    @staticmethod
    def _normalize_model_identifier(name: str) -> str:
        """Normalize model names for deduplication across providers."""

        normalized = name.lower()
        if ":" in normalized:
            normalized = normalized.split(":", 1)[0]
        if "/" in normalized:
            normalized = normalized.split("/", 1)[-1]
        return normalized

    def _get_ranked_model_summaries(self, limit: int = 5) -> tuple[list[str], int, bool]:
        """Return formatted, ranked model summaries and restriction status."""

        ranked = self._collect_ranked_capabilities()

        # Build allowlist map (provider -> lowercase names) when restrictions are active
        allowed_map: dict[Any, set[str]] = {}
        try:
            from utils.model_restrictions import get_restriction_service

            restriction_service = get_restriction_service()
            if restriction_service:
                from providers.shared import ProviderType

                for provider_type in ProviderType:
                    allowed = restriction_service.get_allowed_models(provider_type)
                    if allowed:
                        allowed_map[provider_type] = {name.lower() for name in allowed if name}
        except Exception:
            allowed_map = {}

        filtered: list[tuple[int, str, Any]] = []
        seen_normalized: set[str] = set()

        for rank, model_name, capabilities in ranked:
            canonical_name = getattr(capabilities, "model_name", model_name)
            canonical_lower = canonical_name.lower()
            alias_lower = model_name.lower()
            provider_type = getattr(capabilities, "provider", None)

            if allowed_map:
                if provider_type not in allowed_map:
                    continue
                allowed_set = allowed_map[provider_type]
                if canonical_lower not in allowed_set and alias_lower not in allowed_set:
                    continue

            normalized = self._normalize_model_identifier(canonical_name)
            if normalized in seen_normalized:
                continue

            seen_normalized.add(normalized)
            filtered.append((rank, canonical_name, capabilities))

        summaries: list[str] = []
        for rank, canonical_name, capabilities in filtered[:limit]:
            details: list[str] = []

            context_str = self._format_context_window(capabilities.context_window)
            if context_str:
                details.append(context_str)

            if capabilities.supports_extended_thinking:
                details.append("thinking")

            if capabilities.allow_code_generation:
                details.append("code-gen")

            base = f"{canonical_name} (score {rank}"
            if details:
                base = f"{base}, {', '.join(details)}"
            summaries.append(f"{base})")

        return summaries, len(filtered), bool(allowed_map)

    def _get_restriction_note(self) -> Optional[str]:
        """Return a string describing active per-provider allowlists, if any."""

        env_labels = {
            "OPENAI_ALLOWED_MODELS": "OpenAI",
            "GOOGLE_ALLOWED_MODELS": "Google",
            "XAI_ALLOWED_MODELS": "X.AI",
            "OPENROUTER_ALLOWED_MODELS": "OpenRouter",
            "DIAL_ALLOWED_MODELS": "DIAL",
        }

        notes: list[str] = []
        for env_var, label in env_labels.items():
            raw = get_env(env_var)
            if not raw:
                continue

            models = sorted({token.strip() for token in raw.split(",") if token.strip()})
            if not models:
                continue

            notes.append(f"{label}: {', '.join(models)}")

        if not notes:
            return None

        return "Policy allows only → " + "; ".join(notes)

    def _build_model_unavailable_message(self, model_name: str) -> str:
        """Compose a consistent error message for unavailable model scenarios."""

        tool_category = self.get_model_category()
        suggested_model = ModelProviderRegistry.get_preferred_fallback_model(tool_category)
        available_models_text = self._format_available_models_list()

        return (
            f"Model '{model_name}' is not available with current API keys. "
            f"Available models: {available_models_text}. "
            f"Suggested model for {self.get_name()}: '{suggested_model}' "
            f"(category: {tool_category.value}). If the user explicitly requested a model, you MUST use that exact name or report this error back—do not substitute another model."
        )

    def _build_auto_mode_required_message(self) -> str:
        """Compose the auto-mode prompt when an explicit model selection is required."""

        tool_category = self.get_model_category()
        suggested_model = ModelProviderRegistry.get_preferred_fallback_model(tool_category)
        available_models_text = self._format_available_models_list()

        return (
            "Model parameter is required in auto mode. "
            f"Available models: {available_models_text}. "
            f"Suggested model for {self.get_name()}: '{suggested_model}' "
            f"(category: {tool_category.value}). When the user names a model, relay that exact name—never swap in another option."
        )

    def get_model_field_schema(self) -> dict[str, Any]:
        """
        Generate the model field schema based on auto mode configuration.

        When auto mode is enabled, the model parameter becomes required
        and includes detailed descriptions of each model's capabilities.

        Returns:
            Dict containing the model field JSON schema
        """

        from config import DEFAULT_MODEL

        # Use the centralized effective auto mode check
        if self.is_effective_auto_mode():
            description = (
                "Currently in auto model selection mode. CRITICAL: When the user names a model, you MUST use that exact name unless the server rejects it. "
                "If no model is provided, you may use the `listmodels` tool to review options and select an appropriate match."
            )
            summaries, total, restricted = self._get_ranked_model_summaries()
            remainder = max(0, total - len(summaries))
            if summaries:
                top_line = "; ".join(summaries)
                if remainder > 0:
                    label = "Allowed models" if restricted else "Top models"
                    top_line = f"{label}: {top_line}; +{remainder} more via `listmodels`."
                else:
                    label = "Allowed models" if restricted else "Top models"
                    top_line = f"{label}: {top_line}."
                description = f"{description} {top_line}"

            restriction_note = self._get_restriction_note()
            if restriction_note and (remainder > 0 or not summaries):
                description = f"{description} {restriction_note}."
            return {
                "type": "string",
                "description": description,
            }

        description = (
            f"The default model is '{DEFAULT_MODEL}'. Override only when the user explicitly requests a different model, and use that exact name. "
            "If the requested model fails validation, surface the server error instead of substituting another model. When unsure, use the `listmodels` tool for details."
        )
        summaries, total, restricted = self._get_ranked_model_summaries()
        remainder = max(0, total - len(summaries))
        if summaries:
            top_line = "; ".join(summaries)
            if remainder > 0:
                label = "Allowed models" if restricted else "Preferred alternatives"
                top_line = f"{label}: {top_line}; +{remainder} more via `listmodels`."
            else:
                label = "Allowed models" if restricted else "Preferred alternatives"
                top_line = f"{label}: {top_line}."
            description = f"{description} {top_line}"

        restriction_note = self._get_restriction_note()
        if restriction_note and (remainder > 0 or not summaries):
            description = f"{description} {restriction_note}."

        return {
            "type": "string",
            "description": description,
        }

    def get_default_temperature(self) -> float:
        """
        Return the default temperature setting for this tool.

        Override this method to set tool-specific temperature defaults.
        Lower values (0.0-0.3) for analytical tasks, higher (0.7-1.0) for creative tasks.

        Returns:
            float: Default temperature between 0.0 and 1.0
        """
        return 0.5

    def wants_line_numbers_by_default(self) -> bool:
        """
        Return whether this tool wants line numbers added to code files by default.

        By default, ALL tools get line numbers for precise code references.
        Line numbers are essential for accurate communication about code locations.

        Returns:
            bool: True if line numbers should be added by default for this tool
        """
        return True  # All tools get line numbers by default for consistency

    def get_default_thinking_mode(self) -> str:
        """
        Return the default thinking mode for this tool.

        Thinking mode controls computational budget for reasoning.
        Override for tools that need more or less reasoning depth.

        Returns:
            str: One of "minimal", "low", "medium", "high", "max"
        """
        return "medium"  # Default to medium thinking for better reasoning

    def get_model_category(self) -> ToolModelCategory:
        """
        Return the model category for this tool.

        Model category influences which model is selected in auto mode.
        Override to specify whether your tool needs extended reasoning,
        fast response, or balanced capabilities.

        Returns:
            ToolModelCategory: Category that influences model selection
        """
        return ToolModelCategory.BALANCED

    def get_request_model(self):
        """
        Return the Pydantic model class used for validating requests.

        This model should inherit from ToolRequest and define all
        parameters specific to this tool. The default returns ToolRequest.

        Returns:
            Type[ToolRequest]: The request model class
        """
        from tools.shared.base_models import ToolRequest

        return ToolRequest

    def get_tool_fields(self) -> dict[str, dict[str, Any]]:
        """
        Return tool-specific field definitions. Override to define fields.

        This method should return a dictionary mapping field names to their
        JSON schema definitions. Common fields (model, temperature, etc.)
        are added automatically by SchemaBuilder.

        Returns:
            Dict mapping field names to JSON schema objects
        """
        return {}

    def get_required_fields(self) -> list[str]:
        """
        Return list of required field names. Override to specify requirements.

        The model field is automatically added if in auto mode.

        Returns:
            List of required field names
        """
        return []

    def supports_custom_request_model(self) -> bool:
        """
        Indicate whether this tool supports custom request models.

        Tools that override get_request_model() to return something other than
        ToolRequest should return True here.

        Returns:
            True if the tool uses a custom request model
        """
        from tools.shared.base_models import ToolRequest

        return self.get_request_model() != ToolRequest

    def validate_file_paths(self, request) -> Optional[str]:
        """
        Validate that all file paths in the request are absolute.

        This is a critical security function that prevents path traversal attacks
        and ensures all file access is properly controlled. All file paths must
        be absolute to avoid ambiguity and security issues.

        Args:
            request: The validated request object

        Returns:
            Optional[str]: Error message if validation fails, None if all paths are valid
        """
        # Only validate files/paths if they exist in the request
        file_fields = [
            "absolute_file_paths",
            "file",
            "path",
            "directory",
            "notebooks",
            "test_examples",
            "style_guide_examples",
            "files_checked",
            "relevant_files",
        ]

        for field_name in file_fields:
            if hasattr(request, field_name):
                field_value = getattr(request, field_name)
                if field_value is None:
                    continue

                # Handle both single paths and lists of paths
                paths_to_check = field_value if isinstance(field_value, list) else [field_value]

                for path in paths_to_check:
                    if path and not os.path.isabs(path):
                        return f"All file paths must be FULL absolute paths. Invalid path: '{path}'"

        return None

    def _validate_token_limit(self, content: str, content_type: str = "Content") -> None:
        """
        Validate that user-provided content doesn't exceed the MCP prompt size limit.

        This enforcement is strictly for text crossing the MCP transport boundary
        (i.e., user input). Internal prompt construction may exceed this size and is
        governed by model-specific token limits.

        Args:
            content: The user-originated content to validate
            content_type: Description of the content type for error messages

        Raises:
            ValueError: If content exceeds the character size limit
        """
        if not content:
            logger.debug(f"{self.name} tool {content_type.lower()} validation skipped (no content)")
            return

        char_count = len(content)
        if char_count > MCP_PROMPT_SIZE_LIMIT:
            token_estimate = estimate_tokens(content)
            error_msg = (
                f"{char_count:,} characters (~{token_estimate:,} tokens). "
                f"Maximum is {MCP_PROMPT_SIZE_LIMIT:,} characters."
            )
            logger.error(f"{self.name} tool {content_type.lower()} validation failed: {error_msg}")
            raise ValueError(f"{content_type} too large: {error_msg}")

        token_estimate = estimate_tokens(content)
        logger.debug(
            f"{self.name} tool {content_type.lower()} validation passed: "
            f"{char_count:,} characters (~{token_estimate:,} tokens)"
        )

    def get_model_provider(self, model_name: str) -> ModelProvider:
        """
        Get the appropriate model provider for the given model name.

        This method performs runtime validation to ensure the requested model
        is actually available with the current API key configuration.

        Args:
            model_name: Name of the model to get provider for

        Returns:
            ModelProvider: The provider instance for the model

        Raises:
            ValueError: If the model is not available or provider not found
        """
        try:
            provider = ModelProviderRegistry.get_provider_for_model(model_name)
            if not provider:
                logger.error(f"No provider found for model '{model_name}' in {self.name} tool")
                raise ValueError(self._build_model_unavailable_message(model_name))

            return provider
        except Exception as e:
            logger.error(f"Failed to get provider for model '{model_name}' in {self.name} tool: {e}")
            raise

    # === CONVERSATION AND FILE HANDLING METHODS ===

    def get_conversation_embedded_files(self, continuation_id: Optional[str]) -> list[str]:
        """
        Get list of files already embedded in conversation history.

        This method returns the list of files that have already been embedded
        in the conversation history for a given continuation thread. Tools can
        use this to avoid re-embedding files that are already available in the
        conversation context.

        Args:
            continuation_id: Thread continuation ID, or None for new conversations

        Returns:
            list[str]: List of file paths already embedded in conversation history
        """
        if not continuation_id:
            # New conversation, no files embedded yet
            return []

        thread_context = get_thread(continuation_id)
        if not thread_context:
            # Thread not found, no files embedded
            return []

        embedded_files = get_conversation_file_list(thread_context)
        logger.debug(f"[FILES] {self.name}: Found {len(embedded_files)} embedded files")
        return embedded_files

    def filter_new_files(self, requested_files: list[str], continuation_id: Optional[str]) -> list[str]:
        """
        Filter out files that are already embedded in conversation history.

        This method prevents duplicate file embeddings by filtering out files that have
        already been embedded in the conversation history. This optimizes token usage
        while ensuring tools still have logical access to all requested files through
        conversation history references.

        Args:
            requested_files: List of files requested for current tool execution
            continuation_id: Thread continuation ID, or None for new conversations

        Returns:
            list[str]: List of files that need to be embedded (not already in history)
        """
        logger.debug(f"[FILES] {self.name}: Filtering {len(requested_files)} requested files")

        if not continuation_id:
            # New conversation, all files are new
            logger.debug(f"[FILES] {self.name}: New conversation, all {len(requested_files)} files are new")
            return requested_files

        try:
            embedded_files = set(self.get_conversation_embedded_files(continuation_id))
            logger.debug(f"[FILES] {self.name}: Found {len(embedded_files)} embedded files in conversation")

            # Safety check: If no files are marked as embedded but we have a continuation_id,
            # this might indicate an issue with conversation history. Be conservative.
            if not embedded_files:
                logger.debug(f"{self.name} tool: No files found in conversation history for thread {continuation_id}")
                logger.debug(
                    f"[FILES] {self.name}: No embedded files found, returning all {len(requested_files)} requested files"
                )
                return requested_files

            # Return only files that haven't been embedded yet
            new_files = [f for f in requested_files if f not in embedded_files]
            logger.debug(
                f"[FILES] {self.name}: After filtering: {len(new_files)} new files, {len(requested_files) - len(new_files)} already embedded"
            )
            logger.debug(f"[FILES] {self.name}: New files to embed: {new_files}")

            # Log filtering results for debugging
            if len(new_files) < len(requested_files):
                skipped = [f for f in requested_files if f in embedded_files]
                logger.debug(
                    f"{self.name} tool: Filtering {len(skipped)} files already in conversation history: {', '.join(skipped)}"
                )
                logger.debug(f"[FILES] {self.name}: Skipped (already embedded): {skipped}")

            return new_files

        except Exception as e:
            # If there's any issue with conversation history lookup, be conservative
            # and include all files rather than risk losing access to needed files
            logger.warning(f"{self.name} tool: Error checking conversation history for {continuation_id}: {e}")
            logger.warning(f"{self.name} tool: Including all requested files as fallback")
            logger.debug(
                f"[FILES] {self.name}: Exception in filter_new_files, returning all {len(requested_files)} files as fallback"
            )
            return requested_files

    def format_conversation_turn(self, turn: ConversationTurn) -> list[str]:
        """
        Format a conversation turn for display in conversation history.

        Tools can override this to provide custom formatting for their responses
        while maintaining the standard structure for cross-tool compatibility.

        This method is called by build_conversation_history when reconstructing
        conversation context, allowing each tool to control how its responses
        appear in subsequent conversation turns.

        Args:
            turn: The conversation turn to format (from utils.conversation_memory)

        Returns:
            list[str]: Lines of formatted content for this turn

        Example:
            Default implementation returns:
            ["Files used in this turn: file1.py, file2.py", "", "Response content..."]

            Tools can override to add custom sections, formatting, or metadata display.
        """
        parts = []

        # Add files context if present
        if turn.files:
            parts.append(f"Files used in this turn: {', '.join(turn.files)}")
            parts.append("")  # Empty line for readability

        # Add the actual content
        parts.append(turn.content)

        return parts

    def handle_prompt_file(self, files: Optional[list[str]]) -> tuple[Optional[str], Optional[list[str]]]:
        """
        Check for and handle prompt.txt in the absolute file paths list.

        If prompt.txt is found, reads its content and removes it from the files list.
        This file is treated specially as the main prompt, not as an embedded file.

        This mechanism allows us to work around MCP's ~25K token limit by having
        the CLI save large prompts to a file, effectively using the file transfer
        mechanism to bypass token constraints while preserving response capacity.

        Args:
            files: List of absolute file paths (will be translated for current environment)

        Returns:
            tuple: (prompt_content, updated_files_list)
        """
        if not files:
            return None, files

        prompt_content = None
        updated_files = []

        for file_path in files:

            # Check if the filename is exactly "prompt.txt"
            # This ensures we don't match files like "myprompt.txt" or "prompt.txt.bak"
            if os.path.basename(file_path) == "prompt.txt":
                try:
                    # Read prompt.txt content and extract just the text
                    content, _ = read_file_content(file_path)
                    # Extract the content between the file markers
                    if "--- BEGIN FILE:" in content and "--- END FILE:" in content:
                        lines = content.split("\n")
                        in_content = False
                        content_lines = []
                        for line in lines:
                            if line.startswith("--- BEGIN FILE:"):
                                in_content = True
                                continue
                            elif line.startswith("--- END FILE:"):
                                break
                            elif in_content:
                                content_lines.append(line)
                        prompt_content = "\n".join(content_lines)
                    else:
                        # Fallback: if it's already raw content (from tests or direct input)
                        # and doesn't have error markers, use it directly
                        if not content.startswith("\n--- ERROR"):
                            prompt_content = content
                        else:
                            prompt_content = None
                except Exception:
                    # If we can't read the file, we'll just skip it
                    # The error will be handled elsewhere
                    pass
            else:
                # Keep the original path in the files list (will be translated later by read_files)
                updated_files.append(file_path)

        return prompt_content, updated_files if updated_files else None

    def get_prompt_content_for_size_validation(self, user_content: str) -> str:
        """
        Get the content that should be validated for MCP prompt size limits.

        When server.py embeds conversation history into the prompt field, it also stores
        the original user prompt in _original_user_prompt. We use that for size validation
        to avoid incorrectly triggering size limits due to conversation history.

        Args:
            user_content: The user content (may include conversation history)

        Returns:
            The original user prompt if available, otherwise the full user content
        """
        # Check if we have the current arguments from execute() method
        current_args = getattr(self, "_current_arguments", None)
        if current_args:
            # If server.py embedded conversation history, it stores original prompt separately
            original_user_prompt = current_args.get("_original_user_prompt")
            if original_user_prompt is not None:
                # Use original user prompt for size validation (excludes conversation history)
                return original_user_prompt

        # Fallback to default behavior (validate full user content)
        return user_content

    def check_prompt_size(self, text: str) -> Optional[dict[str, Any]]:
        """
        Check if USER INPUT text is too large for MCP transport boundary.

        IMPORTANT: This method should ONLY be used to validate user input that crosses
        the CLI ↔ MCP Server transport boundary. It should NOT be used to limit
        internal MCP Server operations.

        Args:
            text: The user input text to check (NOT internal prompt content)

        Returns:
            Optional[Dict[str, Any]]: Response asking for file handling if too large, None otherwise
        """
        if text and len(text) > MCP_PROMPT_SIZE_LIMIT:
            return {
                "status": "resend_prompt",
                "content": (
                    f"MANDATORY ACTION REQUIRED: The prompt is too large for MCP's token limits (>{MCP_PROMPT_SIZE_LIMIT:,} characters). "
                    "YOU MUST IMMEDIATELY save the prompt text to a temporary file named 'prompt.txt' in the working directory. "
                    "DO NOT attempt to shorten or modify the prompt. SAVE IT AS-IS to 'prompt.txt'. "
                    "Then resend the request, passing the absolute file path to 'prompt.txt' as part of the tool call, "
                    "along with any other files you wish to share as context. Leave the prompt text itself empty or very brief in the new request. "
                    "This is the ONLY way to handle large prompts - you MUST follow these exact steps."
                ),
                "content_type": "text",
                "metadata": {
                    "prompt_size": len(text),
                    "limit": MCP_PROMPT_SIZE_LIMIT,
                    "instructions": "MANDATORY: Save prompt to 'prompt.txt' in current folder and provide full path when recalling this tool.",
                },
            }
        return None

    def _prepare_file_content_for_prompt(
        self,
        request_files: list[str],
        continuation_id: Optional[str],
        context_description: str = "New files",
        max_tokens: Optional[int] = None,
        reserve_tokens: int = 1_000,
        remaining_budget: Optional[int] = None,
        arguments: Optional[dict] = None,
        model_context: Optional[Any] = None,
    ) -> tuple[str, list[str]]:
        """
        Centralized file processing implementing dual prioritization strategy.

        This method is the heart of conversation-aware file processing across all tools.

        Args:
            request_files: List of files requested for current tool execution
            continuation_id: Thread continuation ID, or None for new conversations
            context_description: Description for token limit validation (e.g. "Code", "New files")
            max_tokens: Maximum tokens to use (defaults to remaining budget or model-specific content allocation)
            reserve_tokens: Tokens to reserve for additional prompt content (default 1K)
            remaining_budget: Remaining token budget after conversation history (from server.py)
            arguments: Original tool arguments (used to extract _remaining_tokens if available)
            model_context: Model context object with all model information including token allocation

        Returns:
            tuple[str, list[str]]: (formatted_file_content, actually_processed_files)
                - formatted_file_content: Formatted file content string ready for prompt inclusion
                - actually_processed_files: List of individual file paths that were actually read and embedded
                  (directories are expanded to individual files)
        """
        if not request_files:
            return "", []

        # Extract remaining budget from arguments if available
        if remaining_budget is None:
            # Use provided arguments or fall back to stored arguments from execute()
            args_to_use = arguments or getattr(self, "_current_arguments", {})
            remaining_budget = args_to_use.get("_remaining_tokens")

        # Use remaining budget if provided, otherwise fall back to max_tokens or model-specific default
        if remaining_budget is not None:
            effective_max_tokens = remaining_budget - reserve_tokens
        elif max_tokens is not None:
            effective_max_tokens = max_tokens - reserve_tokens
        else:
            # Use model_context for token allocation
            if not model_context:
                # Try to get from stored attributes as fallback
                model_context = getattr(self, "_model_context", None)
                if not model_context:
                    logger.error(
                        f"[FILES] {self.name}: _prepare_file_content_for_prompt called without model_context. "
                        "This indicates an incorrect call sequence in the tool's implementation."
                    )
                    raise RuntimeError("Model context not provided for file preparation.")

            # This is now the single source of truth for token allocation.
            try:
                token_allocation = model_context.calculate_token_allocation()
                # Standardize on `file_tokens` for consistency and correctness.
                effective_max_tokens = token_allocation.file_tokens - reserve_tokens
                logger.debug(
                    f"[FILES] {self.name}: Using model context for {model_context.model_name}: "
                    f"{token_allocation.file_tokens:,} file tokens from {token_allocation.total_tokens:,} total"
                )
            except Exception as e:
                logger.error(
                    f"[FILES] {self.name}: Failed to calculate token allocation from model context: {e}", exc_info=True
                )
                # If the context exists but calculation fails, we still need to prevent a crash.
                # A loud error is logged, and we fall back to a safe default.
                effective_max_tokens = 100_000 - reserve_tokens

        # Ensure we have a reasonable minimum budget
        effective_max_tokens = max(1000, effective_max_tokens)

        files_to_embed = self.filter_new_files(request_files, continuation_id)
        logger.debug(f"[FILES] {self.name}: Will embed {len(files_to_embed)} files after filtering")

        # Log the specific files for debugging/testing
        if files_to_embed:
            logger.info(
                f"[FILE_PROCESSING] {self.name} tool will embed new files: {', '.join([os.path.basename(f) for f in files_to_embed])}"
            )
        else:
            logger.info(
                f"[FILE_PROCESSING] {self.name} tool: No new files to embed (all files already in conversation history)"
            )

        content_parts = []
        actually_processed_files = []

        # Read content of new files only
        if files_to_embed:
            logger.debug(f"{self.name} tool embedding {len(files_to_embed)} new files: {', '.join(files_to_embed)}")
            logger.debug(
                f"[FILES] {self.name}: Starting file embedding with token budget {effective_max_tokens + reserve_tokens:,}"
            )
            try:
                # Before calling read_files, expand directories to get individual file paths
                from utils.file_utils import expand_paths

                expanded_files = expand_paths(files_to_embed)
                logger.debug(
                    f"[FILES] {self.name}: Expanded {len(files_to_embed)} paths to {len(expanded_files)} individual files"
                )

                file_content = read_files(
                    files_to_embed,
                    max_tokens=effective_max_tokens + reserve_tokens,
                    reserve_tokens=reserve_tokens,
                    include_line_numbers=self.wants_line_numbers_by_default(),
                )
                # Note: No need to validate against MCP_PROMPT_SIZE_LIMIT here
                # read_files already handles token-aware truncation based on model's capabilities
                content_parts.append(file_content)

                # Track the expanded files as actually processed
                actually_processed_files.extend(expanded_files)

                # Estimate tokens for debug logging
                from utils.token_utils import estimate_tokens

                content_tokens = estimate_tokens(file_content)
                logger.debug(
                    f"{self.name} tool successfully embedded {len(files_to_embed)} files ({content_tokens:,} tokens)"
                )
                logger.debug(f"[FILES] {self.name}: Successfully embedded files - {content_tokens:,} tokens used")
                logger.debug(
                    f"[FILES] {self.name}: Actually processed {len(actually_processed_files)} individual files"
                )
            except Exception as e:
                logger.error(f"{self.name} tool failed to embed files {files_to_embed}: {type(e).__name__}: {e}")
                logger.debug(f"[FILES] {self.name}: File embedding failed - {type(e).__name__}: {e}")
                raise
        else:
            logger.debug(f"[FILES] {self.name}: No files to embed after filtering")

        # Generate note about files already in conversation history
        if continuation_id and len(files_to_embed) < len(request_files):
            embedded_files = self.get_conversation_embedded_files(continuation_id)
            skipped_files = [f for f in request_files if f in embedded_files]
            if skipped_files:
                logger.debug(
                    f"{self.name} tool skipping {len(skipped_files)} files already in conversation history: {', '.join(skipped_files)}"
                )
                logger.debug(f"[FILES] {self.name}: Adding note about {len(skipped_files)} skipped files")
                if content_parts:
                    content_parts.append("\n\n")
                note_lines = [
                    "--- NOTE: Additional files referenced in conversation history ---",
                    "The following files are already available in our conversation context:",
                    "\n".join(f"  - {f}" for f in skipped_files),
                    "--- END NOTE ---",
                ]
                content_parts.append("\n".join(note_lines))
            else:
                logger.debug(f"[FILES] {self.name}: No skipped files to note")

        result = "".join(content_parts) if content_parts else ""
        logger.debug(
            f"[FILES] {self.name}: _prepare_file_content_for_prompt returning {len(result)} chars, {len(actually_processed_files)} processed files"
        )
        return result, actually_processed_files

    def get_websearch_instruction(self, tool_specific: Optional[str] = None) -> str:
        """
        Generate standardized web search instruction.

        Args:
            tool_specific: Optional tool-specific search guidance

        Returns:
            str: Web search instruction to append to prompt
        """

        base_instruction = """

WEB SEARCH CAPABILITY: You can request the calling agent to perform web searches to enhance your analysis with current information!

IMPORTANT: When you identify areas where web searches would significantly improve your response (such as checking current documentation, finding recent solutions, verifying best practices, or gathering community insights), you MUST explicitly instruct the agent to perform specific web searches and then respond back using the continuation_id from this response to continue the analysis.

Use clear, direct language based on the value of the search:

For valuable supplementary information: "Please perform a web search on '[specific topic/query]' and then continue this analysis using the continuation_id from this response if you find relevant information."

For important missing information: "Please search for '[specific topic/query]' and respond back with the findings using the continuation_id from this response - this information is needed to provide a complete analysis."

For critical/essential information: "SEARCH REQUIRED: Please immediately perform a web search on '[specific topic/query]' and respond back with the results using the continuation_id from this response. Cannot provide accurate analysis without this current information."

This ensures you get the most current and comprehensive information while maintaining conversation context through the continuation_id."""

        if tool_specific:
            return f"""{base_instruction}

{tool_specific}

When recommending searches, be specific about what information you need and why it would improve your analysis."""

        # Default instruction for all tools
        return f"""{base_instruction}

Consider requesting searches for:
- Current documentation and API references
- Recent best practices and patterns
- Known issues and community solutions
- Framework updates and compatibility
- Security advisories and patches
- Performance benchmarks and optimizations

When recommending searches, be specific about what information you need and why it would improve your analysis. Always remember to instruct agent to use the continuation_id from this response when providing search results."""

    def get_language_instruction(self) -> str:
        """
        Generate language instruction based on LOCALE configuration.

        Returns:
            str: Language instruction to prepend to prompt, or empty string if
                 no locale set
        """
        # Read LOCALE directly from environment to support dynamic changes
        # Tests can monkeypatch LOCALE via the environment helper (or .env when override is enforced)

        locale = (get_env("LOCALE", "") or "").strip()

        if not locale:
            return ""

        # Simple language instruction
        return f"Always respond in {locale}.\n\n"

    # === ABSTRACT METHODS FOR SIMPLE TOOLS ===

    @abstractmethod
    async def prepare_prompt(self, request) -> str:
        """
        Prepare the complete prompt for the AI model.

        This method should construct the full prompt by combining:
        - System prompt from get_system_prompt()
        - File content from _prepare_file_content_for_prompt()
        - Conversation history from reconstruct_thread_context()
        - User's request and any tool-specific context

        Args:
            request: The validated request object

        Returns:
            str: Complete prompt ready for the AI model
        """
        pass

    def format_response(self, response: str, request, model_info: dict = None) -> str:
        """
        Format the AI model's response for the user.

        This method allows tools to post-process the model's response,
        adding structure, validation, or additional context.

        The default implementation returns the response unchanged.
        Tools can override this method to add custom formatting.

        Args:
            response: Raw response from the AI model
            request: The original request object
            model_info: Optional model information and metadata

        Returns:
            str: Formatted response ready for the user
        """
        return response

    # === IMPLEMENTATION METHODS ===
    # These will be provided in a full implementation but are inherited from current base.py
    # for now to maintain compatibility.

    async def execute(self, arguments: dict[str, Any]) -> list[TextContent]:
        """
        Execute the tool using the comprehensive flow.

        This method handles the full execution pattern:
        1. Request validation
        2. File path security validation
        3. Model resolution and context setup
        4. Conversation history handling
        5. Image validation
        6. Temperature and thinking mode configuration
        7. AI model invocation
        8. Response parsing and formatting
        9. Conversation continuation offers
        """
        tool_logger = logging.getLogger(f"tools.{self.get_name()}")

        try:
            # Store arguments for access by helper methods
            self._current_arguments = arguments

            tool_logger.info(f"🔧 {self.get_name()} tool called with arguments: {list(arguments.keys())}")

            # Validate request using the tool's Pydantic model
            request_model = self.get_request_model()
            request = request_model(**arguments)
            tool_logger.debug(f"Request validation successful for {self.get_name()}")

            # Validate file paths for security
            # This prevents path traversal attacks and ensures proper access control
            path_error = self._validate_file_paths(request)
            if path_error:
                error_output = ToolOutput(
                    status="error",
                    content=path_error,
                    content_type="text",
                )
                tool_logger.error("Path validation failed for %s: %s", self.get_name(), path_error)
                raise ToolExecutionError(error_output.model_dump_json())

            # Handle model resolution like old base.py
            model_name = req.get_request_model_name(request)
            if not model_name:
                from config import DEFAULT_MODEL

                model_name = DEFAULT_MODEL

            # Store the current model name for later use
            self._current_model_name = model_name

            # Handle model context from arguments (for in-process testing)
            if "_model_context" in arguments:
                self._model_context = arguments["_model_context"]
                tool_logger.debug(f"{self.get_name()}: Using model context from arguments")
            else:
                # Create model context if not provided
                from utils.model_context import ModelContext

                self._model_context = ModelContext(model_name)
                tool_logger.debug(f"{self.get_name()}: Created model context for {model_name}")

            # Get images if present
            images = req.get_request_images(request)
            continuation_id = req.get_request_continuation_id(request)

            # Handle conversation history and prompt preparation
            if continuation_id:
                # Check if conversation history is already embedded
                field_value = req.get_request_prompt(request)
                if "=== CONVERSATION HISTORY ===" in field_value:
                    # Use pre-embedded history
                    prompt = field_value
                    tool_logger.debug(f"{self.get_name()}: Using pre-embedded conversation history")
                else:
                    # No embedded history - reconstruct it (for in-process calls)
                    tool_logger.debug(f"{self.get_name()}: No embedded history found, reconstructing conversation")

                    # Get thread context
                    from utils.conversation_memory import add_turn, build_conversation_history, get_thread

                    thread_context = get_thread(continuation_id)

                    if thread_context:
                        # Add user's new input to conversation
                        user_prompt = req.get_request_prompt(request)
                        user_files = req.get_request_files(request)
                        if user_prompt:
                            add_turn(continuation_id, "user", user_prompt, files=user_files)

                            # Get updated thread context after adding the turn
                            thread_context = get_thread(continuation_id)
                            tool_logger.debug(
                                f"{self.get_name()}: Retrieved updated thread with {len(thread_context.turns)} turns"
                            )

                        # Build conversation history with updated thread context
                        conversation_history, conversation_tokens = build_conversation_history(
                            thread_context, self._model_context
                        )

                        # Get the base prompt from the tool
                        base_prompt = await self.prepare_prompt(request)

                        # Combine with conversation history
                        if conversation_history:
                            prompt = f"{conversation_history}\n\n=== NEW USER INPUT ===\n{base_prompt}"
                        else:
                            prompt = base_prompt
                    else:
                        # Thread not found, prepare normally
                        tool_logger.warning(f"Thread {continuation_id} not found, preparing prompt normally")
                        prompt = await self.prepare_prompt(request)
            else:
                # New conversation, prepare prompt normally
                prompt = await self.prepare_prompt(request)

                # Add follow-up instructions for new conversations
                from server import get_follow_up_instructions

                follow_up_instructions = get_follow_up_instructions(0)
                prompt = f"{prompt}\n\n{follow_up_instructions}"
                tool_logger.debug(
                    f"Added follow-up instructions for new {self.get_name()} conversation"
                )  # Validate images if any were provided
            if images:
                image_validation_error = self._validate_image_limits(
                    images, model_context=self._model_context, continuation_id=continuation_id
                )
                if image_validation_error:
                    error_output = ToolOutput(
                        status=image_validation_error.get("status", "error"),
                        content=image_validation_error.get("content"),
                        content_type=image_validation_error.get("content_type", "text"),
                        metadata=image_validation_error.get("metadata"),
                    )
                    payload = error_output.model_dump_json()
                    tool_logger.error("Image validation failed for %s: %s", self.get_name(), payload)
                    raise ToolExecutionError(payload)

            # Get and validate temperature against model constraints
            temperature, temp_warnings = self.get_validated_temperature(request, self._model_context)

            # Log any temperature corrections
            for warning in temp_warnings:
                # Get thinking mode with defaults
                tool_logger.warning(warning)
            thinking_mode = req.get_request_thinking_mode(request)
            if thinking_mode is None:
                thinking_mode = self.get_default_thinking_mode()

            # Get the provider from model context (clean OOP - no re-fetching)
            provider = self._model_context.provider
            capabilities = self._model_context.capabilities

            # Get system prompt for this tool
            base_system_prompt = self.get_system_prompt()
            capability_augmented_prompt = self._augment_system_prompt_with_capabilities(
                base_system_prompt, capabilities
            )
            language_instruction = self.get_language_instruction()
            system_prompt = language_instruction + capability_augmented_prompt

            # Generate AI response using the provider
            tool_logger.info(f"Sending request to {provider.get_provider_type().value} API for {self.get_name()}")
            tool_logger.info(
                f"Using model: {self._model_context.model_name} via {provider.get_provider_type().value} provider"
            )

            # Estimate tokens for logging
            from utils.token_utils import estimate_tokens as _estimate_tokens

            estimated_tokens = _estimate_tokens(prompt)
            tool_logger.debug(f"Prompt length: {len(prompt)} characters (~{estimated_tokens:,} tokens)")

            # Resolve model capabilities for feature gating
            supports_thinking = capabilities.supports_extended_thinking

            # Generate content with provider abstraction
            model_response = provider.generate_content(
                prompt=prompt,
                model_name=self._current_model_name,
                system_prompt=system_prompt,
                temperature=temperature,
                thinking_mode=thinking_mode if supports_thinking else None,
                images=images if images else None,
            )

            tool_logger.info(f"Received response from {provider.get_provider_type().value} API for {self.get_name()}")

            # Process the model's response
            if model_response.content:
                raw_text = model_response.content

                # Create model info for conversation tracking
                model_info = {
                    "provider": provider,
                    "model_name": self._current_model_name,
                    "model_response": model_response,
                }

                # Parse response using the same logic as old base.py
                tool_output = self._parse_response(raw_text, request, model_info)
                tool_logger.info(f"✅ {self.get_name()} tool completed successfully")

            else:
                # Handle cases where the model couldn't generate a response
                metadata = model_response.metadata or {}
                finish_reason = metadata.get("finish_reason", "Unknown")

                if metadata.get("is_blocked_by_safety"):
                    # Specific handling for content safety blocks
                    safety_details = metadata.get("safety_feedback") or "details not provided"
                    tool_logger.warning(
                        f"Response blocked by content safety policy for {self.get_name()}. "
                        f"Reason: {finish_reason}, Details: {safety_details}"
                    )
                    tool_output = ToolOutput(
                        status="error",
                        content="Your request was blocked by the content safety policy. "
                        "Please try modifying your prompt.",
                        content_type="text",
                    )
                else:
                    # Handle other empty responses - could be legitimate completion or unclear blocking
                    if finish_reason == "STOP":
                        # Model completed normally but returned empty content - retry with clarification
                        tool_logger.info(
                            f"Model completed with empty response for {self.get_name()}, retrying with clarification"
                        )

                        # Retry the same request with modified prompt asking for explicit response
                        original_prompt = prompt
                        retry_prompt = f"{original_prompt}\n\nIMPORTANT: Please provide a substantive response. If you cannot respond to the above request, please explain why and suggest alternatives."

                        try:
                            retry_response = provider.generate_content(
                                prompt=retry_prompt,
                                model_name=self._current_model_name,
                                system_prompt=system_prompt,
                                temperature=temperature,
                                thinking_mode=thinking_mode if supports_thinking else None,
                                images=images if images else None,
                            )

                            if retry_response.content:
                                # Successful retry - use the retry response
                                tool_logger.info(f"Retry successful for {self.get_name()}")
                                raw_text = retry_response.content

                                # Update model info for the successful retry
                                model_info = {
                                    "provider": provider,
                                    "model_name": self._current_model_name,
                                    "model_response": retry_response,
                                }

                                # Parse the retry response
                                tool_output = self._parse_response(raw_text, request, model_info)
                                tool_logger.info(f"✅ {self.get_name()} tool completed successfully after retry")
                            else:
                                # Retry also failed - inspect metadata to find out why
                                retry_metadata = retry_response.metadata or {}
                                if retry_metadata.get("is_blocked_by_safety"):
                                    # The retry was blocked by safety filters
                                    safety_details = retry_metadata.get("safety_feedback") or "details not provided"
                                    tool_logger.warning(
                                        f"Retry for {self.get_name()} was blocked by content safety policy. "
                                        f"Details: {safety_details}"
                                    )
                                    tool_output = ToolOutput(
                                        status="error",
                                        content="Your request was also blocked by the content safety policy after a retry. "
                                        "Please try rephrasing your prompt significantly.",
                                        content_type="text",
                                    )
                                else:
                                    # Retry failed for other reasons (e.g., another STOP)
                                    tool_output = ToolOutput(
                                        status="error",
                                        content="The model repeatedly returned empty responses. This may indicate content filtering or a model issue.",
                                        content_type="text",
                                    )
                        except Exception as retry_error:
                            tool_logger.warning(f"Retry failed for {self.get_name()}: {retry_error}")
                            tool_output = ToolOutput(
                                status="error",
                                content=f"Model returned empty response and retry failed: {str(retry_error)}",
                                content_type="text",
                            )
                    else:
                        # Non-STOP finish reasons are likely actual errors
                        tool_logger.warning(
                            f"Response blocked or incomplete for {self.get_name()}. Finish reason: {finish_reason}"
                        )
                        tool_output = ToolOutput(
                            status="error",
                            content=f"Response blocked or incomplete. Finish reason: {finish_reason}",
                            content_type="text",
                        )

            # Return the tool output as TextContent, marking protocol errors appropriately
            payload = tool_output.model_dump_json()
            if tool_output.status == "error":
                tool_logger.error("%s reported error status - raising ToolExecutionError", self.get_name())
                raise ToolExecutionError(payload)
            return [TextContent(type="text", text=payload)]

        except ToolExecutionError:
            raise
        except Exception as e:
            # Special handling for MCP size check errors
            if str(e).startswith("MCP_SIZE_CHECK:"):
                # Extract the JSON content after the prefix
                json_content = str(e)[len("MCP_SIZE_CHECK:") :]
                raise ToolExecutionError(json_content)

            tool_logger.error(f"Error in {self.get_name()}: {str(e)}")
            error_output = ToolOutput(
                status="error",
                content=f"Error in {self.get_name()}: {str(e)}",
                content_type="text",
            )
            raise ToolExecutionError(error_output.model_dump_json()) from e

    def _should_require_model_selection(self, model_name: str) -> bool:
        """
        Check if we should require the CLI to select a model at runtime.

        This is called during request execution to determine if we need
        to return an error asking the CLI to provide a model parameter.

        Args:
            model_name: The model name from the request or DEFAULT_MODEL

        Returns:
            bool: True if we should require model selection
        """
        # Case 1: Model is explicitly "auto"
        if model_name.lower() == "auto":
            return True

        # Case 2: Requested model is not available
        from providers.registry import ModelProviderRegistry

        provider = ModelProviderRegistry.get_provider_for_model(model_name)
        if not provider:
            logger.warning(f"Model '{model_name}' is not available with current API keys. Requiring model selection.")
            return True

        return False

    def _get_available_models(self) -> list[str]:
        """
        Get list of models available from enabled providers.

        Only returns models from providers that have valid API keys configured.
        This fixes the namespace collision bug where models from disabled providers
        were shown to the CLI, causing routing conflicts.

        Returns:
            List of model names from enabled providers only
        """
        from providers.registry import ModelProviderRegistry

        # Get models from enabled providers only (those with valid API keys)
        all_models = ModelProviderRegistry.get_available_model_names()

        # Add OpenRouter models and their aliases when OpenRouter is configured
        openrouter_key = get_env("OPENROUTER_API_KEY")
        if openrouter_key and openrouter_key != "your_openrouter_api_key_here":
            try:
                registry = self._get_openrouter_registry()

                for alias in registry.list_aliases():
                    if alias not in all_models:
                        all_models.append(alias)
            except Exception as exc:  # pragma: no cover - logged for observability
                import logging

                logging.debug(f"Failed to add OpenRouter models to enum: {exc}")

        # Add custom models (and their aliases) when a custom endpoint is available
        custom_url = get_env("CUSTOM_API_URL")
        if custom_url:
            try:
                registry = self._get_custom_registry()
                for alias in registry.list_aliases():
                    if alias not in all_models:
                        all_models.append(alias)
            except Exception as exc:  # pragma: no cover - logged for observability
                import logging

                logging.debug(f"Failed to add custom models to enum: {exc}")

        # Remove duplicates while preserving insertion order
        seen: set[str] = set()
        unique_models: list[str] = []
        for model in all_models:
            if model not in seen:
                seen.add(model)
                unique_models.append(model)

        return unique_models

    def _resolve_model_context(self, arguments: dict, request) -> tuple[str, Any]:
        """
        Resolve model context and name using centralized logic.

        This method extracts the model resolution logic from execute() so it can be
        reused by tools that override execute() (like debug tool) without duplicating code.

        Args:
            arguments: Dictionary of arguments from the MCP client
            request: The validated request object

        Returns:
            tuple[str, ModelContext]: (resolved_model_name, model_context)

        Raises:
            ValueError: If model resolution fails or model selection is required
        """
        # MODEL RESOLUTION NOW HAPPENS AT MCP BOUNDARY
        # Extract pre-resolved model context from server.py
        model_context = arguments.get("_model_context")
        resolved_model_name = arguments.get("_resolved_model_name")

        if model_context and resolved_model_name:
            # Model was already resolved at MCP boundary
            model_name = resolved_model_name
            logger.debug(f"Using pre-resolved model '{model_name}' from MCP boundary")
        else:
            # Fallback for direct execute calls
            model_name = getattr(request, "model", None)
            if not model_name:
                from config import DEFAULT_MODEL

                model_name = DEFAULT_MODEL
            logger.debug(f"Using fallback model resolution for '{model_name}' (test mode)")

            # For tests: Check if we should require model selection (auto mode)
            if self._should_require_model_selection(model_name):
                # Build error message based on why selection is required
                if model_name.lower() == "auto":
                    error_message = self._build_auto_mode_required_message()
                else:
                    error_message = self._build_model_unavailable_message(model_name)
                raise ValueError(error_message)

            # Create model context for tests
            from utils.model_context import ModelContext

            model_context = ModelContext(model_name)

        return model_name, model_context

    def validate_and_correct_temperature(self, temperature: float, model_context: Any) -> tuple[float, list[str]]:
        """
        Validate and correct temperature for the specified model.

        This method ensures that the temperature value is within the valid range
        for the specific model being used. Different models have different temperature
        constraints (e.g., o1 models require temperature=1.0, GPT models support 0-2).

        Args:
            temperature: Temperature value to validate
            model_context: Model context object containing model name, provider, and capabilities

        Returns:
            Tuple of (corrected_temperature, warning_messages)
        """
        try:
            # Use model context capabilities directly - clean OOP approach
            capabilities = model_context.capabilities
            constraint = capabilities.temperature_constraint

            warnings = []
            if not constraint.validate(temperature):
                corrected = constraint.get_corrected_value(temperature)
                warning = (
                    f"Temperature {temperature} invalid for {model_context.model_name}. "
                    f"{constraint.get_description()}. Using {corrected} instead."
                )
                warnings.append(warning)
                return corrected, warnings

            return temperature, warnings

        except Exception as e:
            # If validation fails for any reason, use the original temperature
            # and log a warning (but don't fail the request)
            logger.warning(f"Temperature validation failed for {model_context.model_name}: {e}")
            return temperature, [f"Temperature validation failed: {e}"]

    def _validate_image_limits(
        self, images: Optional[list[str]], model_context: Optional[Any] = None, continuation_id: Optional[str] = None
    ) -> Optional[dict]:
        """
        Validate image size and count against model capabilities.

        This performs strict validation to ensure we don't exceed model-specific
        image limits. Uses capability-based validation with actual model
        configuration rather than hard-coded limits.

        Args:
            images: List of image paths/data URLs to validate
            model_context: Model context object containing model name, provider, and capabilities
            continuation_id: Optional continuation ID for conversation context

        Returns:
            Optional[dict]: Error response if validation fails, None if valid
        """
        if not images:
            return None

        # Import here to avoid circular imports
        import base64
        from pathlib import Path

        if not model_context:
            # Get from tool's stored context as fallback
            model_context = getattr(self, "_model_context", None)
            if not model_context:
                logger.warning("No model context available for image validation")
                return None

        try:
            # Use model context capabilities directly - clean OOP approach
            capabilities = model_context.capabilities
            model_name = model_context.model_name
        except Exception as e:
            logger.warning(f"Failed to get capabilities from model_context for image validation: {e}")
            # Generic error response when capabilities cannot be accessed
            model_name = getattr(model_context, "model_name", "unknown")
            return {
                "status": "error",
                "content": self._build_model_unavailable_message(model_name),
                "content_type": "text",
                "metadata": {
                    "error_type": "validation_error",
                    "model_name": model_name,
                    "supports_images": None,  # Unknown since model capabilities unavailable
                    "image_count": len(images) if images else 0,
                },
            }

        # Check if model supports images
        if not capabilities.supports_images:
            return {
                "status": "error",
                "content": (
                    f"Image support not available: Model '{model_name}' does not support image processing. "
                    f"Please use a vision-capable model such as 'gemini-2.5-flash', 'o3', "
                    f"or 'claude-opus-4.1' for image analysis tasks."
                ),
                "content_type": "text",
                "metadata": {
                    "error_type": "validation_error",
                    "model_name": model_name,
                    "supports_images": False,
                    "image_count": len(images),
                },
            }

        # Get model image limits from capabilities
        max_images = 5  # Default max number of images
        max_size_mb = capabilities.max_image_size_mb

        # Check image count
        if len(images) > max_images:
            return {
                "status": "error",
                "content": (
                    f"Too many images: Model '{model_name}' supports a maximum of {max_images} images, "
                    f"but {len(images)} were provided. Please reduce the number of images."
                ),
                "content_type": "text",
                "metadata": {
                    "error_type": "validation_error",
                    "model_name": model_name,
                    "image_count": len(images),
                    "max_images": max_images,
                },
            }

        # Calculate total size of all images
        total_size_mb = 0.0
        for image_path in images:
            try:
                if image_path.startswith("data:image/"):
                    # Handle data URL: data:image/png;base64,iVBORw0...
                    _, data = image_path.split(",", 1)
                    # Base64 encoding increases size by ~33%, so decode to get actual size
                    actual_size = len(base64.b64decode(data))
                    total_size_mb += actual_size / (1024 * 1024)
                else:
                    # Handle file path
                    path = Path(image_path)
                    if path.exists():
                        file_size = path.stat().st_size
                        total_size_mb += file_size / (1024 * 1024)
                    else:
                        logger.warning(f"Image file not found: {image_path}")
                        # Assume a reasonable size for missing files to avoid breaking validation
                        total_size_mb += 1.0  # 1MB assumption
            except Exception as e:
                logger.warning(f"Failed to get size for image {image_path}: {e}")
                # Assume a reasonable size for problematic files
                total_size_mb += 1.0  # 1MB assumption

        # Apply 40MB cap for custom models if needed
        effective_limit_mb = max_size_mb
        try:
            from providers.shared import ProviderType

            # ModelCapabilities dataclass has provider field defined
            if capabilities.provider == ProviderType.CUSTOM:
                effective_limit_mb = min(max_size_mb, 40.0)
        except Exception:
            pass

        # Validate against size limit
        if total_size_mb > effective_limit_mb:
            return {
                "status": "error",
                "content": (
                    f"Image size limit exceeded: Model '{model_name}' supports maximum {effective_limit_mb:.1f}MB "
                    f"for all images combined, but {total_size_mb:.1f}MB was provided. "
                    f"Please reduce image sizes or count and try again."
                ),
                "content_type": "text",
                "metadata": {
                    "error_type": "validation_error",
                    "model_name": model_name,
                    "total_size_mb": round(total_size_mb, 2),
                    "limit_mb": round(effective_limit_mb, 2),
                    "image_count": len(images),
                    "supports_images": True,
                },
            }

        # All validations passed
        logger.debug(f"Image validation passed: {len(images)} images, {total_size_mb:.1f}MB total")
        return None

    def _parse_response(self, raw_text: str, request, model_info: Optional[dict] = None):
        """
        Parse the raw response and format it using the hook method.

        This simplified version focuses on formatting the response
        using the format_response hook, then handling conversation continuation.
        """
        # Format the response using the hook method
        formatted_response = self.format_response(raw_text, request, model_info)

        # Handle conversation continuation
        continuation_id = req.get_request_continuation_id(request)
        if continuation_id:
            self._record_assistant_turn(continuation_id, raw_text, request, model_info)

        # Create continuation offer
        continuation_data = self._create_continuation_offer(request, model_info)
        if continuation_data:
            return self._create_continuation_offer_response(formatted_response, continuation_data, request, model_info)
        else:
            # Build metadata with model and provider info for success response
            metadata = {}
            if model_info:
                model_name = model_info.get("model_name")
                if model_name:
                    metadata["model_used"] = model_name
                provider_name = self._extract_provider_name(model_info.get("provider"))
                if provider_name:
                    metadata["provider_used"] = provider_name

            return ToolOutput(
                status="success",
                content=formatted_response,
                content_type="text",
                metadata=metadata if metadata else None,
            )

    # === CONTINUATION AND CONVERSATION METHODS ===

    def _create_continuation_offer(self, request, model_info: Optional[dict] = None):
        """Create continuation offer following old base.py pattern."""
        continuation_id = req.get_request_continuation_id(request)

        try:
            from utils.conversation_memory import create_thread, get_thread

            if continuation_id:
                # Existing conversation
                thread_context = get_thread(continuation_id)
                if thread_context and thread_context.turns:
                    turn_count = len(thread_context.turns)
                    from utils.conversation_memory import MAX_CONVERSATION_TURNS

                    if turn_count >= MAX_CONVERSATION_TURNS - 1:
                        return None  # No more turns allowed

                    remaining_turns = MAX_CONVERSATION_TURNS - turn_count - 1
                    return {
                        "continuation_id": continuation_id,
                        "remaining_turns": remaining_turns,
                        "note": f"You can continue this conversation for {remaining_turns} more exchanges.",
                    }
            else:
                # New conversation - create thread and offer continuation
                # Convert request to dict for initial_context
                initial_request_dict = req.get_request_as_dict(request)

                new_thread_id = create_thread(tool_name=self.get_name(), initial_request=initial_request_dict)

                # Add the initial user turn to the new thread
                from utils.conversation_memory import MAX_CONVERSATION_TURNS, add_turn

                user_prompt = req.get_request_prompt(request)
                user_files = req.get_request_files(request)
                user_images = req.get_request_images(request)

                # Add user's initial turn
                add_turn(
                    new_thread_id,
                    "user",
                    user_prompt,
                    files=user_files,
                    images=user_images,
                    tool_name=self.get_name(),
                )

                return {
                    "continuation_id": new_thread_id,
                    "remaining_turns": MAX_CONVERSATION_TURNS - 1,
                    "note": f"You can continue this conversation for {MAX_CONVERSATION_TURNS - 1} more exchanges.",
                }
        except Exception:
            return None

    @staticmethod
    def _extract_provider_name(provider) -> Optional[str]:
        """Extract a string provider name from a provider object or string.

        Handles provider objects (with get_provider_type()), plain strings,
        and None values.
        """
        if provider is None:
            return None
        if isinstance(provider, str):
            return provider
        try:
            return provider.get_provider_type().value
        except AttributeError:
            return str(provider)

    def _create_continuation_offer_response(
        self, content: str, continuation_data: dict, request, model_info: Optional[dict] = None
    ):
        """Create response with continuation offer following old base.py pattern."""
        try:
            if not req.get_request_continuation_id(request):
                self._record_assistant_turn(
                    continuation_data["continuation_id"],
                    content,
                    request,
                    model_info,
                )

            continuation_offer = ContinuationOffer(
                continuation_id=continuation_data["continuation_id"],
                note=continuation_data["note"],
                remaining_turns=continuation_data["remaining_turns"],
            )

            # Build metadata with model and provider info
            metadata = {"tool_name": self.get_name(), "conversation_ready": True}
            if model_info:
                model_name = model_info.get("model_name")
                if model_name:
                    metadata["model_used"] = model_name
                provider_name = self._extract_provider_name(model_info.get("provider"))
                if provider_name:
                    metadata["provider_used"] = provider_name

            return ToolOutput(
                status="continuation_available",
                content=content,
                content_type="text",
                continuation_offer=continuation_offer,
                metadata=metadata,
            )
        except Exception:
            # Fallback to simple success if continuation offer fails
            return ToolOutput(status="success", content=content, content_type="text")

    def _record_assistant_turn(
        self, continuation_id: str, response_text: str, request, model_info: Optional[dict]
    ) -> None:
        """Persist an assistant response in conversation memory."""

        if not continuation_id:
            return

        from utils.conversation_memory import add_turn

        model_provider = None
        model_name = None
        model_metadata = None

        if model_info:
            model_provider = self._extract_provider_name(model_info.get("provider"))
            model_name = model_info.get("model_name")
            model_response = model_info.get("model_response")
            if model_response:
                model_metadata = {"usage": model_response.usage, "metadata": model_response.metadata}

        add_turn(
            continuation_id,
            "assistant",
            response_text,
            files=req.get_request_files(request),
            images=req.get_request_images(request),
            tool_name=self.get_name(),
            model_provider=model_provider,
            model_name=model_name,
            model_metadata=model_metadata,
        )

    # === CONVENIENCE METHODS FOR COMMON TOOL PATTERNS ===

    def build_standard_prompt(
        self, system_prompt: str, user_content: str, request, file_context_title: str = "CONTEXT FILES"
    ) -> str:
        """
        Build a standard prompt with system prompt, user content, and optional files.

        This is a convenience method that handles the common pattern of:
        1. Adding file content if present
        2. Checking token limits
        3. Adding web search instructions
        4. Combining everything into a well-formatted prompt

        Args:
            system_prompt: The system prompt for the tool
            user_content: The main user request/content
            request: The validated request object
            file_context_title: Title for the file context section

        Returns:
            Complete formatted prompt ready for the AI model
        """
        # Check size limits against raw user input before enriching with internal context
        content_to_validate = self.get_prompt_content_for_size_validation(user_content)
        self._validate_token_limit(content_to_validate, "Content")

        # Add context files if provided (does not affect MCP boundary enforcement)
        files = req.get_request_files(request)
        if files:
            file_content, processed_files = self._prepare_file_content_for_prompt(
                files,
                req.get_request_continuation_id(request),
                "Context files",
                model_context=getattr(self, "_model_context", None),
            )
            self._actually_processed_files = processed_files
            if file_content:
                user_content = f"{user_content}\n\n=== {file_context_title} ===\n{file_content}\n=== END CONTEXT ===="

        # Add standardized web search guidance
        websearch_instruction = self.get_websearch_instruction(self.get_websearch_guidance())

        # Combine system prompt with user content
        full_prompt = f"""{system_prompt}{websearch_instruction}

=== USER REQUEST ===
{user_content}
=== END REQUEST ===

Please provide a thoughtful, comprehensive response:"""

        return full_prompt

    def get_websearch_guidance(self) -> Optional[str]:
        """
        Return tool-specific web search guidance.

        Override this to provide tool-specific guidance for when web searches
        would be helpful. Return None to use the default guidance.

        Returns:
            Tool-specific web search guidance or None for default
        """
        return None

    def handle_prompt_file_with_fallback(self, request) -> str:
        """
        Handle prompt.txt files with fallback to request field.

        This is a convenience method for tools that accept prompts either
        as a field or as a prompt.txt file. It handles the extraction
        and validation automatically.

        Args:
            request: The validated request object

        Returns:
            The effective prompt content

        Raises:
            ValueError: If prompt is too large for MCP transport
        """
        # Check for prompt.txt in provided absolute file paths
        files = req.get_request_files(request)
        if files:
            prompt_content, updated_files = self.handle_prompt_file(files)

            # Update request files list if needed
            if updated_files is not None:
                req.set_request_files(request, updated_files)
        else:
            prompt_content = None

        # Use prompt.txt content if available, otherwise use the prompt field
        user_content = prompt_content if prompt_content else req.get_request_prompt(request)

        # Check user input size at MCP transport boundary (excluding conversation history)
        validation_content = self.get_prompt_content_for_size_validation(user_content)
        size_check = self.check_prompt_size(validation_content)
        if size_check:
            raise ValueError(f"MCP_SIZE_CHECK:{ToolOutput(**size_check).model_dump_json()}")

        return user_content

    def get_chat_style_websearch_guidance(self) -> str:
        """
        Get Chat tool-style web search guidance.

        Returns web search guidance that matches the original Chat tool pattern.
        This is useful for tools that want to maintain the same search behavior.

        Returns:
            Web search guidance text
        """
        return """When discussing topics, consider if searches for these would help:
- Documentation for any technologies or concepts mentioned
- Current best practices and patterns
- Recent developments or updates
- Community discussions and solutions"""

    def get_actually_processed_files(self) -> list:
        """Get actually processed files. Override for custom file tracking."""
        try:
            return self._actually_processed_files
        except AttributeError:
            return []

    def _validate_file_paths(self, request) -> Optional[str]:
        """
        Validate that all file paths in the request are absolute paths.

        This is a security measure to prevent path traversal attacks and ensure
        proper access control. All file paths must be absolute (starting with '/').

        Args:
            request: The validated request object

        Returns:
            Optional[str]: Error message if validation fails, None if all paths are valid
        """
        # Check if request has absolute file paths attribute (legacy tools may still provide 'files')
        files = req.get_request_files(request)
        if files:
            for file_path in files:
                if not os.path.isabs(file_path):
                    return (
                        f"Error: All file paths must be FULL absolute paths to real files / folders - DO NOT SHORTEN. "
                        f"Received relative path: {file_path}\n"
                        f"Please provide the full absolute path starting with '/' (must be FULL absolute paths to real files / folders - DO NOT SHORTEN)"
                    )

        return None

    def prepare_chat_style_prompt(self, request, system_prompt: str = None) -> str:
        """
        Prepare a prompt using Chat tool-style patterns.

        This convenience method replicates the Chat tool's prompt preparation logic:
        1. Handle prompt.txt file if present
        2. Add file context with specific formatting
        3. Add web search guidance
        4. Format with system prompt

        Args:
            request: The validated request object
            system_prompt: System prompt to use (uses get_system_prompt() if None)

        Returns:
            Complete formatted prompt
        """
        # Use provided system prompt or get from tool
        if system_prompt is None:
            system_prompt = self.get_system_prompt()

        # Get user content (handles prompt.txt files)
        user_content = self.handle_prompt_file_with_fallback(request)

        # Build standard prompt with Chat-style web search guidance
        websearch_guidance = self.get_chat_style_websearch_guidance()

        # Override the websearch guidance temporarily
        original_guidance = self.get_websearch_guidance
        self.get_websearch_guidance = lambda: websearch_guidance

        try:
            full_prompt = self.build_standard_prompt(system_prompt, user_content, request, "CONTEXT FILES")
        finally:
            # Restore original guidance method
            self.get_websearch_guidance = original_guidance

        if system_prompt:
            marker = "\n\n=== USER REQUEST ===\n"
            if marker in full_prompt:
                _, user_section = full_prompt.split(marker, 1)
                return f"=== USER REQUEST ===\n{user_section}"

        return full_prompt

    def get_validated_temperature(self, request, model_context: Any) -> tuple[float, list[str]]:
        """
        Get temperature from request and validate it against model constraints.

        This is a convenience method that combines temperature extraction and validation.
        It ensures temperature is within valid range for the model.

        Args:
            request: The request object containing temperature
            model_context: Model context object containing model info

        Returns:
            Tuple of (validated_temperature, warning_messages)
        """
        temperature = req.get_request_temperature(request)
        if temperature is None:
            temperature = self.get_default_temperature()
        return self.validate_and_correct_temperature(temperature, model_context)

    # === REQUEST FIELD ACCESS METHODS ===
    # These delegate to the standalone functions in request_helpers but are
    # available as instance methods so subclasses can override them for
    # custom request handling.

    def get_request_model_name(self, request) -> Optional[str]:
        """Get model name from request. Override for custom model name handling."""
        return req.get_request_model_name(request)

    def get_request_images(self, request) -> list:
        """Get images from request. Override for custom image handling."""
        return req.get_request_images(request)

    def get_request_continuation_id(self, request) -> Optional[str]:
        """Get continuation_id from request. Override for custom continuation handling."""
        return req.get_request_continuation_id(request)

    def get_request_prompt(self, request) -> str:
        """Get prompt from request. Override for custom prompt handling."""
        return req.get_request_prompt(request)

    def get_request_temperature(self, request) -> Optional[float]:
        """Get temperature from request. Override for custom temperature handling."""
        return req.get_request_temperature(request)

    def get_request_thinking_mode(self, request) -> Optional[str]:
        """Get thinking_mode from request. Override for custom thinking mode handling."""
        return req.get_request_thinking_mode(request)

    def get_request_files(self, request) -> list:
        """Get absolute file paths from request. Override for custom file handling."""
        return req.get_request_files(request)

    def get_request_as_dict(self, request) -> dict:
        """Convert request to dictionary. Override for custom serialization."""
        return req.get_request_as_dict(request)

    def set_request_files(self, request, files: list) -> None:
        """Set absolute file paths on request. Override for custom file setting."""
        req.set_request_files(request, files)
