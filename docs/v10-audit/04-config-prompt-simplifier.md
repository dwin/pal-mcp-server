# PAL MCP Server: Configuration & Prompt Simplification Report

**Agent**: Configuration & Prompt Simplifier
**Focus**: Prompt duplication, model routing complexity, overengineered config

## Executive Summary

Configuration and prompt management shows significant duplication and unnecessary complexity. Temperature defaults are duplicated across 18 tools, system prompts share ~150+ lines of identical boilerplate across 8+ files, and model selection logic is scattered across 4+ locations. Refactoring could reduce config/prompt maintenance burden by **60-70%**.

---

## 1. Redundant Temperature Configuration (HIGH)

**Files**: `config.py` + 18 tool files

Three temperature constants (`TEMPERATURE_ANALYTICAL`, `TEMPERATURE_BALANCED`, `TEMPERATURE_CREATIVE`) are all set to **1.0** — making the taxonomy meaningless. Each of 18 tools implements an identical `get_default_temperature()` method returning one of these identical values.

**~60 lines of boilerplate across 18 files.**

**Suggestion**: Replace with a single `DEFAULT_TEMPERATURE = 1.0` and a tool-to-temperature mapping dict in `BaseTool`. Delete all 18 `get_default_temperature()` implementations. If categories ever diverge, change the mapping in one place.

---

## 2. Scattered Model/Provider Routing Logic (HIGH)

**Files**: `config.py`, `server.py` (lines 795, 1113-1184), `providers/registry.py`, `tools/shared/base_tool.py` (lines 240-342, 500-620)

Model selection logic is distributed across 4+ files:
- `config.py` defines `DEFAULT_MODEL` and comments about provider priority
- `server.py` has 3+ identical `get_preferred_fallback_model()` calls
- `base_tool.py` duplicates model lookup in `get_model_request()` and `resolve_model_with_auto_mode()`
- `registry.py` defines `PROVIDER_PRIORITY_ORDER`

**~150 lines of scattered routing logic.**

**Suggestion**: Create a centralized `ModelSelector` class with a single `select_for_tool(tool_category, requested_model)` method. Replace all 6+ fragmented call sites with one interface. Future model policy changes require edits in 1 place.

---

## 3. Prompt Duplication & Composition (HIGH)

**Files**: 8+ files in `systemprompts/`

System prompts contain heavily overlapping instruction blocks:

| Duplicated Block | Appears In | Lines Each |
|-----------------|-----------|-----------|
| CRITICAL LINE NUMBER INSTRUCTIONS | 9 prompts | 10-20 |
| IF MORE INFORMATION NEEDED (JSON) | 9 prompts | 8-12 |
| OUTPUT FORMAT (JSON structure) | 7 prompts | 15-40 |
| Severity definitions | 3 prompts | 5-15 |
| SCOPE CONTROL | 2+ prompts | 6-10 |

**~800+ lines of duplicated prompt content.**

**Suggestion**: Create `systemprompts/fragments.py` with reusable building blocks (`CRITICAL_LINE_NUMBER_INSTRUCTIONS`, `JSON_MORE_INFO_TEMPLATE`, `SEVERITY_DEFINITIONS`, etc.). Refactor each prompt to compose from fragments using f-strings. New tools can compose prompts in 50 lines instead of 200+.

---

## 4. Clink Text Prompt Redundancy (MEDIUM)

**Files**: `systemprompts/clink/default.txt`, `default_analyze.txt`, `default_codereviewer.txt`

Three nearly identical clink system prompts with 90% overlap. Each is a complete copy with 1-2 lines modified for role-specific behavior.

**Suggestion**: Create a single `base.txt` template with a `{role}` placeholder. Define role variants as a dict in `clink.py`. Eliminates 2 duplicate files.

---

## 5. Temperature Constraint Scattered Defaults (MEDIUM)

**Files**: `providers/shared/model_capabilities.py`, `providers/shared/temperature.py`, individual provider registries

Default temperature constraints (0.0-2.0, default 0.3) defined in multiple places. Each model re-specifies temperature rules even when sharing defaults.

**Suggestion**: Create `providers/shared/temperature_defaults.py` with standard constraint templates (`STANDARD_RANGE`, `O1_EXACT`, `O3_RANGE`). Reference these in model definitions instead of re-defining.

---

## 6. Configuration Plumbing Overengineering (MEDIUM)

**Files**: `config.py` (lines 117-142), `utils/env.py`, multiple `registries/*.py`

- 25-line function for a simple calculation (`_calculate_mcp_prompt_limit`) that could be 2 lines
- Every custom registry re-implements JSON loading with near-identical code
- 3-level indirection: `get_env()` wrapper -> config logic -> provider registries

**Suggestion**: Simplify MCP limit calc to 2 lines. Extract shared JSON loading to a `JsonModelRegistry` base class. Saves ~50 lines.

---

## 7. Model Category Boilerplate (LOW-MEDIUM)

**Files**: 15+ tool files

Each tool implements `get_model_category()` as a single return statement.

**Suggestion**: Replace with a `MODEL_CATEGORY` class attribute. `BaseTool` provides the method:
```python
def get_model_category(self):
    return self.MODEL_CATEGORY or ToolModelCategory.GENERAL
```
Eliminates 15 method definitions.

---

## Summary Table

| Issue | Files | Lines | Priority |
|-------|-------|-------|----------|
| Temperature config duplication | 18 tools + config | ~60 | **HIGH** |
| Model/provider routing scatter | 4 files | ~150 | **HIGH** |
| Prompt composition blocks | 8+ prompts | ~800 | **HIGH** |
| Clink prompt duplication | 3 files | ~50 | MEDIUM |
| Temperature constraint defaults | 5+ files | ~40 | MEDIUM |
| Config plumbing complexity | 2+ files | ~50 | MEDIUM |
| Model category boilerplate | 15 tools | ~45 | LOW |

## Recommended Order

1. Temperature config (easiest, immediate ROI — delete 18 methods)
2. Prompt composition blocks (highest impact on maintainability)
3. Model routing consolidation (reduces cognitive load, enables flexibility)
4. Clink prompts (quick win, 30 minutes)
5. Remaining items handled opportunistically
