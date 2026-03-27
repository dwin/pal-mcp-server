# PAL MCP Server: DRY Code Audit Report

**Agent**: DRY Auditor
**Focus**: Duplicated code, repeated patterns, copy-paste logic

## Executive Summary

The codebase shows good architectural patterns with base classes and mixins, but contains **significant duplication** in workflow tool request models, schema generation, request field accessors, and provider template methods. Consolidation could eliminate ~1,500+ lines.

---

## 1. Workflow Tool Request Models (HIGH IMPACT)

**Files**: 11+ workflow tools (`debug.py`, `codereview.py`, `refactor.py`, `precommit.py`, `analyze.py`, `docgen.py`, `planner.py`, `secaudit.py`, `testgen.py`, `tracer.py`, `thinkdeep.py`, `consensus.py`)

All workflow tools define nearly identical request models with duplicated field definitions:
- `step`, `step_number`, `total_steps`, `next_step_required`
- `findings`, `files_checked`, `relevant_files`, `relevant_context`, `issues_found`
- `confidence`, `images`, `temperature`, `thinking_mode`
- Identical `validate_step_one_requirements` model_validator

**~500 lines duplicated across 11 files.**

**Suggestion**: Create a `StandardWorkflowRequest` base class. Tools extend with **only** their custom fields:
```python
class RefactorRequest(StandardWorkflowRequest):
    refactor_type: Optional[Literal["codesmells", "decompose", "modernize"]] = Field(...)
    focus_areas: Optional[list[str]] = Field(...)
```

---

## 2. Field Description Dictionaries (MEDIUM)

**Files**: 11+ workflow tools each define their own `*_FIELD_DESCRIPTIONS` dict

Each tool repeats near-identical descriptions for shared fields (`step`, `findings`, `files_checked`, etc.) with only minor wording variations.

**~300 lines of duplication.**

**Suggestion**: Create a factory function `build_workflow_descriptions(activity, focus_area)` that generates tool-specific descriptions from templates, with a shared `WORKFLOW_CORE_FIELD_DESCRIPTIONS` base.

---

## 3. Request Field Accessor Methods (HIGH)

**Files**: `tools/simple/base.py` (lines 171-241), `tools/workflow/workflow_mixin.py`, `tools/thinkdeep.py`, `tools/tracer.py`

SimpleTool defines 18+ getter methods (`get_request_model_name`, `get_request_images`, `get_request_continuation_id`, etc.) all following identical try/except/AttributeError patterns.

**~200 lines of boilerplate.**

**Suggestion**: Create a `RequestFieldAccessor` mixin with a generic `_safe_get(obj, field, default)` method. All 18+ accessors become one-liners delegating to it.

---

## 4. Provider Template Method Patterns (MEDIUM)

**Files**: `providers/openai.py`, `providers/openrouter.py`, `providers/custom.py`, `providers/azure_openai.py`, `providers/dial.py`

Multiple providers repeat the same `_lookup_capabilities` / `_finalise_capabilities` override pattern — check builtin, fall back to registry, handle exceptions.

**~200 lines duplicated across 5+ providers.**

**Suggestion**: Enhance `RegistryBackedProviderMixin` with a `_lookup_capabilities_with_fallbacks()` template method. Providers just declare `FALLBACK_REGISTRIES = [...]` and inherit the logic.

---

## 5. Schema Generation Patterns (MEDIUM)

**Files**: `tools/chat.py` (lines 110-159), `tools/apilookup.py`, `tools/shared/schema_builders.py`, `tools/workflow/schema_builders.py`

Chat tool manually rebuilds the entire schema instead of using the inherited `get_input_schema()` from SimpleTool. Other tools do similar overrides.

**~200+ lines of unnecessary schema boilerplate.**

**Suggestion**: Ensure all simple tools use the inherited `get_input_schema()` pattern. Tools should only override `get_tool_fields()` and `get_required_fields()`, not the full schema method.

---

## 6. Conversation Handling / Provider Info Extraction (MEDIUM)

**Files**: `tools/simple/base.py` (lines 637-776)

`_record_assistant_turn` and `_create_continuation_offer_response` both contain identical logic to extract provider name, model name, and metadata from a `model_info` dict.

**~50 lines duplicated.**

**Suggestion**: Extract a `_extract_model_info(model_info) -> tuple` utility method.

---

## 7. Tool Initialization Patterns (LOW)

**Files**: `debug.py`, `codereview.py`, `refactor.py`, `precommit.py` (4+ files)

Workflow tools repeat boilerplate `__init__` setting `self.initial_request = None` and `self.tool_config = {}`.

**Suggestion**: Set class-level defaults in WorkflowTool base class.

---

## Summary Table

| Category | Files | Lines Duplicated | Priority |
|----------|-------|-----------------|----------|
| Workflow Request Models | 11+ | ~500 | **HIGH** |
| Field Descriptions | 11+ | ~300 | MEDIUM |
| Request Accessors | 3+ | ~200 | **HIGH** |
| Provider Patterns | 6+ | ~200 | MEDIUM |
| Schema Generation | 4+ | ~200 | MEDIUM |
| Conversation Handling | 2+ | ~50 | MEDIUM |
| Tool Initialization | 4+ | ~20 | LOW |
| **TOTAL** | | **~1,470** | |

## Recommended Order

1. Consolidate workflow request models into `StandardWorkflowRequest` (biggest bang)
2. Create generic field accessor mixin (benefits all tools)
3. Consolidate field description factories (single source of truth)
4. Enhance provider registry mixin (cleaner provider onboarding)
5. Audit schema generation overrides (enforce inheritance)
6. Extract provider info extraction utility (small cleanup)
