"""
Simple tools for PAL MCP.

Simple tools now inherit directly from BaseTool.
This module provides backward compatibility.
"""

from tools.shared.base_tool import BaseTool

# Backward compatibility alias
SimpleTool = BaseTool

__all__ = ["SimpleTool"]
