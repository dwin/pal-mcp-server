"""
Tests for the simulator pytest adapter infrastructure.

Verifies that the pytest adapter correctly wraps TEST_REGISTRY entries
and that the conftest fixtures and markers work as expected.
"""


class TestSimulatorPytestAdapter:
    """Verify the simulator tests are properly wrapped for pytest."""

    def test_registry_entries_become_test_functions(self):
        """Every TEST_REGISTRY entry should appear in the adapter module."""
        from simulator_tests import TEST_REGISTRY
        from simulator_tests import test_pytest_adapter as adapter

        for name in TEST_REGISTRY:
            func_name = f"test_{name}"
            assert hasattr(adapter, func_name), f"Missing pytest wrapper for '{name}'"
            func = getattr(adapter, func_name)
            assert callable(func)

    def test_quick_mode_markers_applied(self):
        """Quick-mode tests must carry the @pytest.mark.quick marker."""
        from simulator_tests import QUICK_TESTS
        from simulator_tests import test_pytest_adapter as adapter

        for name in QUICK_TESTS:
            func = getattr(adapter, f"test_{name}")
            markers = [m.name for m in func.pytestmark]
            assert "quick" in markers, f"test_{name} missing 'quick' marker"

    def test_non_quick_tests_lack_quick_marker(self):
        """Non-quick tests should NOT have the quick marker."""
        from simulator_tests import QUICK_TESTS, TEST_REGISTRY
        from simulator_tests import test_pytest_adapter as adapter

        non_quick = set(TEST_REGISTRY.keys()) - QUICK_TESTS
        for name in non_quick:
            func = getattr(adapter, f"test_{name}")
            markers = [m.name for m in func.pytestmark]
            assert "quick" not in markers, f"test_{name} should not have 'quick' marker"

    def test_all_adapter_tests_have_simulator_marker(self):
        """Every generated test should carry the @pytest.mark.simulator marker."""
        from simulator_tests import TEST_REGISTRY
        from simulator_tests import test_pytest_adapter as adapter

        for name in TEST_REGISTRY:
            func = getattr(adapter, f"test_{name}")
            markers = [m.name for m in func.pytestmark]
            assert "simulator" in markers, f"test_{name} missing 'simulator' marker"
