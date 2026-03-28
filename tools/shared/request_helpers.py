"""Request extraction helpers for PAL MCP tools.

Standalone functions for extracting fields from tool request objects,
replacing the hook methods previously on SimpleTool.
"""

from typing import Optional


def get_request_model_name(request) -> Optional[str]:
    """Get model name from request."""
    return getattr(request, "model", None)


def get_request_images(request) -> list:
    """Get images from request."""
    return getattr(request, "images", None) or []


def get_request_continuation_id(request) -> Optional[str]:
    """Get continuation_id from request."""
    return getattr(request, "continuation_id", None)


def get_request_prompt(request) -> str:
    """Get prompt from request."""
    return getattr(request, "prompt", "")


def get_request_temperature(request) -> Optional[float]:
    """Get temperature from request."""
    return getattr(request, "temperature", None)


def get_request_thinking_mode(request) -> Optional[str]:
    """Get thinking_mode from request."""
    return getattr(request, "thinking_mode", None)


def get_request_files(request) -> list:
    """Get absolute file paths from request."""
    return getattr(request, "absolute_file_paths", None) or []


def get_request_as_dict(request) -> dict:
    """Convert request to dictionary."""
    for method in ("model_dump", "dict"):
        fn = getattr(request, method, None)
        if fn is not None:
            return fn()
    return {"prompt": get_request_prompt(request)}


def set_request_files(request, files: list) -> None:
    """Set absolute file paths on request."""
    try:
        request.absolute_file_paths = files
    except AttributeError:
        pass


def get_request_use_assistant_model(request) -> bool:
    """Get use_assistant_model from request, defaulting to True."""
    val = getattr(request, "use_assistant_model", None)
    return val if val is not None else True
