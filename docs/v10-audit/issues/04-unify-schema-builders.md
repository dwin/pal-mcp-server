# Issue: Unify Schema Builders

**Labels**: `refactor`, `DRY`, `v10`
**Priority**: MEDIUM
**Estimated lines removed**: ~350

## Problem

Two separate schema builder classes do essentially the same thing:
- `tools/shared/schema_builders.py` (159 lines)
- `tools/workflow/schema_builders.py` (169 lines)

Both build JSON schema dicts, both reuse `COMMON_FIELD_SCHEMAS`, both follow identical patterns.

Additionally, some tools (e.g., `chat.py` lines 110-159, `apilookup.py`) manually rebuild the entire schema instead of using the inherited `get_input_schema()` from SimpleTool — ~200+ lines of unnecessary overrides.

## Key Files

- `tools/shared/schema_builders.py`
- `tools/workflow/schema_builders.py`
- `tools/chat.py` (lines 110-159)
- `tools/apilookup.py`

## Proposed Solution

1. Replace both schema builder classes with a single `build_schema()` utility function that takes `workflow: bool` as a flag
2. Audit all tools overriding `get_input_schema()` — ensure they use inherited methods and only override `get_tool_fields()` + `get_required_fields()`
3. Document when `get_input_schema()` override is actually needed

## Related Findings

- Audit Report 01 (DRY Auditor): Finding 5
- Audit Report 02 (Dependency Minimalist): Finding 5
