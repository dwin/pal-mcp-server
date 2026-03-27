# Issue: Compose System Prompts from Shared Fragments

**Labels**: `refactor`, `DRY`, `v10`
**Priority**: HIGH
**Estimated lines removed**: ~850

## Problem

System prompts are massive single-file strings with heavily overlapping instruction blocks:

| Duplicated Block | Appears In | Lines Each |
|-----------------|-----------|-----------|
| CRITICAL LINE NUMBER INSTRUCTIONS | 9 prompts | 10-20 |
| IF MORE INFORMATION NEEDED (JSON format) | 9 prompts | 8-12 |
| OUTPUT FORMAT (JSON structure) | 7 prompts | 15-40 |
| Severity definitions (Critical/High/Medium/Low) | 3 prompts | 5-15 |
| SCOPE CONTROL | 2+ prompts | 6-10 |

Additionally, 3 clink system prompts (`default.txt`, `default_analyze.txt`, `default_codereviewer.txt`) are 90% identical — each is a complete copy with 1-2 lines modified.

Changes to standard instructions require updates to 8+ files. New tools copy-paste from existing prompts, perpetuating duplication.

## Key Files

- `systemprompts/codereview_prompt.py`, `debug_prompt.py`, `refactor_prompt.py`
- `systemprompts/secaudit_prompt.py`, `testgen_prompt.py`, `docgen_prompt.py`
- `systemprompts/generate_code_prompt.py`, `planner_prompt.py`
- `systemprompts/clink/default.txt`, `default_analyze.txt`, `default_codereviewer.txt`

## Proposed Solution

1. Create `systemprompts/fragments.py` with reusable building blocks:
   - `CRITICAL_LINE_NUMBER_INSTRUCTIONS`
   - `JSON_MORE_INFO_TEMPLATE`
   - `SEVERITY_DEFINITIONS`
   - `SCOPE_CONTROL`
   - `JSON_OUTPUT_TEMPLATE`
2. Refactor each prompt to compose from fragments using f-strings
3. For clink: create a single `base.txt` template with `{role}` placeholder, define variants as a dict

## Related Findings

- Audit Report 04 (Config Simplifier): Findings 3, 4
