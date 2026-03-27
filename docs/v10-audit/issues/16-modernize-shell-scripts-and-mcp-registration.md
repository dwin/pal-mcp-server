# Issue: Modernize Shell Scripts and MCP Registration

**Labels**: `infrastructure`, `portability`, `v10`
**Priority**: MEDIUM
**Estimated lines affected**: ~4,200

## Problem

### Duplicate shell/PowerShell scripts
Near-identical functionality duplicated across Unix and Windows:
- `run-server.sh` (1,969 lines) / `run-server.ps1` (1,963 lines)
- `code_quality_checks.sh` (43 lines) / `code_quality_checks.ps1` (93 lines)
- `run_integration_tests.sh` (90 lines) / `run_integration_tests.ps1` (206 lines)

Bug fixes must be applied to both, and they've already diverged (`run_integration_tests.ps1` is 206 lines vs `.sh` at 90 lines).

### Fragile MCP registration
`run-server.sh` uses `eval` for string interpolation when running `claude mcp add`, parses `claude mcp list` output with grep. Complex string manipulation is error-prone and has security implications.

### Hardcoded Claude Desktop config paths
Paths per-platform are hardcoded and assume a specific directory structure that Anthropic could change.

### Fragile WSL detection
Only checks `/proc/version` for "microsoft" — could add fallback checks for `$WSL_DISTRO_NAME`, `$WSL_INTEROP`, or `wsl.exe`.

## Key Files

- `run-server.sh`, `run-server.ps1`
- `code_quality_checks.sh`, `code_quality_checks.ps1`
- `run_integration_tests.sh`, `run_integration_tests.ps1`

## Proposed Solution

1. Replace shell scripts with Python-based equivalents (cross-platform by default, single codebase)
2. Use Python to directly modify `claude_desktop_config.json` for MCP registration — eliminate `eval` and grep parsing
3. Search multiple candidate paths for Claude config, query Claude CLI if available
4. Add fallback WSL detection methods
5. Alternative: keep shell scripts but use a Makefile or `invoke` as the entry point to reduce duplication

## Related Findings

- Audit Report 05 (Test Archaeologist): Finding 1
- Audit Report 07 (System/Host Inspector): Findings 4.2, 6.3, 7.1
