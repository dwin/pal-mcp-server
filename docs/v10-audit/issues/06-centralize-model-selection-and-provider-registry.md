# Issue: Centralize Model Selection and Simplify Provider Registry

**Labels**: `refactor`, `architecture`, `v10`
**Priority**: HIGH
**Estimated lines removed**: ~400+

## Problem

Model selection and provider routing is scattered across 4+ locations with duplicated fallback logic:

1. **`config.py`** — defines `DEFAULT_MODEL`, comments about provider priority
2. **`server.py`** (lines 795, 1113-1184) — 3+ identical `get_preferred_fallback_model()` calls
3. **`providers/registry.py`** — `PROVIDER_PRIORITY_ORDER`, registry singleton
4. **`tools/shared/base_tool.py`** (lines 240-342, 500-620) — duplicates model lookup in `get_model_request()` and `resolve_model_with_auto_mode()`

Additionally:
- **Provider template methods** (`_lookup_capabilities` / `_finalise_capabilities`) are duplicated across 5+ providers (~200 lines) with identical "check builtin, fall back to registry" patterns
- **Two registry layers** (`registry.py` + `registry_provider_mixin.py`) force all providers through registries even when simpler
- **Temperature constraint defaults** (0.0-2.0, default 0.3) are re-defined in multiple places per model instead of referencing shared templates
- **Config plumbing** has a 25-line function for a 2-line calculation, and every custom registry re-implements JSON loading

## Key Files

- `config.py`, `server.py`, `providers/registry.py`, `providers/registry_provider_mixin.py`
- `tools/shared/base_tool.py`
- `providers/openai.py`, `providers/openrouter.py`, `providers/custom.py`, `providers/azure_openai.py`, `providers/dial.py`
- `providers/shared/model_capabilities.py`, `providers/shared/temperature.py`

## Proposed Solution

1. Create a `ModelSelector` class with a single `select_for_tool(tool_category, requested_model)` method — replaces 6+ scattered call sites
2. Enhance `RegistryBackedProviderMixin` with `_lookup_capabilities_with_fallbacks()` template — providers just declare `FALLBACK_REGISTRIES = [...]`
3. Merge `registry.py` + `registry_provider_mixin.py` into a single registry with optional capability loading
4. Create shared temperature constraint templates (`STANDARD_RANGE`, `O1_EXACT`, `O3_RANGE`)
5. Extract shared JSON loading to a `JsonModelRegistry` base class
6. Simplify `_calculate_mcp_prompt_limit` to 2 lines

## Related Findings

- Audit Report 01 (DRY Auditor): Finding 4
- Audit Report 02 (Dependency Minimalist): Finding 7
- Audit Report 04 (Config Simplifier): Findings 2, 5, 6
