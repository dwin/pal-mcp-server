"""
Communication Simulator Test for PAL MCP Server

Thin wrapper around pytest that runs the simulator test suite.
The test classes live in simulator_tests/ and are adapted into pytest
test functions by simulator_tests/test_pytest_adapter.py.

Usage:
    # Run all simulator tests
    python communication_simulator_test.py

    # Run quick mode (6 essential tests)
    python communication_simulator_test.py --quick

    # Run a single test by name
    python communication_simulator_test.py --individual basic_conversation

    # Run selected tests
    python communication_simulator_test.py --tests basic_conversation content_validation

    # List available tests
    python communication_simulator_test.py --list-tests

    # Verbose output
    python communication_simulator_test.py --verbose

    # Or use pytest directly (recommended):
    pytest simulator_tests/test_pytest_adapter.py              # all tests
    pytest simulator_tests/test_pytest_adapter.py -m quick     # quick mode
    pytest simulator_tests/test_pytest_adapter.py -k basic     # filter by name
"""

import argparse
import subprocess
import sys


def _build_pytest_args(args) -> list[str]:
    """Build the pytest command-line from parsed arguments."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "simulator_tests/test_pytest_adapter.py",
    ]

    if args.verbose:
        cmd.append("-vv")

    if args.quick:
        cmd.extend(["-m", "quick"])
    elif args.individual:
        cmd.extend(["-k", args.individual])
    elif args.tests:
        expr = " or ".join(args.tests)
        cmd.extend(["-k", expr])

    # Always show short tracebacks for readability
    cmd.extend(["--tb=short"])

    return cmd


def _list_tests():
    """List available tests from the registry."""
    from simulator_tests import QUICK_TESTS, TEST_REGISTRY

    print("Available simulator tests:")
    for name, cls in TEST_REGISTRY.items():
        instance = cls(verbose=False)
        quick_tag = " [quick]" if name in QUICK_TESTS else ""
        print(f"  {name:<35} - {instance.test_description}{quick_tag}")


def main():
    parser = argparse.ArgumentParser(description="PAL MCP Communication Simulator Test")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
    parser.add_argument("--keep-logs", action="store_true", help="(legacy, ignored) Logs are managed by pytest")
    parser.add_argument("--tests", "-t", nargs="+", help="Specific tests to run (space-separated)")
    parser.add_argument("--list-tests", action="store_true", help="List available tests and exit")
    parser.add_argument("--individual", "-i", help="Run a single test by name")
    parser.add_argument("--quick", "-q", action="store_true", help="Run quick mode (6 essential tests)")
    parser.add_argument("--setup", action="store_true", help="(legacy, ignored) Environment setup is automatic")

    args = parser.parse_args()

    if args.list_tests:
        _list_tests()
        return

    cmd = _build_pytest_args(args)
    try:
        result = subprocess.run(cmd)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        sys.exit(130)


if __name__ == "__main__":
    main()
