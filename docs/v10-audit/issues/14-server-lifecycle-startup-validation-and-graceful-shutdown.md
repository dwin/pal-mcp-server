# Issue: Improve Server Lifecycle: Startup Validation and Graceful Shutdown

**Labels**: `reliability`, `v10`
**Priority**: HIGH

## Problem

### Missing signal handling for graceful shutdown
`server.py` only catches `KeyboardInterrupt` (Ctrl+C). There is:
- No SIGTERM handler — Docker/systemd graceful shutdown may not clean up properly
- No SIGPIPE handler — MCP pipe breakage not handled
- `atexit.register(cleanup_providers)` may not fire in all shutdown scenarios (SIGKILL, `os._exit()`)

This causes resource leaks, incomplete provider cleanup, and potential zombie processes in containerized deployments.

### No startup validation of API keys
Missing API keys only fail when a tool is invoked, not at startup. At least one API key is required but this isn't validated early — leading to confusing runtime errors instead of clear startup failures.

## Key Files

- `server.py` (lines 22, 1522-1524)

## Proposed Solution

1. Register signal handlers for SIGTERM and SIGINT with proper async cleanup
2. Ignore SIGPIPE for robustness with MCP stdio transport
3. Add early validation in `configure_providers()`: fail fast if no API keys are configured
4. Log clear startup messages indicating which providers are available

```python
import signal

for sig in (signal.SIGTERM, signal.SIGINT):
    signal.signal(sig, shutdown_handler)
try:
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
except (AttributeError, ValueError):
    pass  # Not available on Windows
```

~10-15 lines of code, high impact.

## Related Findings

- Audit Report 07 (System/Host Inspector): Findings 1.3, 3.2
