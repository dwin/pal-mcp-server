"""
Tests for conftest.py fixtures to ensure they work correctly.

Validates the consolidated test helper fixtures including
the mock_provider factory fixture.
"""

from providers.shared import ProviderType


class TestConftestFixtures:
    """Test that conftest fixtures are properly configured."""

    def test_mock_provider_fixture_exists(self, mock_provider):
        """The mock_provider fixture should create a usable mock provider."""
        assert mock_provider is not None
        caps = mock_provider.get_capabilities()
        assert caps.provider == ProviderType.GOOGLE
        assert caps.model_name == "gemini-3-flash-preview"
        assert caps.context_window == 1_048_576

    def test_mock_provider_generates_content(self, mock_provider):
        """The mock_provider fixture should return a mock response from generate_content."""
        response = mock_provider.generate_content("test")
        assert response.content == "Test response"
        assert response.usage == {"input_tokens": 10, "output_tokens": 20}
        assert response.provider == ProviderType.GOOGLE

    def test_create_mock_provider_fixture_customizable(self, create_mock_provider):
        """The create_mock_provider fixture should accept custom parameters."""
        provider = create_mock_provider(model_name="gpt-4", context_window=128_000)
        caps = provider.get_capabilities()
        assert caps.model_name == "gpt-4"
        assert caps.context_window == 128_000

    def test_project_path_fixture(self, project_path):
        """The project_path fixture should provide an isolated temp directory."""
        assert project_path.exists()
        assert project_path.is_dir()
        assert "test_workspace" in str(project_path)
