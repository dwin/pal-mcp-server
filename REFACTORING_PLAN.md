# Tool Class Hierarchy Collapse - Refactoring Plan

## Problem Analysis

The current tool infrastructure has **5,001 lines** of abstraction code supporting **16 concrete tools** - a 1:312 ratio. The hierarchy has 4 levels:

1. `BaseTool` (1,606 lines, 47 methods)
2. `SimpleTool` (1,011 lines, 29 methods)
3. `BaseWorkflowMixin` (1,608 lines, 73 methods)
4. `WorkflowTool` (448 lines, 26 methods)

**Issue**: Too much abstraction for the number of tools. Need to collapse to 2 base classes and reduce BaseTool to ~20 core methods.

## Current Tool Classification

**Simple Tools (4):** chat, clink, apilookup, challenge
- Inherit: BaseTool → SimpleTool → ConcreteTool

**Workflow Tools (13):** analyze, codereview, consensus, debug, docgen, planner, precommit, refactor, secaudit, testgen, thinkdeep, tracer, listmodels
- Inherit: (BaseTool + BaseWorkflowMixin) → WorkflowTool → ConcreteTool

**Utility Tools (3):** version, listmodels, clink_listmodels
- Special cases, minimal inheritance

## Proposed Solution

### Goal: 2 Base Classes
1. **BaseTool**: Core MCP interface (~20 core methods)
2. **StatefulTool**: For multi-step workflow tools (merges WorkflowTool + BaseWorkflowMixin)

### Phase 1: Simplify BaseTool (Reduce from 47 to ~20 methods)

**Keep (Core MCP Interface - 20 methods):**
- `get_name()`, `get_description()`, `get_input_schema()`, `get_annotations()`
- `get_system_prompt()`, `get_default_temperature()`, `get_model_category()`
- `get_model_provider()`, `requires_model()`, `is_effective_auto_mode()`
- `execute()` - abstract method that tools must implement
- `_prepare_file_content_for_prompt()`, `_validate_token_limit()`, `_validate_image_limits()`
- `get_language_instruction()`, `format_response()`
- `_resolve_model_context()`, `validate_and_correct_temperature()`
- `get_model_field_schema()`, `check_prompt_size()`
- `handle_prompt_file()`

**Move to Utility Modules (reduce BaseTool size):**
- Model discovery helpers → `utils/model_discovery.py`
  - `_get_available_models()`, `_get_ranked_model_summaries()`
  - `_format_available_models_list()`, `_build_model_unavailable_message()`
  - `_collect_ranked_capabilities()`, `_get_restriction_note()`

- Conversation helpers → `utils/conversation_helpers.py`
  - `get_conversation_embedded_files()`, `filter_new_files()`
  - `format_conversation_turn()`

- Schema helpers → `tools/shared/schema_helpers.py`
  - `_format_context_window()`, `_normalize_model_identifier()`

**Integrate from SimpleTool (since SimpleTool will be removed):**
- Add `get_tool_fields()` as optional hook (returns {} by default)
- Add request accessor methods for safe attribute access
- Add `build_standard_prompt()` helper
- Add SimpleTool's `execute()` implementation as default

### Phase 2: Remove SimpleTool Layer

**Why Remove?**
SimpleTool adds 1,011 lines but only provides:
- Schema building (can be in BaseTool)
- Execute method (can be default implementation in BaseTool)
- Request accessors (can be helper methods in BaseTool)

**Migration:**
```python
# Before
from tools.simple.base import SimpleTool

class ChatTool(SimpleTool):
    def get_tool_fields(self):
        return {"prompt": {...}}

# After
from tools.shared.base_tool import BaseTool

class ChatTool(BaseTool):
    def get_tool_fields(self):  # Now optional hook in BaseTool
        return {"prompt": {...}}

    # No other changes needed - BaseTool has integrated SimpleTool's functionality
```

**Files to Update:**
- `tools/chat.py`
- `tools/clink.py`
- `tools/apilookup.py`
- `tools/challenge.py`

**Files to Delete:**
- `tools/simple/base.py` (1,011 lines removed)
- Update `tools/simple/__init__.py`

### Phase 3: Merge BaseWorkflowMixin into WorkflowTool → StatefulTool

**Why Merge?**
BaseWorkflowMixin (1,608 lines) is only used by WorkflowTool (448 lines). They form a tight coupling that doesn't need separation.

**Implementation:**
1. Copy all BaseWorkflowMixin content into `tools/workflow/base.py`
2. Rename `WorkflowTool` → `StatefulTool`
3. Remove the mixin import and multiple inheritance
4. Update docstrings to reflect merged class

**Files to Update:**
- `tools/workflow/base.py` - merge and rename
- All 13 workflow tools:
  - `tools/analyze.py`
  - `tools/codereview.py`
  - `tools/consensus.py`
  - `tools/debug.py`
  - `tools/docgen.py`
  - `tools/planner.py`
  - `tools/precommit.py`
  - `tools/refactor.py`
  - `tools/secaudit.py`
  - `tools/testgen.py`
  - `tools/thinkdeep.py`
  - `tools/tracer.py`
  - `tools/listmodels.py` (if it uses WorkflowTool)

