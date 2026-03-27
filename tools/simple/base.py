"""
Backward-compatibility shim.

SimpleTool has been merged into BaseTool as part of the v10 hierarchy collapse.
This module preserves the import path for existing code.
"""

from tools.shared.base_tool import BaseTool
from tools.shared.schema_builders import SchemaBuilder

# SimpleTool is now just BaseTool
SimpleTool = BaseTool

__all__ = ["SimpleTool", "SchemaBuilder"]
