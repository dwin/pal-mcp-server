"""Request extraction helpers for PAL MCP tools.

Standalone functions for extracting fields from tool request objects,
replacing the hook methods previously on SimpleTool.
"""

from typing import Optional


def get_request_model_name(request) -> Optional[str]:
    """Get model name from request."""
    try:
        return request.model
    except AttributeError:
        return None


def get_request_images(request) -> list:
    """Get images from request."""
    try:
        return request.images if request.images is not None else []
    except AttributeError:
        return []


def get_request_continuation_id(request) -> Optional[str]:
    """Get continuation_id from request."""
    try:
        return request.continuation_id
    except AttributeError:
        return None


def get_request_prompt(request) -> str:
    """Get prompt from request."""
    try:
        return request.prompt
    except AttributeError:
        return ""


def get_request_temperature(request) -> Optional[float]:
    """Get temperature from request."""
    try:
        return request.temperature
    except AttributeError:
        return None


def get_request_thinking_mode(request) -> Optional[str]:
    """Get thinking_mode from request."""
    try:
        return request.thinking_mode
    except AttributeError:
        return None


def get_request_files(request) -> list:
    """Get absolute file paths from request."""
    try:
        files = request.absolute_file_paths
    except AttributeError:
        files = None
    if files is None:
        return []
    return files


def get_request_as_dict(request) -> dict:
    """Convert request to dictionary."""
    try:
        return request.model_dump()
    except AttributeError:
        try:
            return request.dict()
        except AttributeError:
            return {"prompt": get_request_prompt(request)}


def set_request_files(request, files: list) -> None:
    """Set absolute file paths on request."""
    try:
        request.absolute_file_paths = files
    except AttributeError:
        pass


def get_request_use_assistant_model(request) -> bool:
    """Get use_assistant_model from request, defaulting to True."""
    try:
        val = request.use_assistant_model
        return val if val is not None else True
    except AttributeError:
        return True
