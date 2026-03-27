# Issue: Platform-Aware Config Directory Paths

**Labels**: `portability`, `v10`
**Priority**: MEDIUM

## Problem

### Hardcoded config path ignores platform conventions
`clink/constants.py:15`:
```python
USER_CONFIG_DIR = Path.home() / ".pal" / "cli_clients"
```

Problems:
- Doesn't follow XDG Base Directory spec (`$XDG_CONFIG_HOME`) on Linux
- Windows users expect `~/AppData/Roaming/`
- Non-standard Unix convention (should be `~/.config/pal/`)
- No `PAL_CONFIG_DIR` env var override

### Home directory assumptions
Assumes user has a writable home directory. Fails for:
- System users (nologin, git)
- Container environments with no HOME set
- Chroot/sandbox environments

### Log directory write assumption
`server.py:117-118` creates log directory with `mkdir(exist_ok=True)` but no permission check — fails silently if not writable.

## Key Files

- `clink/constants.py` (line 15)
- `server.py` (lines 117-118)

## Proposed Solution

1. Create a platform-aware `get_config_dir()` function:
   - Linux: respect `$XDG_CONFIG_HOME`, default to `~/.config/pal/`
   - macOS: `~/Library/Application Support/PAL/`
   - Windows: `$APPDATA/PAL/`
2. Add `PAL_CONFIG_DIR` env var override for all platforms
3. Fall back to `tempfile.gettempdir()` as last resort for restricted environments
4. Check `os.access(log_dir, os.W_OK)` and fall back to stderr if not writable

## Related Findings

- Audit Report 07 (System/Host Inspector): Findings 2.1, 2.2, 2.3
