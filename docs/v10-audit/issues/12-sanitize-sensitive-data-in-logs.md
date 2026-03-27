# Issue: Sanitize Sensitive Data in Logs and Error Messages

**Labels**: `security`, `high`, `v10`
**Priority**: HIGH

## Problem

Multiple related concerns about sensitive data leaking through logs and error messages:

### API key exposure in errors
`str(error)` is used throughout providers without sanitization. Some API errors from underlying SDKs (OpenAI, Gemini) may contain auth tokens or keys in exception messages. Providers log error strings directly.

### Inadequate security audit logging
While API key presence is logged safely as "[PRESENT]/[MISSING]", there are gaps:
- No structured audit trail for tool executions
- Failed file accesses lack context for security monitoring
- No security event logging separate from debug logs

### DIAL API key in memory/headers
API key stored in plaintext in `self._dial_api_key` and passed via headers. Event hook removes Authorization header but preserves `Api-Key` header — visible in httpx debug logs.

### Endpoint URL logging
Custom provider logs full endpoint URLs (`providers/custom.py` lines 75, 159, 165) which may reveal internal infrastructure.

### Exception details in responses
URL validation errors include the original exception which could reveal system details (DNS failures, etc.).

## Key Files

- `providers/openai_compatible.py` (lines 102-104, 250)
- `providers/base.py` (line 256)
- `providers/dial.py` (lines 74-100)
- `providers/custom.py` (lines 75, 159, 165)
- `server.py` (lines 391-395)

## Proposed Solution

1. Create `sanitize_error_message()` utility that strips API key patterns, Bearer tokens, etc.
2. Use sanitized logging throughout all providers when logging exceptions
3. Add structured audit logging for tool executions and file access events
4. Sanitize URLs for logging (show scheme + masked hostname + port only)
5. Don't persist raw API keys in provider instance state — use transient auth mechanisms

## Related Findings

- Audit Report 06 (Security Reviewer): Findings 4, 6, 9, 12, 13
