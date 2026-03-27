# Issue: Eliminate Per-Tool Boilerplate Methods

**Labels**: `refactor`, `DRY`, `v10`
**Priority**: HIGH
**Estimated lines removed**: ~260+

## Problem

Three categories of trivial methods are copy-pasted across nearly every tool:

### Temperature defaults (~60 lines across 18 tools)
Three constants (`TEMPERATURE_ANALYTICAL`, `TEMPERATURE_BALANCED`, `TEMPERATURE_CREATIVE`) are **all set to 1.0**, making the taxonomy meaningless. Yet each of 18 tools implements `get_default_temperature()` returning one of these identical values.

### Model category (~45 lines across 15 tools)
Each tool implements `get_model_category()` as a single return statement.

### Request field accessors (~200 lines in SimpleTool)
18+ getter methods (`get_request_model_name`, `get_request_images`, `get_request_continuation_id`, etc.) all follow an identical `try/except AttributeError` pattern.

## Key Files

- `config.py` (temperature constants)
- `tools/simple/base.py` (lines 171-241, accessor methods)
- All 18+ tool files (temperature + model category methods)

## Proposed Solution

1. **Temperature**: Replace 3 identical constants with `DEFAULT_TEMPERATURE = 1.0`. Add a tool-to-temperature mapping dict in `BaseTool`. Delete all 18 `get_default_temperature()` implementations.
2. **Model category**: Replace method with `MODEL_CATEGORY` class attribute. `BaseTool` provides the method.
3. **Accessors**: Create a generic `_safe_get(obj, field, default)` method. All 18+ accessors become one-liners.

## Related Findings

- Audit Report 04 (Config Simplifier): Findings 1, 7
- Audit Report 01 (DRY Auditor): Finding 3
