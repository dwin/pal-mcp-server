"""Helper functions for test mocking.

This module re-exports create_mock_provider from conftest.py for backward
compatibility. New code should use the ``mock_provider`` or
``create_mock_provider`` pytest fixtures defined in conftest.py instead.
"""


def create_mock_provider(*args, **kwargs):
    """Backward-compatible wrapper around tests.conftest._create_mock_provider."""
    from tests.conftest import _create_mock_provider

    return _create_mock_provider(*args, **kwargs)


__all__ = ["create_mock_provider"]
