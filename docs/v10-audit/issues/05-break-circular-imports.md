# Issue: Break Circular Imports with Shared Types Module

**Labels**: `refactor`, `architecture`, `v10`
**Priority**: HIGH
**Estimated lines removed**: ~200+ (TYPE_CHECKING blocks)

## Problem

21 files across the codebase use `if TYPE_CHECKING:` imports as a workaround for circular dependencies:
- `providers/base.py` needs `tools.models` for type hints
- `tools/shared/base_tool.py` needs `providers.shared` for type hints
- This creates a circular import graph broken only at runtime

**Consequences**:
- Delayed error detection (runtime vs import time)
- IDE autocompletion issues
- Makes refactoring harder — can't safely move code between modules

## Key Files

- 21+ files with `if TYPE_CHECKING:` blocks
- `providers/base.py`
- `tools/shared/base_tool.py`
- `tools/models.py`
- `providers/shared/`

## Proposed Solution

Create a `types.py` (or `shared_types.py`) module at the package root for shared type definitions:
- `ToolModelCategory`
- `ModelCapabilities`
- Other types currently causing circular imports

Both `providers/` and `tools/` import from this neutral module, eliminating the circular dependency entirely.

## Related Findings

- Audit Report 02 (Dependency Minimalist): Finding 2
