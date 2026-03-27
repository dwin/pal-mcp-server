# Issue: Collapse Tool Class Hierarchy

**Labels**: `refactor`, `architecture`, `v10`
**Priority**: HIGH
**Estimated lines removed**: ~1,500

## Problem

The tool infrastructure has 5,085 lines of abstraction code to support only 19 concrete tools — a 1:267 ratio. There are 4+ inheritance levels (BaseTool -> SimpleTool -> WorkflowTool -> ConcreteTool) with 49 methods in BaseTool alone.

Additionally, Pydantic is used heavily (18 files) but only 7 actually use `model_validator` — the rest use `Field()` purely for descriptions, which stdlib `TypedDict` or `dataclasses` could handle.

**Current hierarchy**:
- `BaseTool`: 1,606 lines
- `SimpleTool`: 1,011 lines
- `BaseWorkflowMixin`: 1,608 lines
- `WorkflowTool`: 448 lines
- `SchemaBuilder` variants: 328 lines

## Key Files

- `tools/shared/base_tool.py`
- `tools/simple/base.py`
- `tools/workflow/workflow_mixin.py`
- `tools/workflow/workflow_tool.py`

## Proposed Solution

1. Collapse to 2 base classes: `BaseTool` (core MCP interface) and `StatefulTool` (for workflow tools)
2. Remove `SimpleTool` as unnecessary middle layer
3. Reduce BaseTool from 49 to ~20 core methods
4. Keep Pydantic only for the 7 tools that use `model_validator`; use TypedDict for the rest

## Related Findings

- Audit Report 02 (Dependency Minimalist): Finding 1, Finding 6
