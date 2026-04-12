"""
Test that enforces clear boundaries between tests/ and simulator_tests/.

Policy:
  - tests/       → fast unit tests with mocks, discovered by pytest
  - simulator_tests/ → end-to-end tests that call real tools, run via pytest adapter

This test verifies:
  1. No obsolete _old files remain in simulator_tests/
  2. simulator_tests/ has a pytest conftest.py
  3. simulator_tests/ has the pytest adapter for test discovery
"""

from pathlib import Path

SIMULATOR_DIR = Path(__file__).resolve().parent.parent / "simulator_tests"


class TestTestBoundaries:
    """Enforce structural conventions for the test suite."""

    def test_no_obsolete_old_files_in_simulator_tests(self):
        """There should be no *_old.py files in simulator_tests/."""
        old_files = list(SIMULATOR_DIR.glob("*_old.py"))
        assert not old_files, f"Obsolete *_old.py files found in simulator_tests/: " f"{[f.name for f in old_files]}"

    def test_simulator_tests_has_conftest(self):
        """simulator_tests/ should have its own conftest.py for pytest fixtures."""
        assert (
            SIMULATOR_DIR / "conftest.py"
        ).exists(), "simulator_tests/conftest.py is missing — shared fixtures belong here"

    def test_simulator_tests_has_pytest_adapter(self):
        """simulator_tests/ should have the pytest adapter for test discovery."""
        assert (SIMULATOR_DIR / "test_pytest_adapter.py").exists(), (
            "simulator_tests/test_pytest_adapter.py is missing — " "this module wraps TEST_REGISTRY for pytest"
        )

    def test_mock_helpers_is_thin_reexport(self):
        """mock_helpers.py should be a thin wrapper, not a standalone module.

        The canonical implementation of create_mock_provider lives in
        tests/conftest.py as _create_mock_provider. mock_helpers.py must
        only re-export it without defining provider logic itself.
        """
        import inspect

        import tests.mock_helpers as mh

        source = inspect.getsource(mh)
        # The module should NOT define ModelCapabilities, Mock(), etc. inline
        assert "ModelCapabilities" not in source, "mock_helpers.py should not define provider logic"
        assert (
            "mock_provider" not in source.lower() or "create_mock_provider" in source
        ), "mock_helpers.py should only re-export create_mock_provider"
