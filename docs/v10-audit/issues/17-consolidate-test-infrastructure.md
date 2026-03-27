# Issue: Consolidate Test Infrastructure

**Labels**: `testing`, `v10`
**Priority**: HIGH

## Problem

### Parallel test suites with overlapping coverage
- `tests/` — 112 Python files, unit and integration tests with mocks
- `simulator_tests/` — 38 Python files, end-to-end conversation simulations

Same tools tested redundantly across both directories:
- **Consensus**: 6 test files
- **Planner**: 3 files (including an obsolete `_old` version)
- **Debug**: 3 files (unit + 2 simulator tests totaling 68KB)
- **Refactor, SecAudit**: Duplicated across both

### Obsolete test file
`simulator_tests/test_planner_validation_old.py` (439 lines) — explicitly named `_old`, superseded by `test_planner_validation.py` (717 lines).

### Overgrown test orchestrator
`communication_simulator_test.py` (556 lines) reinvents pytest: custom test registry, manual runner creation, custom CLI parsing, manual result reporting.

### Duplicate test helper modules
`tests/mock_helpers.py`, `simulator_tests/base_test.py`, `tests/conftest.py` — split responsibility for mock/helper setup across 3 modules.

### Hardcoded `/tmp` in tests
`tests/test_chat_simple.py` and others use `"/tmp"` which is Unix-only.

## Key Files

- `communication_simulator_test.py`
- `simulator_tests/test_planner_validation_old.py`
- `tests/mock_helpers.py`, `simulator_tests/base_test.py`, `tests/conftest.py`
- Various test files in both `tests/` and `simulator_tests/`

## Proposed Solution

1. **Delete immediately**: `simulator_tests/test_planner_validation_old.py`
2. **Migrate** `communication_simulator_test.py` to pytest: move setup to `conftest.py`, delete the orchestrator, use native pytest features (`-k`, `--tb=short`, `-vv`)
3. **Establish clear boundaries**: `tests/` = fast unit tests with mocks; `simulator_tests/` = e2e only. Remove redundant coverage.
4. **Consolidate helpers** into a single `conftest.py` with pytest fixtures
5. **Replace** hardcoded `/tmp` with `tempfile.gettempdir()`

## Related Findings

- Audit Report 05 (Test Archaeologist): Findings 2, 3, 4, 6
- Audit Report 07 (System/Host Inspector): Finding 5.2
