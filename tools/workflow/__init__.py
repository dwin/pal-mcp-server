"""
Workflow tools for PAL MCP.

Workflow tools follow a multi-step pattern with forced pauses between steps
to encourage thorough investigation and analysis. They inherit from StatefulTool
which provides workflow orchestration on top of BaseTool.

Available workflow tools:
- debug: Systematic investigation and root cause analysis
- planner: Sequential planning (special case - no AI calls)
- analyze: Code analysis workflow
- codereview: Code review workflow
- precommit: Pre-commit validation workflow
- refactor: Refactoring analysis workflow
- thinkdeep: Deep thinking workflow
"""

from .schema_builders import WorkflowSchemaBuilder
from .stateful_tool import StatefulTool

# Backward compatibility alias — the old WorkflowTool(BaseTool, BaseWorkflowMixin)
# pattern is replaced by inheriting from StatefulTool directly.
# BaseWorkflowMixin is intentionally NOT aliased here because
# StatefulTool already inherits from BaseTool; aliasing it as a
# "mixin" would cause MRO errors if someone tried the old
# `class X(BaseTool, BaseWorkflowMixin)` pattern.
WorkflowTool = StatefulTool

__all__ = ["StatefulTool", "WorkflowTool", "WorkflowSchemaBuilder"]
