# PAL MCP Server: System/Host Boundary Inspection Report

**Agent**: System/Host/User Boundary Inspector
**Focus**: OS assumptions, file paths, platform fragility, host system interactions

## Executive Summary

The server has a **clean architecture** with well-separated MCP protocol concerns and thoughtful security patterns. However, there are **portability and reliability issues** from platform-specific assumptions: hardcoded config paths ignoring XDG spec, missing signal handling for graceful shutdown, scattered `os.environ` access bypassing the centralized env helper, and fragile shell-based MCP registration.

---

## 1. Environment Variable Usage

### 1.1 Centralized Access via `get_env()` (GOOD)

`utils/env.py` provides centralized env var handling with `.env` file support and a `PAL_MCP_FORCE_ENV_OVERRIDE` flag. Clean contract.

### 1.2 Scattered Direct `os.environ` Access (CONCERN)

**Files**: `clink/agents/base.py:251`, `clink/agents/cursor.py`

CLI agent subprocess spawning uses `os.environ.copy()` directly, bypassing the centralized `get_env()` semantics and `PAL_MCP_FORCE_ENV_OVERRIDE` flag. Also passes all env vars (including API keys) to subprocesses.

**Suggestion**: Create a `get_subprocess_environment()` helper that respects override semantics and filters sensitive variables.

### 1.3 No Startup Validation of API Keys (CONCERN)

Missing API keys only fail when a tool is invoked, not at startup. At least one key is required but this isn't validated early.

**Suggestion**: Add early validation in `server.py:configure_providers()` — fail fast if no API keys are configured.

---

## 2. File System Interactions

### 2.1 Hardcoded Home Directory Config Path (PORTABILITY)

**File**: `clink/constants.py:15`

```python
USER_CONFIG_DIR = Path.home() / ".pal" / "cli_clients"
```

Problems:
- Doesn't follow XDG Base Directory spec (`$XDG_CONFIG_HOME`)
- Windows users expect `~/AppData/Roaming/`
- Non-standard Unix convention (should be `~/.config/pal/`)

**Suggestion**: Platform-aware config directory function respecting `XDG_CONFIG_HOME` on Unix, `APPDATA` on Windows.

### 2.2 Log Directory Write Assumption (MINOR)

**File**: `server.py:117-118`

`log_dir.mkdir(exist_ok=True)` — no permission check, fails silently if not writable.

**Suggestion**: Check `os.access(log_dir, os.W_OK)` and fall back to stderr if not writable.

### 2.3 Home Directory Assumptions (CONCERN)

**Files**: `clink/constants.py:15`, `run-server.sh:125-154`

Assumes user has a writable home directory. Fails for system users, containers without HOME set, or chroot/sandbox environments.

**Suggestion**: Add `PAL_CONFIG_DIR` env var override and fall back to `tempfile.gettempdir()` as last resort.

---

## 3. Process Management & Signal Handling

### 3.1 Subprocess Execution (GOOD)

`clink/agents/base.py` uses `asyncio.create_subprocess_exec()` with array arguments (no shell injection), separate streams, configurable limits (10MB), and proper timeout handling with `process.kill()` on timeout.

### 3.2 Missing Signal Handling (HIGH CONCERN)

**File**: `server.py:1522-1524`

Only catches `KeyboardInterrupt`. No SIGTERM handler (Docker/systemd graceful shutdown), no SIGPIPE handler (MCP pipe breakage). `atexit.register(cleanup_providers)` may not fire in all shutdown scenarios.

**Suggestion**: Register handlers for SIGTERM and SIGINT. Ignore SIGPIPE for robustness with MCP stdio transport. ~10 lines of code, high impact for containerized deployments.

---

## 4. Platform-Specific Code

### 4.1 OS Detection in Shell Scripts (GOOD)

`run-server.sh` detects macOS, Linux, WSL, Windows with sophisticated WSL detection via `/proc/version`.

### 4.2 Claude Desktop Config Paths (HARDCODED)

**File**: `run-server.sh:125-154`

Hardcoded paths for Claude Desktop config per-platform. Assumes specific directory structure that Anthropic could change.

