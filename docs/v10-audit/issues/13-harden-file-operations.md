# Issue: Harden File Operations with Rate Limits and Path Traversal Fixes

**Labels**: `security`, `high`, `v10`
**Priority**: HIGH

## Problem

### Path traversal race condition
`resolve_and_validate_path()` resolves symlinks via `path.resolve()` then checks against dangerous paths. However, symlinks can be changed between validation and access (TOCTOU race condition). No check for deeply nested symlinks resolving outside boundaries.

### Missing rate limits on file operations
No enforcement of:
- Maximum file size before reading
- Maximum directory depth when expanding directories
- Timeout on filesystem operations
- Limit on number of files returned from directory expansion

A malicious or accidental input could request a directory with millions of files or a very large file, causing memory exhaustion or service hang.

## Key Files

- `utils/file_utils.py` (lines 282-350, entire module)
- `utils/security_config.py`

## Proposed Solution

1. Use `realpath()` with `strict=True` to catch broken symlinks
2. Add canonical path comparison as final validation step
3. Add constants and enforce limits:
   - `MAX_FILE_SIZE = 50MB`
   - `MAX_TOTAL_SIZE = 100MB`
   - `MAX_FILES = 1000`
   - `MAX_DIR_DEPTH = 10`
4. Enforce these limits in file reading functions before content is loaded into memory

## Related Findings

- Audit Report 06 (Security Reviewer): Findings 3, 10
