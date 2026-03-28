"""
Standalone validation and file processing helper functions.

These functions are extracted from BaseTool and SimpleTool to allow reuse
without requiring a tool instance. Each function takes explicit parameters
instead of relying on ``self``.
"""

import base64
import logging
import os
from pathlib import Path
from typing import Any, Callable, Optional

from config import MCP_PROMPT_SIZE_LIMIT
from utils import estimate_tokens
from utils.conversation_memory import get_conversation_file_list, get_thread
from utils.file_utils import expand_paths, read_file_content, read_files

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. validate_file_paths  (from BaseTool.validate_file_paths)
# ---------------------------------------------------------------------------


def validate_file_paths(request) -> Optional[str]:
    """
    Validate that all file paths in the request are absolute.

    This is a critical security function that prevents path traversal attacks
    and ensures all file access is properly controlled. All file paths must
    be absolute to avoid ambiguity and security issues.

    Args:
        request: The validated request object.  Checked attributes include
            ``absolute_file_paths``, ``file``, ``path``, ``directory``,
            ``notebooks``, ``test_examples``, ``style_guide_examples``,
            ``files_checked``, and ``relevant_files``.

    Returns:
        Error message if validation fails, ``None`` if all paths are valid.
    """
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


# ---------------------------------------------------------------------------
# 2. validate_file_paths_simple  (from SimpleTool._validate_file_paths)
# ---------------------------------------------------------------------------


def validate_file_paths_simple(
    request,
    get_files_fn: Callable,
    set_files_fn: Callable,
) -> Optional[str]:
    """
    Validate that all file paths in the request are absolute paths.

    This is a security measure to prevent path traversal attacks and ensure
    proper access control.  All file paths must be absolute (starting with
    ``/``).

    Args:
        request: The validated request object.
        get_files_fn: Callable that accepts *request* and returns the list
            of file paths (may return ``[]``).
        set_files_fn: Callable that accepts *(request, files)* and sets
            the file paths on the request.  (Unused in the current logic
            but kept for API symmetry with the original method.)

    Returns:
        Error message if validation fails, ``None`` if all paths are valid.
    """
    files = get_files_fn(request)
    if files:
        for file_path in files:
            if not os.path.isabs(file_path):
                return (
                    f"Error: All file paths must be FULL absolute paths to real files / folders - DO NOT SHORTEN. "
                    f"Received relative path: {file_path}\n"
                    f"Please provide the full absolute path starting with '/' "
                    f"(must be FULL absolute paths to real files / folders - DO NOT SHORTEN)"
                )

    return None


# ---------------------------------------------------------------------------
# 3. validate_token_limit  (from BaseTool._validate_token_limit)
# ---------------------------------------------------------------------------


def validate_token_limit(
    content: str,
    content_type: str = "Content",
    tool_name: str = "unknown",
    size_limit: int = MCP_PROMPT_SIZE_LIMIT,
) -> None:
    """
    Validate that user-provided content doesn't exceed the MCP prompt size limit.

    This enforcement is strictly for text crossing the MCP transport boundary
    (i.e., user input).  Internal prompt construction may exceed this size
    and is governed by model-specific token limits.

    Args:
        content: The user-originated content to validate.
        content_type: Description of the content type for error messages.
        tool_name: Name of the tool performing validation (used in log messages).
        size_limit: Maximum allowed character count.

    Raises:
        ValueError: If *content* exceeds the character size limit.
    """
    if not content:
        logger.debug(f"{tool_name} tool {content_type.lower()} validation skipped (no content)")
        return

    char_count = len(content)
    if char_count > size_limit:
        token_estimate = estimate_tokens(content)
        error_msg = f"{char_count:,} characters (~{token_estimate:,} tokens). " f"Maximum is {size_limit:,} characters."
        logger.error(f"{tool_name} tool {content_type.lower()} validation failed: {error_msg}")
        raise ValueError(f"{content_type} too large: {error_msg}")

    token_estimate = estimate_tokens(content)
    logger.debug(
        f"{tool_name} tool {content_type.lower()} validation passed: "
        f"{char_count:,} characters (~{token_estimate:,} tokens)"
    )


