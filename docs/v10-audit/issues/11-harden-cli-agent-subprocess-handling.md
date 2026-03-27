# Issue: Harden CLI Agent Subprocess Environment and Command Building

**Labels**: `security`, `medium`, `v10`
**Priority**: MEDIUM

## Problem

Three related issues in how CLI agents spawn subprocesses:

### 1. Environment variables passed unchecked
`_build_environment()` uses `os.environ.copy()` passing ALL environment variables to subprocesses, including API keys (`GEMINI_API_KEY`, `OPENAI_API_KEY`, etc.). This also bypasses the centralized `get_env()` / `PAL_MCP_FORCE_ENV_OVERRIDE` semantics.

### 2. Command building via string templates
`flag_template.format(path=...)` followed by `shlex.split()` — if `flag_template` were ever user-controllable, the `format()` call could inject code. Currently from hardcoded config so low practical risk, but the pattern should be hardened.

### 3. Scattered `os.environ` access
CLI agents use `os.environ.copy()` directly instead of the centralized `get_env()` helper, creating inconsistent behavior when `PAL_MCP_FORCE_ENV_OVERRIDE` is enabled.

## Key Files

- `clink/agents/base.py` (lines 100-108, 122, 251)
- `clink/agents/cursor.py`

## Proposed Solution

1. Create `get_subprocess_environment()` helper that respects override semantics AND filters sensitive API key variables
2. Use explicit flag construction instead of `format()` templates for command building
3. Route all env var access through the centralized `utils/env.py` helper

## Related Findings

- Audit Report 06 (Security Reviewer): Findings 7, 8
- Audit Report 07 (System/Host Inspector): Finding 1.2
