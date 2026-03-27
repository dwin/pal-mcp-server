# PAL MCP Server: Test & Script Archaeology Report

**Agent**: Test & Script Archaeologist
**Focus**: Dead code, obsolete tests, redundant scripts, overgrown utilities

## Executive Summary

The codebase has accumulated significant technical debt in test infrastructure and build scripts:
- **Parallel test frameworks** (`tests/` + `simulator_tests/`) with overlapping coverage
- **Duplicate shell/PowerShell scripts** (~4,200 lines of cross-platform duplication)
- **Obsolete test files** still in the codebase
- **Unused utility functions** defined but never called
- **Overgrown test orchestrator** (556 lines) that reinvents pytest

---

## 1. Duplicate Shell/PowerShell Scripts (HIGH)

**Files**:
- `run-server.sh` (1,969 lines) / `run-server.ps1` (1,963 lines)
- `code_quality_checks.sh` (43 lines) / `code_quality_checks.ps1` (93 lines)
- `run_integration_tests.sh` (90 lines) / `run_integration_tests.ps1` (206 lines)

Near-identical functionality duplicated across Unix and Windows. Bug fixes must be applied to both, and divergence risk is high.

**~4,200+ lines of duplicate functionality.**

**Suggestion**: Create a unified approach — either Python-based scripts or a Makefile with conditional logic. Notable: `run_integration_tests.ps1` is 206 lines vs `.sh` at 90 lines, suggesting the versions have already diverged.

---

## 2. Parallel Test Suites with Overlapping Coverage (HIGH)

**Structure**:
- `tests/` — 112 Python files, unit and integration tests with mocks
- `simulator_tests/` — 38 Python files, end-to-end conversation simulations

**Overlapping coverage examples**:
- **Consensus**: 6 test files across both directories testing the same tool
- **Planner**: 3 files (including an obsolete `_old` version)
- **Debug**: 3 files (unit + 2 simulator tests totaling 68KB)
- **Refactor, SecAudit**: Duplicated across both directories

**Suggestion**: Establish clear boundaries — `tests/` for fast unit tests with mocks, `simulator_tests/` for e2e only. Remove redundant coverage where both suites test the same behavior.

---

## 3. Obsolete Test File (HIGH — immediate removal)

**File**: `simulator_tests/test_planner_validation_old.py` (439 lines)

Explicitly named `_old`, superseded by `test_planner_validation.py` (717 lines) with expanded functionality. Creates confusion about which version is authoritative.

**Suggestion**: Delete immediately. Git history preserves the old version if needed.

---

## 4. Overgrown communication_simulator_test.py (HIGH)

**File**: `communication_simulator_test.py` (556 lines)

Custom test orchestrator that reinvents pytest functionality:
- Lines 103-129: Custom test registry management (pytest handles this)
- Lines 157-168: Manual test runner creation (pytest fixtures do this)
- Lines 227-260: Custom CLI parsing (pytest has built-in argument handling)
- Lines 290-350: Manual result reporting (pytest handles this)

**Suggestion**: Convert `simulator_tests/` to run directly via pytest. Move setup logic to `conftest.py` fixtures. Delete `communication_simulator_test.py`. Use native pytest features:
- Test selection: `pytest -k "consensus"`
- Quick mode: `pytest simulator_tests/ --tb=short`
- Verbose: `pytest -vv`

---

## 5. Unused File Type Functions (MEDIUM)

**File**: `utils/file_types.py` (272 lines)

Functions never called in production code:
- `is_code_file()` — 0 references
- `is_binary_file()` — 0 references
- `get_file_category()` — 0 references

Functions actually used:
- `get_token_estimation_ratio()` — called from `file_utils.py`
- `get_image_mime_type()` — called from `file_utils.py`
- `is_text_file()` — wrapped by `file_utils.py`

**Suggestion**: Delete the 3 unused functions (~60 lines). Consider inlining the remaining ones into `file_utils.py`.

---

## 6. Duplicate Test Helper Modules (MEDIUM)

**Files**:
- `tests/mock_helpers.py` (42 lines)
- `simulator_tests/base_test.py` (400+ lines)
- `tests/conftest.py` (comprehensive pytest fixtures)

Split responsibility for mock/helper setup across 3 modules. `base_test.py` contains hardcoded test file content (lines 55-90+) regenerated for each test run.

**Suggestion**: Consolidate into a single `conftest.py` with pytest fixtures. Convert `base_test.py` test file generation to temporary fixtures.

---

## 7. Technical Debt Markers (LOW)

Found in code:
- `utils/model_context.py:33` — `TODO: Integrate model-specific tokenizers` (unfinished)
- `tools/codereview.py` — `Deprecated confidence field kept for backward compatibility only`
- `tests/test_consensus.py` — `Verify unused workflow fields are empty` (testing dead fields)

**Suggestion**: Complete or remove TODOs. Remove deprecated fields if no longer needed.

---

## Summary Table

| Item | Priority | Lines | Action |
|------|----------|-------|--------|
| Delete `test_planner_validation_old.py` | **HIGH** | 439 | Immediate deletion |
| Delete/replace `communication_simulator_test.py` | **HIGH** | 556 | Migrate to pytest |
| Consolidate overlapping test suites | **HIGH** | varies | Deduplicate coverage |
| Unify shell/PowerShell scripts | **MEDIUM** | ~4,200 | Cross-platform tool |
| Remove unused file type functions | **MEDIUM** | ~60 | Safe deletion |
| Refactor test infrastructure | **MEDIUM** | ~440 | Consolidate to conftest.py |
| Clean up TODOs/deprecated markers | **LOW** | minimal | Remove or complete |

## Total Debt Identified

- ~600 lines of dead test code
- ~150 lines of unused utility functions
- ~4,200 lines of duplicate shell/PowerShell scripts
- 6+ redundantly-tested tools across parallel test suites
