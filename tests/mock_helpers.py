"""Helper functions for test mocking.

This module re-exports create_mock_provider from conftest.py for backward
compatibility. New code should use the ``mock_provider`` or
``create_mock_provider`` pytest fixtures defined in conftest.py instead.
"""

from tests.conftest import _create_mock_provider as create_mock_provider

__all__ = ["create_mock_provider"]
