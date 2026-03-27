"""
Pytest configuration for simulator tests.

Provides shared fixtures for environment setup and cleanup,
and adapts the TEST_REGISTRY classes into pytest-discoverable tests.
"""

import os
import shutil
import sys
import tempfile

import pytest


@pytest.fixture(scope="session")
def simulator_env():
    """Verify that the server environment is available for simulator tests."""
    if not os.path.exists("server.py"):
        pytest.skip("server.py not found — simulator tests require the server environment")

    # Find a usable Python interpreter (Unix and Windows layouts)
    cwd = os.getcwd()
    for venv_dir in (".venv", "venv", ".pal_venv"):
        for bin_path in ("bin/python", "Scripts/python.exe"):
            python = os.path.join(cwd, venv_dir, bin_path)
            if os.path.exists(python):
                return python

    # Fall back to the running interpreter if no venv found
    return sys.executable


@pytest.fixture
def sim_temp_dir():
    """Provide a temporary directory that is cleaned up after the test."""
    temp_dir = tempfile.mkdtemp(prefix="mcp_test_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)
