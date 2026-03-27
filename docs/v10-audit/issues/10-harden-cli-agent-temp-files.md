# Issue: Harden CLI Agent Temporary File Handling

**Labels**: `security`, `critical`, `v10`
**Priority**: CRITICAL

## Problem

TOCTOU (Time-of-Check-Time-of-Use) vulnerability in `clink/agents/base.py`:

```python
fd, tmp_path = tempfile.mkstemp(prefix="clink-", suffix=".json")
os.close(fd)  # File descriptor closed immediately
output_file_path = Path(tmp_path)
# Path passed to external command — race window exists
```

The temporary file is created and immediately closed, then its path is passed to an external command. An attacker could race-condition access to this file between creation and use. Same pattern in `clink/agents/cursor.py`.

Additionally, cleanup is best-effort only (`except OSError: pass`) — temp files may accumulate if the process crashes.

## Key Files

- `clink/agents/base.py` (lines 99-108, 149-150)
- `clink/agents/cursor.py`

## Proposed Solution

1. Keep the file descriptor open until after the subprocess completes, OR
2. Use `NamedTemporaryFile` context manager with `delete=False` for guaranteed cleanup:

```python
with tempfile.NamedTemporaryFile(prefix="clink-", suffix=".json", delete=False) as tmp:
    tmp_path = tmp.name
try:
    # ... run command with tmp_path ...
finally:
    Path(tmp_path).unlink(missing_ok=True)
```

## Related Findings

- Audit Report 06 (Security Reviewer): Finding 1
- Audit Report 07 (System/Host Inspector): Finding 5.1
