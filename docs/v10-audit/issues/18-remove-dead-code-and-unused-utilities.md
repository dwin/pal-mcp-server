# Issue: Remove Dead Code and Unused Utilities

**Labels**: `cleanup`, `v10`
**Priority**: MEDIUM
**Estimated lines removed**: ~550+

## Problem

Several modules, functions, and patterns are defined but unused or barely used:

### Unused utility functions in `utils/file_types.py` (~60 lines)
- `is_code_file()` — 0 references in production code
- `is_binary_file()` — 0 references
- `get_file_category()` — 0 references

### Underutilized `utils/client_info.py` (293 lines)
Only 2 files import this module. 5 functions for tracking client context that are barely used.

### Thin wrapper modules in `providers/shared/`
- `model_response.py` (26 lines) — wraps a dataclass, only adds `total_tokens` property. Could be a TypedDict.
- `provider_type.py` (363 lines) — ProviderType enum with repetitive mappings that could be simplified.

### Unused production dependencies
`python-dotenv` declared globally but only imported in 3 locations (docker scripts, tests). Core server uses `utils.env.get_env()` which doesn't use dotenv.

### Config special-casing
`_is_builtin_custom_models_config` in `utils/file_utils.py` — 15 lines of special-case code to prevent reading the server's own config file.

### Duplicated provider info extraction
`_record_assistant_turn` and `_create_continuation_offer_response` in `tools/simple/base.py` both contain identical logic to extract provider name, model name, and metadata (~50 lines).

### Technical debt markers
- `utils/model_context.py:33` — unfinished TODO for model-specific tokenizers
- `tools/codereview.py` — deprecated confidence field kept for backward compatibility
- Tests verifying "unused workflow fields are empty"

## Key Files

- `utils/file_types.py`, `utils/client_info.py`, `utils/file_utils.py`
- `providers/shared/model_response.py`, `providers/shared/provider_type.py`
- `tools/simple/base.py` (lines 637-776)
- `pyproject.toml`

## Proposed Solution

1. Delete unused functions from `file_types.py`; inline remaining functions into `file_utils.py`
2. Remove or relocate `client_info.py` (to tests/examples if needed for debugging)
3. Replace `ModelResponse` with TypedDict; simplify `ProviderType`
4. Move `python-dotenv` to dev dependency group
5. Replace config special-casing with a `ServerConfig` dataclass
6. Extract `_extract_model_info()` utility to deduplicate provider info extraction
7. Resolve or remove TODO markers and deprecated fields

## Related Findings

- Audit Report 02 (Dependency Minimalist): Findings 3, 4, 8, 9
- Audit Report 05 (Test Archaeologist): Findings 5, 7
- Audit Report 01 (DRY Auditor): Finding 6
