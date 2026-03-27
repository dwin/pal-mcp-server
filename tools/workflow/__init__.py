"""
Workflow tools for PAL MCP.

Workflow tools follow a multi-step pattern with forced pauses between steps
to encourage thorough investigation and analysis. They inherit from StatefulTool
which combines BaseTool with BaseWorkflowMixin.

StatefulTool was previously named WorkflowTool. The old name is still available
as a backward-compatibility alias.
"""

from .base import StatefulTool, WorkflowTool
from .schema_builders import WorkflowSchemaBuilder
from .workflow_mixin import BaseWorkflowMixin

__all__ = ["StatefulTool", "WorkflowTool", "WorkflowSchemaBuilder", "BaseWorkflowMixin"]
