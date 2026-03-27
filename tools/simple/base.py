"""Compatibility wrapper for legacy simple-tool imports.

Simple request/response behavior now lives directly on ``BaseTool`` so concrete
simple tools can inherit from the shared base class without an extra hierarchy
layer. ``SimpleTool`` remains as a thin compatibility shim for existing imports
and documentation.
"""

from tools.shared.base_tool import BaseTool
from tools.shared.schema_builders import SchemaBuilder


class SimpleTool(BaseTool):
    """Backward-compatible alias for the former simple-tool base class."""

    pass

