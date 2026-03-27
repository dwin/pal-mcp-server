"""
Backward-compatibility shim for simple tools.

SimpleTool has been merged into BaseTool. This module preserves the import path.
"""

from tools.shared.base_tool import BaseTool as SimpleTool

__all__ = ["SimpleTool"]