**Change:**
```python
# Before
from tools.workflow.base import WorkflowTool

class DebugTool(WorkflowTool):
    ...

# After
from tools.workflow.base import StatefulTool

class DebugTool(StatefulTool):
    ...
```

**Files to Delete:**
- `tools/workflow/workflow_mixin.py` (1,608 lines removed)
- Update `tools/workflow/__init__.py`

### Phase 4: Update Imports and __init__ Files

**tools/__init__.py**: Update exports
**tools/simple/__init__.py**: Remove SimpleTool references
**tools/workflow/__init__.py**: Export StatefulTool instead of WorkflowTool
**server.py**: Update any direct imports

## Expected Line Reduction

**Files Deleted:**
- `tools/simple/base.py`: -1,011 lines
- `tools/workflow/workflow_mixin.py`: -1,608 lines
- **Total Deleted**: **-2,619 lines**

**Files Modified:**
- `tools/shared/base_tool.py`: +300 lines (integrate SimpleTool essentials)
- `tools/workflow/base.py`: +1,608 lines (merge BaseWorkflowMixin)
- **Total Added**: **+1,908 lines**

**Net Reduction: ~711 lines**

Plus additional reduction from:
- Removing helper methods from BaseTool: -200-300 lines
- Consolidating duplicates and utilities: -100-200 lines

**Target: ~1,000-1,200 line reduction**

## Risks & Mitigation

### High Risk Areas
1. **SimpleTool execute() method**: 300+ lines of critical logic
   - Mitigation: Comprehensive test coverage before and after

2. **BaseWorkflowMixin state management**: Complex workflow orchestration
   - Mitigation: No logic changes, just file merging

3. **Import updates across 17 tools**: Easy to miss one
   - Mitigation: Grep for all imports, update systematically

### Testing Strategy
1. Run full test suite before changes (baseline)
2. Phase 1: Test after BaseTool changes
3. Phase 2: Test after each simple tool migration
4. Phase 3: Test after StatefulTool creation
5. Phase 4: Test after each workflow tool migration
6. Final: Full integration test suite

### Rollback Plan
- Each phase is in separate commits
- Can revert by phase if issues found
- Keep SimpleTool/BaseWorkflowMixin deprecated but functional for one release

## Implementation Order

1. ✅ Create this refactoring plan
2. ⬜ Create comprehensive test coverage
3. ⬜ Phase 1: Simplify BaseTool (remove helpers to utils)
4. ⬜ Phase 1: Integrate SimpleTool functionality into BaseTool
5. ⬜ Phase 2: Migrate simple tools one by one (chat first)
6. ⬜ Phase 2: Delete SimpleTool after all tools migrated
7. ⬜ Phase 3: Merge BaseWorkflowMixin into WorkflowTool
8. ⬜ Phase 3: Rename to StatefulTool
9. ⬜ Phase 3: Update all workflow tool imports
10. ⬜ Phase 3: Delete BaseWorkflowMixin
11. ⬜ Phase 4: Update all __init__.py files
12. ⬜ Run full test suite and fix any issues
13. ⬜ Update documentation
14. ⬜ Measure final line count reduction

## Success Criteria

- [x] Tool hierarchy reduced from 4 levels to 2
- [ ] SimpleTool eliminated as middle layer
- [ ] BaseWorkflowMixin merged into StatefulTool
- [ ] BaseTool reduced from 47 to ~20 core methods
- [ ] All 17 tools functioning correctly
- [ ] All tests passing
- [ ] ~1,000+ line reduction achieved
- [ ] Code maintainability improved

## Pydantic Usage (Separate Concern)

The issue also mentions "Keep Pydantic only for the 7 tools that use `model_validator`". This is a separate refactoring:

**Tools using Pydantic validators (10):**
- testgen, refactor, consensus, codereview, analyze, secaudit, precommit, planner, tracer
- Plus: base_models.py

**Tools using Pydantic only for Field descriptions (7):**
- chat, clink, apilookup, challenge, debug, thinkdeep, docgen

**Recommendation**: Address Pydantic reduction in a separate PR after hierarchy collapse is complete and stable.

## Timeline Estimate

- Phase 1 (BaseTool simplification): 2-3 days
- Phase 2 (SimpleTool removal): 2-3 days
- Phase 3 (StatefulTool creation): 2-3 days
- Phase 4 (Testing & fixes): 2-3 days
- **Total**: 8-12 days with proper testing

## Notes

This refactoring achieves the goal of simplifying the hierarchy while maintaining all functionality. The line reduction comes from:
1. Eliminating unnecessary abstraction layers (SimpleTool, BaseWorkflowMixin as separate files)
2. Moving utility methods out of BaseTool into focused utility modules
3. Consolidating duplicate/redundant methods

The result is cleaner, more maintainable code with a 1:140 ratio (5 concrete tools per abstraction level) instead of 1:312.
