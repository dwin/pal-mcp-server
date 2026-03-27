"""
Pytest adapter for simulator test classes.

Wraps each TEST_REGISTRY entry as a proper pytest test function so that
the full simulator suite can be run via::

    pytest simulator_tests/test_pytest_adapter.py          # all tests
    pytest simulator_tests/test_pytest_adapter.py -k basic  # filter by name
    pytest simulator_tests/test_pytest_adapter.py -m quick  # quick mode only

This replaces the custom orchestrator in communication_simulator_test.py.
"""

import pytest

from simulator_tests import QUICK_TESTS, TEST_REGISTRY


def _make_test(name, test_cls):
    """Create a pytest test function that runs a simulator test class."""

    @pytest.mark.simulator
    def test_func(simulator_env, request):
        verbose = bool(request.config.getoption("verbose"))
        instance = test_cls(verbose=verbose)
        result = instance.run_test()
        assert result, f"Simulator test '{name}' failed"

    test_func.__name__ = f"test_{name}"
    test_func.__qualname__ = f"test_{name}"
    test_func.__doc__ = f"Simulator: {name}"

    if name in QUICK_TESTS:
        test_func = pytest.mark.quick(test_func)

    return test_func


# Dynamically generate a pytest test function for each registry entry.
for _name, _cls in TEST_REGISTRY.items():
    globals()[f"test_{_name}"] = _make_test(_name, _cls)
