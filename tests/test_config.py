"""
Tests for configuration
"""

from config import (
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    __author__,
    __updated__,
    __version__,
)


class TestConfig:
    """Test configuration values"""

    def test_version_info(self):
        """Test version information exists and has correct format"""
        # Check version format (e.g., "2.4.1")
        assert isinstance(__version__, str)
        assert len(__version__.split(".")) == 3  # Major.Minor.Patch

        # Check author
        assert __author__ == "Fahad Gilani"

        # Check updated date exists (don't assert on specific format/value)
        assert isinstance(__updated__, str)

    def test_model_config(self):
        """Test model configuration"""
        # DEFAULT_MODEL is set in conftest.py for tests
        assert DEFAULT_MODEL == "gemini-3-flash-preview"

    def test_temperature_defaults(self):
        """Test temperature constant"""
        assert DEFAULT_TEMPERATURE == 1.0