**Suggestion**: Search multiple candidate paths, query Claude CLI for config location if available.

### 4.3 WSL Detection is Fragile (MINOR)

Only checks `/proc/version` for "microsoft". Could add fallback checks: `$WSL_DISTRO_NAME` env var, `$WSL_INTEROP`, or `wsl.exe` availability.

### 4.4 Venv Path Resolution (GOOD)

Checks both Unix (`bin/python`) and Windows (`Scripts/python.exe`) locations. Sed compatibility handles GNU vs BSD differences.

---

## 5. Temp File Usage

### 5.1 CLI Agent Temp Files (MOSTLY SAFE)

**File**: `clink/agents/base.py:99-100`

Uses `tempfile.mkstemp()` with prefix. Cleanup attempted but best-effort only (`except OSError: pass`). Temp files may accumulate on crashes.

**Suggestion**: Use `NamedTemporaryFile` context manager for guaranteed cleanup.

### 5.2 Hardcoded `/tmp` in Tests (PORTABILITY)

**Files**: `tests/test_chat_simple.py` and others

```python
"working_directory_absolute_path": "/tmp"
```

Unix-only assumption. Tests fail on Windows.

**Suggestion**: Use `tempfile.gettempdir()` instead.

---

## 6. MCP Protocol Boundary

### 6.1 Clean MCP/Business Logic Separation (EXCELLENT)

Architecture cleanly layers: MCP Protocol (server.py) -> Tool Registry -> Tool Classes -> Business Logic (providers). Tools are testable without the MCP server. Request/response marshaling is clean.

### 6.2 Stateless to Stateful Bridge (WELL-DOCUMENTED)

`server.py:703-749` explicitly documents how it bridges MCP's stateless protocol with conversation thread resumption. In-memory storage is appropriate for MCP's ephemeral nature but lost on restart.

### 6.3 MCP Registration via Shell (FRAGILE)

**File**: `run-server.sh:515-600`

Uses `eval` for string interpolation when running `claude mcp add`, parses `claude mcp list` output with grep. Complex string manipulation is error-prone.

**Suggestion**: Use Python to directly modify `claude_desktop_config.json` — more reliable and testable.

---

## 7. Shell Script Fragility

### 7.1 `eval` Usage in run-server.sh (CONCERN)

```bash
local claude_cmd="claude mcp add pal -s user$env_args -- \"$python_cmd\" \"$server_path\""
if eval "$claude_cmd" 2>/dev/null; then
```

Potential security issue with eval-based string interpolation.

### 7.2 code_quality_checks.sh (GOOD)

Uses `uv` (platform-agnostic), no hardcoded paths, simple and straightforward.

---

## 8. Permissions & User Context

### 8.1 No Root/Admin Assumptions (GOOD)

Server doesn't assume specific user, write permissions to specific directories, or sudo/elevation. Can run as any user.

### 8.2 Directory Write Assumptions (MINOR)

Log directory and config directory creation assume writability without checking. Fail silently or with unhelpful errors.

---

## Summary Table

| Area | Assessment | Risk | Priority |
|------|-----------|------|----------|
| Env Vars | Mostly Good | Low-Med | 2 |
| File System Paths | Mixed | Med-High | 2 |
| Process Management | Good | Low | - |
| Signal Handling | **Poor** | **High** | **1** |
| Platform Code | Good-Fair | Med | 3 |
| Temp Files | Good | Low | 3 |
| Security/Path Validation | Excellent | Low | - |
| MCP Boundary | Excellent | Low | - |
| Shell Scripts | Fair-Good | Med | 2 |
| Permissions | Fair | Med | 3 |

## Recommended Priority

**Critical** (low effort, high impact):
1. Add SIGTERM/SIGINT signal handlers for graceful shutdown (~10 lines)
2. Validate at least one API key at startup (fail fast)
3. Fix hardcoded `/tmp` in tests

**High** (medium effort):
4. Support XDG Base Directory spec for config paths
5. Replace shell-based MCP registration with Python
6. Centralize subprocess environment handling

**Medium** (cleanup):
7. Temp file context manager pattern
8. Graceful log directory fallback
9. Home directory fallbacks for restricted environments
10. Document config search order
