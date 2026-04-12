"""Shared type definitions used across providers and tools.

This module exists to break circular imports between the ``tools`` and
``providers`` packages.  Types placed here must have **no** dependencies
on either package.
"""

from enum import Enum

__all__ = ["ToolModelCategory"]


class ToolModelCategory(Enum):
    """Categories for tool model selection based on requirements."""

    EXTENDED_REASONING = "extended_reasoning"  # Requires deep thinking capabilities
    FAST_RESPONSE = "fast_response"  # Speed and cost efficiency preferred
    BALANCED = "balanced"  # Balance of capability and performance
