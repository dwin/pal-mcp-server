# PAL MCP Server: Security Audit Report

**Agent**: Security Reviewer
**Focus**: Credentials, input validation, injection risks, logging of sensitive data

## Executive Summary

The codebase has several strong security practices (centralized API key handling, subprocess safety with array arguments, comprehensive path validation). However, there are **2 critical**, **4 high**, **4 medium**, and **3 low** severity findings. The most urgent issues are SSRF protection gaps and unsafe temporary file handling in CLI agents.

---

## Critical Findings

### 1. Unsafe Temporary File Creation in CLI Agents (CRITICAL)

**File**: `clink/agents/base.py` (lines 99-108), `clink/agents/cursor.py`

A TOCTOU (Time-of-Check-Time-of-Use) vulnerability: temporary file is created with `mkstemp`, immediately closed, and its path passed to an external command. An attacker could race-condition access to this file between creation and use.

**Remediation**: Keep the file descriptor open until the process completes, or use `NamedTemporaryFile` with `delete=False` in a context manager.

### 2. Missing SSRF Protection for Custom API Endpoints (CRITICAL)

**File**: `providers/openai_compatible.py` (lines 197-250)

`_validate_base_url()` checks URL scheme and hostname existence but does NOT block:
- Internal metadata service URLs (169.254.169.254 for AWS/GCP)
- Private network addresses (192.168.x.x, 10.x.x.x, 172.16.x.x) unless localhost
- Link-local addresses

**Remediation**: Add `ipaddress` module checks to block all private/reserved/loopback IP addresses for non-localhost custom endpoints.

---

## High Severity Findings

### 3. Path Traversal Race Condition (HIGH)

**File**: `utils/file_utils.py` (lines 282-350)

`resolve_and_validate_path()` resolves symlinks via `path.resolve()` then checks against dangerous paths. However, symlinks can be changed between validation and access (race condition). No check for deeply nested symlinks resolving outside boundaries.

**Remediation**: Use `realpath()` with `strict=True`, add canonical path comparison as final validation, consider `O_NOFOLLOW` flags where appropriate.

### 4. API Key Exposure in Error Messages (HIGH)

**Files**: `providers/openai_compatible.py` (lines 102-104), `providers/base.py` (line 256)

`str(error)` is used throughout without sanitization. Some API errors from underlying SDKs may contain auth tokens or keys in exception messages. Providers log error strings directly.

**Remediation**: Create a `sanitize_error_message()` function that strips common API key patterns (`api_key: [REDACTED]`, `Authorization: Bearer [REDACTED]`) and use it when logging exceptions.

### 5. Unprotected HTTP URLs for Custom Endpoints (HIGH)

**Files**: `providers/custom.py` (line 51)

Custom provider supports `http://` URLs with no warning for non-localhost external endpoints when an API key IS provided. Only warns when both conditions met: external URL AND no API key.

**Remediation**: Always warn when using HTTP for non-localhost URLs, regardless of whether an API key is present.

### 6. Inadequate Security Audit Logging (HIGH)

**File**: `server.py` (lines 391-395)

While API key presence is logged safely as "[PRESENT]/[MISSING]", there are gaps:
- No rate limiting logs for API usage
- Failed file accesses lack context for security monitoring
- No security event logging separate from debug logs

**Remediation**: Add structured audit logging for tool executions and file access events.

---

## Medium Severity Findings

### 7. Subprocess Command Building Pattern (MEDIUM)

**File**: `clink/agents/base.py` (lines 100-108)

`flag_template.format(path=...)` followed by `shlex.split()` — if `flag_template` were ever user-controllable, the `format()` call could inject code. Currently from hardcoded config so LOW practical risk.

**Remediation**: Use explicit flag construction instead of template formatting.

### 8. Environment Variables Passed Unchecked to Subprocess (MEDIUM)

**File**: `clink/agents/base.py` (line 122)

`_build_environment()` passes ALL environment variables to subprocesses via `os.environ.copy()`, including API keys from `.env`.

**Remediation**: Filter out sensitive variables (`GEMINI_API_KEY`, `OPENAI_API_KEY`, etc.) before passing environment to subprocesses.

### 9. DIAL API Key Storage (MEDIUM)

**File**: `providers/dial.py` (lines 74-100)

API key stored in plaintext in `self._dial_api_key` and passed via headers. Event hook removes Authorization header but preserves the `Api-Key` header. Visible in httpx debug logs or network captures.

**Remediation**: Avoid persisting the raw API key in provider instance state. Use constructor-level auth that doesn't linger.

### 10. Missing Rate Limits on File Operations (MEDIUM)

**File**: `utils/file_utils.py` (entire module)

No enforcement of: maximum file size before reading, maximum directory depth, timeout on filesystem operations, or limit on number of files from directory expansion. Could cause memory exhaustion or service hang.

**Remediation**: Add constants for `MAX_FILE_SIZE`, `MAX_TOTAL_SIZE`, `MAX_FILES`, `MAX_DIR_DEPTH` and enforce them in file reading functions.

---

## Low Severity Findings

### 11. Healthcheck Subprocess (LOW)

**File**: `docker/scripts/healthcheck.py` (line 22) — Minor, already has timeout=10.

### 12. Logging of Custom Endpoints (LOW)

**File**: `providers/custom.py` (lines 75, 159, 165) — Logs full endpoint URLs which may reveal internal infrastructure. Use sanitized URL format for logging.

### 13. Exception Details in Error Responses (LOW)

**File**: `providers/openai_compatible.py` (line 250) — URL validation errors include original exception which could reveal system details (DNS failures, etc.).

---

## Positive Security Findings

The codebase does several things well:
- **Path Validation**: Comprehensive symlink resolution and dangerous path blocking in `security_config.py`
- **Subprocess Safety**: Uses `asyncio.create_subprocess_exec()` with array arguments (no `shell=True`)
- **API Key Centralization**: Through `utils/env.py` with `get_env()`, not scattered
- **URL Validation**: HTTPS enforcement warnings and scheme/port validation
- **Timeout Configuration**: Appropriate timeout values for different endpoint types
- **Error Classes**: Custom `ToolExecutionError` for controlled error messaging

---

## Summary Table

| Severity | Count | Key Issues |
|----------|-------|-----------|
| Critical | 2 | Unsafe temp files, SSRF gap |
| High | 4 | Path traversal race, API key in errors, HTTP without TLS, logging gaps |
| Medium | 4 | Command injection pattern, env var leakage, DIAL key storage, rate limiting |
| Low | 3 | Healthcheck, endpoint logging, exception details |

## Recommended Priority

**Immediate**: Fix SSRF validation, fix temp file TOCTOU, add API key sanitization
**Short-term**: Add file operation rate limits, filter env vars for subprocesses, harden command templates
**Medium-term**: Implement security event logging, add security-focused unit tests, document all external API integrations
