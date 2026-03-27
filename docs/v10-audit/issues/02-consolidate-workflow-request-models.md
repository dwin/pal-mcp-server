# Issue: Consolidate Workflow Request Models and Field Descriptions

**Labels**: `refactor`, `DRY`, `v10`
**Priority**: HIGH
**Estimated lines removed**: ~820

## Problem

11+ workflow tools define nearly identical request models (~500 lines duplicated) with the same fields (`step`, `step_number`, `total_steps`, `findings`, `files_checked`, `relevant_files`, `issues_found`, `confidence`, `images`, etc.) and the same `validate_step_one_requirements` model_validator.

Each tool also defines its own `*_FIELD_DESCRIPTIONS` dictionary (~300 lines duplicated) with near-identical descriptions for shared fields, varying only in minor wording.

Workflow tool `__init__` methods repeat the same boilerplate (`self.initial_request = None`, `self.tool_config = {}`).

## Key Files

- `tools/debug.py`, `tools/codereview.py`, `tools/refactor.py`, `tools/precommit.py`
- `tools/analyze.py`, `tools/docgen.py`, `tools/planner.py`, `tools/secaudit.py`
- `tools/testgen.py`, `tools/tracer.py`, `tools/thinkdeep.py`, `tools/consensus.py`

## Proposed Solution

1. Create `StandardWorkflowRequest` base class with all shared fields and the shared validator
2. Tools extend with **only** their custom fields (e.g., `RefactorRequest` adds `refactor_type`, `focus_areas`)
3. Create a `build_workflow_descriptions(activity, focus_area)` factory function with shared `WORKFLOW_CORE_FIELD_DESCRIPTIONS`
4. Set class-level defaults for `initial_request`/`tool_config` in WorkflowTool base

## Related Findings

- Audit Report 01 (DRY Auditor): Findings 1, 2, 7