# ---------------------------------------------------------------------------
# 4. validate_image_limits  (from BaseTool._validate_image_limits)
# ---------------------------------------------------------------------------


def validate_image_limits(
    images: Optional[list[str]],
    model_context: Optional[Any],
    tool_name: str = "unknown",
) -> Optional[dict]:
    """
    Validate image size and count against model capabilities.

    This performs strict validation to ensure we don't exceed model-specific
    image limits.  Uses capability-based validation with actual model
    configuration rather than hard-coded limits.

    Args:
        images: List of image paths / data URLs to validate.
        model_context: Model context object containing model name, provider,
            and capabilities.
        tool_name: Name of the tool performing validation (used in log/error
            messages).

    Returns:
        Error response dict if validation fails, ``None`` if valid.
    """
    if not images:
        return None

    if not model_context:
        logger.warning("No model context available for image validation")
        return None

    try:
        capabilities = model_context.capabilities
        model_name = model_context.model_name
    except Exception as e:
        logger.warning(f"Failed to get capabilities from model_context for image validation: {e}")
        model_name = getattr(model_context, "model_name", "unknown")
        return {
            "status": "error",
            "content": (
                f"Model '{model_name}' is not available or not recognized. "
                "Please check available models and try again."
            ),
            "content_type": "text",
            "metadata": {
                "error_type": "validation_error",
                "model_name": model_name,
                "supports_images": None,
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
                    total_size_mb += 1.0  # 1MB assumption
        except Exception as e:
            logger.warning(f"Failed to get size for image {image_path}: {e}")
            total_size_mb += 1.0  # 1MB assumption

    # Apply 40MB cap for custom models if needed
    effective_limit_mb = max_size_mb
    try:
        from providers.shared import ProviderType

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


# ---------------------------------------------------------------------------
# 5. check_prompt_size  (from BaseTool.check_prompt_size)
# ---------------------------------------------------------------------------


def check_prompt_size(
    text: str,
    size_limit: int = MCP_PROMPT_SIZE_LIMIT,
) -> Optional[dict[str, Any]]:
    """
    Check if USER INPUT text is too large for MCP transport boundary.

    IMPORTANT: This function should ONLY be used to validate user input that
    crosses the CLI -> MCP Server transport boundary.  It should NOT be used
    to limit internal MCP Server operations.

    Args:
        text: The user input text to check (NOT internal prompt content).
        size_limit: Maximum allowed character count.

    Returns:
        Response dict asking for file handling if too large, ``None`` otherwise.
    """
    if text and len(text) > size_limit:
        return {
            "status": "resend_prompt",
            "content": (
                f"MANDATORY ACTION REQUIRED: The prompt is too large for MCP's token limits "
                f"(>{size_limit:,} characters). "
                "YOU MUST IMMEDIATELY save the prompt text to a temporary file named 'prompt.txt' "
                "in the working directory. "
                "DO NOT attempt to shorten or modify the prompt. SAVE IT AS-IS to 'prompt.txt'. "
                "Then resend the request, passing the absolute file path to 'prompt.txt' as part "
                "of the tool call, along with any other files you wish to share as context. "
                "Leave the prompt text itself empty or very brief in the new request. "
                "This is the ONLY way to handle large prompts - you MUST follow these exact steps."
            ),
            "content_type": "text",
            "metadata": {
                "prompt_size": len(text),
                "limit": size_limit,
                "instructions": (
                    "MANDATORY: Save prompt to 'prompt.txt' in current folder and "
                    "provide full path when recalling this tool."
                ),
            },
        }
    return None


# ---------------------------------------------------------------------------
# 6. prepare_file_content_for_prompt  (from BaseTool._prepare_file_content_for_prompt)
# ---------------------------------------------------------------------------


def prepare_file_content_for_prompt(
    request_files: list[str],
    continuation_id: Optional[str],
    tool_name: str,
    context_description: str = "New files",
    max_tokens: Optional[int] = None,
    reserve_tokens: int = 1_000,
    remaining_budget: Optional[int] = None,
    arguments: Optional[dict] = None,
    model_context: Optional[Any] = None,
    filter_new_files_fn: Optional[Callable] = None,
    wants_line_numbers: bool = True,
) -> tuple[str, list[str]]:
    """
    Centralised file processing implementing the dual prioritisation strategy.

    This function is the heart of conversation-aware file processing across
    all tools.

    Args:
        request_files: List of files requested for current tool execution.
        continuation_id: Thread continuation ID, or ``None`` for new
            conversations.
        tool_name: Name of the calling tool (used for logging).
        context_description: Description for token limit validation (e.g.
            ``"Code"``, ``"New files"``).
        max_tokens: Maximum tokens to use (defaults to remaining budget or
            model-specific content allocation).
        reserve_tokens: Tokens to reserve for additional prompt content
            (default 1K).
        remaining_budget: Remaining token budget after conversation history
            (from ``server.py``).
        arguments: Original tool arguments (used to extract
            ``_remaining_tokens`` if available).
        model_context: Model context object with all model information
            including token allocation.
        filter_new_files_fn: Callable ``(requested_files, continuation_id)``
            that returns the list of files not yet embedded.  Defaults to
            :func:`filter_new_files`.
        wants_line_numbers: Whether to include line numbers in file output.

    Returns:
        ``(formatted_file_content, actually_processed_files)`` -- the
        formatted string ready for prompt inclusion and the list of
        individual file paths that were actually read and embedded.
    """
    if not request_files:
        return "", []

    # Default filter function
    if filter_new_files_fn is None:

        def filter_new_files_fn(files, cid):
            return filter_new_files(files, cid, tool_name)

    # Extract remaining budget from arguments if available
    if remaining_budget is None:
        args_to_use = arguments or {}
        remaining_budget = args_to_use.get("_remaining_tokens")

    # Use remaining budget if provided, otherwise fall back to max_tokens or model-specific default
    if remaining_budget is not None:
        effective_max_tokens = remaining_budget - reserve_tokens
    elif max_tokens is not None:
        effective_max_tokens = max_tokens - reserve_tokens
    else:
        if not model_context:
            logger.error(
                f"[FILES] {tool_name}: prepare_file_content_for_prompt called without model_context. "
                "This indicates an incorrect call sequence in the tool's implementation."
            )
            raise RuntimeError("Model context not provided for file preparation.")

        try:
            token_allocation = model_context.calculate_token_allocation()
            effective_max_tokens = token_allocation.file_tokens - reserve_tokens
            logger.debug(
                f"[FILES] {tool_name}: Using model context for {model_context.model_name}: "
                f"{token_allocation.file_tokens:,} file tokens from {token_allocation.total_tokens:,} total"
            )
        except Exception as e:
            logger.error(
                f"[FILES] {tool_name}: Failed to calculate token allocation from model context: {e}",
                exc_info=True,
            )
            effective_max_tokens = 100_000 - reserve_tokens

    # Ensure we have a reasonable minimum budget
    effective_max_tokens = max(1000, effective_max_tokens)

    files_to_embed = filter_new_files_fn(request_files, continuation_id)
    logger.debug(f"[FILES] {tool_name}: Will embed {len(files_to_embed)} files after filtering")

    if files_to_embed:
        logger.info(
            f"[FILE_PROCESSING] {tool_name} tool will embed new files: "
            f"{', '.join([os.path.basename(f) for f in files_to_embed])}"
        )
    else:
        logger.info(
            f"[FILE_PROCESSING] {tool_name} tool: No new files to embed " f"(all files already in conversation history)"
        )

    content_parts: list[str] = []
    actually_processed_files: list[str] = []

    # Read content of new files only
    if files_to_embed:
        logger.debug(f"{tool_name} tool embedding {len(files_to_embed)} new files: {', '.join(files_to_embed)}")
        logger.debug(
            f"[FILES] {tool_name}: Starting file embedding with token budget "
            f"{effective_max_tokens + reserve_tokens:,}"
        )
        try:
            expanded_files = expand_paths(files_to_embed)
            logger.debug(
                f"[FILES] {tool_name}: Expanded {len(files_to_embed)} paths to "
                f"{len(expanded_files)} individual files"
            )

            file_content = read_files(
                files_to_embed,
                max_tokens=effective_max_tokens + reserve_tokens,
                reserve_tokens=reserve_tokens,
                include_line_numbers=wants_line_numbers,
            )
            content_parts.append(file_content)
            actually_processed_files.extend(expanded_files)

            from utils.token_utils import estimate_tokens as _estimate_tokens

            content_tokens = _estimate_tokens(file_content)
            logger.debug(
                f"{tool_name} tool successfully embedded {len(files_to_embed)} files " f"({content_tokens:,} tokens)"
            )
            logger.debug(f"[FILES] {tool_name}: Successfully embedded files - {content_tokens:,} tokens used")
            logger.debug(f"[FILES] {tool_name}: Actually processed {len(actually_processed_files)} individual files")
        except Exception as e:
            logger.error(f"{tool_name} tool failed to embed files {files_to_embed}: {type(e).__name__}: {e}")
            logger.debug(f"[FILES] {tool_name}: File embedding failed - {type(e).__name__}: {e}")
            raise
    else:
        logger.debug(f"[FILES] {tool_name}: No files to embed after filtering")

    # Generate note about files already in conversation history
    if continuation_id and len(files_to_embed) < len(request_files):
        embedded_files = get_conversation_embedded_files(continuation_id, tool_name)
        skipped_files = [f for f in request_files if f in embedded_files]
        if skipped_files:
            logger.debug(
                f"{tool_name} tool skipping {len(skipped_files)} files already in conversation history: "
                f"{', '.join(skipped_files)}"
            )
            logger.debug(f"[FILES] {tool_name}: Adding note about {len(skipped_files)} skipped files")
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
            logger.debug(f"[FILES] {tool_name}: No skipped files to note")

    result = "".join(content_parts) if content_parts else ""
    logger.debug(
        f"[FILES] {tool_name}: prepare_file_content_for_prompt returning "
        f"{len(result)} chars, {len(actually_processed_files)} processed files"
    )
    return result, actually_processed_files


# ---------------------------------------------------------------------------
# 7. filter_new_files  (from BaseTool.filter_new_files)
# ---------------------------------------------------------------------------


def filter_new_files(
    requested_files: list[str],
    continuation_id: Optional[str],
    tool_name: str = "unknown",
    get_embedded_fn: Optional[Callable] = None,
) -> list[str]:
    """
    Filter out files that are already embedded in conversation history.

    This prevents duplicate file embeddings by filtering out files that have
    already been embedded in the conversation history, optimising token usage
    while ensuring tools still have logical access to all requested files
    through conversation history references.

    Args:
        requested_files: List of files requested for current tool execution.
        continuation_id: Thread continuation ID, or ``None`` for new
            conversations.
        tool_name: Name of the calling tool (used in log messages).
        get_embedded_fn: Callable ``(continuation_id)`` returning a list of
            already-embedded file paths.  Defaults to
            :func:`get_conversation_embedded_files`.

    Returns:
        List of files that need to be embedded (not already in history).
    """
    logger.debug(f"[FILES] {tool_name}: Filtering {len(requested_files)} requested files")

    if not continuation_id:
        logger.debug(f"[FILES] {tool_name}: New conversation, all {len(requested_files)} files are new")
        return requested_files

    if get_embedded_fn is None:

        def get_embedded_fn(cid):
            return get_conversation_embedded_files(cid, tool_name)

    try:
        embedded_files = set(get_embedded_fn(continuation_id))
        logger.debug(f"[FILES] {tool_name}: Found {len(embedded_files)} embedded files in conversation")

        if not embedded_files:
            logger.debug(f"{tool_name} tool: No files found in conversation history for thread {continuation_id}")
            logger.debug(
                f"[FILES] {tool_name}: No embedded files found, returning all "
                f"{len(requested_files)} requested files"
            )
            return requested_files

        new_files = [f for f in requested_files if f not in embedded_files]
        logger.debug(
            f"[FILES] {tool_name}: After filtering: {len(new_files)} new files, "
            f"{len(requested_files) - len(new_files)} already embedded"
        )
        logger.debug(f"[FILES] {tool_name}: New files to embed: {new_files}")

        if len(new_files) < len(requested_files):
            skipped = [f for f in requested_files if f in embedded_files]
            logger.debug(
                f"{tool_name} tool: Filtering {len(skipped)} files already in conversation history: "
                f"{', '.join(skipped)}"
            )
            logger.debug(f"[FILES] {tool_name}: Skipped (already embedded): {skipped}")

        return new_files

    except Exception as e:
        logger.warning(f"{tool_name} tool: Error checking conversation history for {continuation_id}: {e}")
        logger.warning(f"{tool_name} tool: Including all requested files as fallback")
        logger.debug(
            f"[FILES] {tool_name}: Exception in filter_new_files, returning all "
            f"{len(requested_files)} files as fallback"
        )
        return requested_files


# ---------------------------------------------------------------------------
# 8. get_conversation_embedded_files  (from BaseTool.get_conversation_embedded_files)
# ---------------------------------------------------------------------------


def get_conversation_embedded_files(
    continuation_id: Optional[str],
    tool_name: str = "unknown",
) -> list[str]:
    """
    Get list of files already embedded in conversation history.

    Args:
        continuation_id: Thread continuation ID, or ``None`` for new
            conversations.
        tool_name: Name of the calling tool (used in log messages).

    Returns:
        List of file paths already embedded in conversation history.
    """
    if not continuation_id:
        return []

    thread_context = get_thread(continuation_id)
    if not thread_context:
        return []

    embedded_files = get_conversation_file_list(thread_context)
    logger.debug(f"[FILES] {tool_name}: Found {len(embedded_files)} embedded files")
    return embedded_files


# ---------------------------------------------------------------------------
# 9. handle_prompt_file  (from BaseTool.handle_prompt_file)
# ---------------------------------------------------------------------------


def handle_prompt_file(
    files: Optional[list[str]],
) -> tuple[Optional[str], Optional[list[str]]]:
    """
    Check for and handle ``prompt.txt`` in the absolute file paths list.

    If ``prompt.txt`` is found, reads its content and removes it from the
    files list.  This file is treated specially as the main prompt, not as
    an embedded file.

    This mechanism allows us to work around MCP's ~25K token limit by having
    the CLI save large prompts to a file, effectively using the file transfer
    mechanism to bypass token constraints while preserving response capacity.

    Args:
        files: List of absolute file paths.

    Returns:
        ``(prompt_content, updated_files_list)``
    """
    if not files:
        return None, files

    prompt_content = None
    updated_files: list[str] = []

    for file_path in files:
        # Check if the filename is exactly "prompt.txt"
        # This ensures we don't match files like "myprompt.txt" or "prompt.txt.bak"
        if os.path.basename(file_path) == "prompt.txt":
            try:
                content, _ = read_file_content(file_path)
                # Extract the content between the file markers
                if "--- BEGIN FILE:" in content and "--- END FILE:" in content:
                    lines = content.split("\n")
                    in_content = False
                    content_lines: list[str] = []
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
                pass
        else:
            updated_files.append(file_path)

    return prompt_content, updated_files if updated_files else None


# ---------------------------------------------------------------------------
# 10. get_websearch_instruction  (from BaseTool.get_websearch_instruction)
# ---------------------------------------------------------------------------


def get_websearch_instruction(tool_specific: Optional[str] = None) -> str:
    """
    Generate standardised web search instruction.

    Args:
        tool_specific: Optional tool-specific search guidance.

    Returns:
        Web search instruction to append to prompt.
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
