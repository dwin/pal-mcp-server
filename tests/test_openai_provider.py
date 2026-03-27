"""Tests for OpenAI provider implementation."""

import os
from unittest.mock import MagicMock, patch

from providers.openai import OpenAIModelProvider
from providers.shared import ProviderType


class TestOpenAIProvider:
    """Test OpenAI provider functionality."""

    def setup_method(self):
        """Set up clean state before each test."""
        # Clear restriction service cache before each test
        import utils.model_restrictions

        utils.model_restrictions._restriction_service = None

    def teardown_method(self):
        """Clean up after each test to avoid singleton issues."""
        # Clear restriction service cache after each test
        import utils.model_restrictions

        utils.model_restrictions._restriction_service = None

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    def test_initialization(self):
        """Test provider initialization."""
        provider = OpenAIModelProvider("test-key")
        assert provider.api_key == "test-key"
        assert provider.get_provider_type() == ProviderType.OPENAI
        assert provider.base_url == "https://api.openai.com/v1"

    def test_initialization_with_custom_url(self):
        """Test provider initialization with custom base URL."""
        provider = OpenAIModelProvider("test-key", base_url="https://custom.openai.com/v1")
        assert provider.api_key == "test-key"
        assert provider.base_url == "https://custom.openai.com/v1"

    def test_model_validation(self):
        """Test model name validation."""
        provider = OpenAIModelProvider("test-key")

        # Test valid models
        assert provider.validate_model_name("gpt-5.4") is True
        assert provider.validate_model_name("gpt-5.4-pro") is True
        assert provider.validate_model_name("gpt-5.2") is True
        assert provider.validate_model_name("gpt-5.2-pro") is True
        assert provider.validate_model_name("gpt-5.3-codex") is True
        assert provider.validate_model_name("gpt-5.2-codex") is True
        assert provider.validate_model_name("gpt-5.4-mini") is True
        assert provider.validate_model_name("o4-mini") is True
        assert provider.validate_model_name("gpt-5.4-nano") is True

        # Test valid aliases
        assert provider.validate_model_name("mini") is True
        assert provider.validate_model_name("o4mini") is True
        assert provider.validate_model_name("gpt5.2") is True
        assert provider.validate_model_name("codex") is True
        assert provider.validate_model_name("nano") is True
        assert provider.validate_model_name("gpt5.4-pro") is True

        # Test invalid model
        assert provider.validate_model_name("invalid-model") is False
        assert provider.validate_model_name("gpt-4") is False
        assert provider.validate_model_name("gemini-pro") is False

    def test_resolve_model_name(self):
        """Test model name resolution."""
        provider = OpenAIModelProvider("test-key")

        # Test shorthand resolution
        assert provider._resolve_model_name("mini") == "gpt-5.4-mini"
        assert provider._resolve_model_name("o4mini") == "o4-mini"
        assert provider._resolve_model_name("gpt5.2") == "gpt-5.2"
        assert provider._resolve_model_name("codex") == "gpt-5.3-codex"
        assert provider._resolve_model_name("nano") == "gpt-5.4-nano"
        assert provider._resolve_model_name("gpt5.4-pro") == "gpt-5.4-pro"

        # Test full name passthrough
        assert provider._resolve_model_name("o4-mini") == "o4-mini"
        assert provider._resolve_model_name("gpt-5.4") == "gpt-5.4"
        assert provider._resolve_model_name("gpt-5.4-pro") == "gpt-5.4-pro"
        assert provider._resolve_model_name("gpt-5.2") == "gpt-5.2"
        assert provider._resolve_model_name("gpt-5.3-codex") == "gpt-5.3-codex"
        assert provider._resolve_model_name("gpt-5.2-codex") == "gpt-5.2-codex"
        assert provider._resolve_model_name("gpt-5.4-mini") == "gpt-5.4-mini"
        assert provider._resolve_model_name("gpt-5.4-nano") == "gpt-5.4-nano"

    def test_get_capabilities_o4_mini_direct(self):
        """Test getting model capabilities for O4-mini."""
        provider = OpenAIModelProvider("test-key")

        capabilities = provider.get_capabilities("o4-mini")
        assert capabilities.model_name == "o4-mini"
        assert capabilities.context_window == 200_000
        assert capabilities.provider == ProviderType.OPENAI
        assert not capabilities.supports_extended_thinking
        assert capabilities.supports_system_prompts is True
        assert capabilities.supports_streaming is True
        assert capabilities.supports_function_calling is True

        # Test temperature constraint (o4-mini has fixed temperature)
        assert capabilities.temperature_constraint.value == 1.0

    def test_get_capabilities_with_alias(self):
        """Test getting model capabilities with alias resolves correctly."""
        provider = OpenAIModelProvider("test-key")

        capabilities = provider.get_capabilities("mini")
        assert capabilities.model_name == "gpt-5.4-mini"  # "mini" now resolves to gpt-5.4-mini
        assert capabilities.context_window == 400_000
        assert capabilities.provider == ProviderType.OPENAI

    def test_get_capabilities_gpt54(self):
        """Test getting model capabilities for GPT-5.4."""
        provider = OpenAIModelProvider("test-key")

        capabilities = provider.get_capabilities("gpt-5.4")
        assert capabilities.model_name == "gpt-5.4"
        assert capabilities.context_window == 272_000
        assert capabilities.max_output_tokens == 128_000
        assert capabilities.provider == ProviderType.OPENAI
        assert capabilities.supports_extended_thinking is True
        assert capabilities.supports_system_prompts is True
        assert capabilities.supports_streaming is True
        assert capabilities.supports_function_calling is True
        assert capabilities.supports_temperature is True

    def test_get_capabilities_gpt54_mini(self):
        """Test getting model capabilities for GPT-5.4-mini."""
        provider = OpenAIModelProvider("test-key")

        capabilities = provider.get_capabilities("gpt-5.4-mini")
        assert capabilities.model_name == "gpt-5.4-mini"
        assert capabilities.context_window == 400_000
        assert capabilities.max_output_tokens == 128_000
        assert capabilities.provider == ProviderType.OPENAI
        assert capabilities.supports_extended_thinking is False
        assert capabilities.supports_system_prompts is True
        assert capabilities.supports_streaming is True
        assert capabilities.supports_function_calling is True

    def test_get_capabilities_gpt52(self):
        """Test GPT-5.2 capabilities reflect new metadata."""
        provider = OpenAIModelProvider("test-key")

        capabilities = provider.get_capabilities("gpt-5.2")
        assert capabilities.model_name == "gpt-5.2"
        assert capabilities.supports_streaming is True
        assert capabilities.supports_function_calling is True
        assert capabilities.supports_json_mode is True
        assert capabilities.allow_code_generation is True

    def test_get_capabilities_gpt53_codex(self):
        """Test GPT-5.3 Codex is responses-only and non-streaming."""
        provider = OpenAIModelProvider("test-key")

        capabilities = provider.get_capabilities("gpt-5.3-codex")
        assert capabilities.model_name == "gpt-5.3-codex"
        assert capabilities.supports_streaming is False
        assert capabilities.use_openai_response_api is True
        assert capabilities.allow_code_generation is True

    @patch("providers.openai_compatible.OpenAI")
    def test_generate_content_resolves_alias_before_api_call(self, mock_openai_class):
        """Test that generate_content resolves aliases before making API calls.

        This is the CRITICAL test that was missing - verifying that aliases
        like 'mini' get resolved to 'o4-mini' before being sent to OpenAI API.
        """
        # Set up mock OpenAI client
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        # Mock the completion response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-5.2"  # API returns the resolved model name
        mock_response.id = "test-id"
        mock_response.created = 1234567890
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15

        mock_client.chat.completions.create.return_value = mock_response

        provider = OpenAIModelProvider("test-key")

        # Call generate_content with alias 'gpt5.2' (resolves to gpt-5.2, supports temperature)
        result = provider.generate_content(
            prompt="Test prompt",
            model_name="gpt5.2",
            temperature=1.0,  # This should be resolved to "gpt-5.2"
        )

        # Verify the API was called with the RESOLVED model name
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args[1]

        # CRITICAL ASSERTION: The API should receive "gpt-5.2", not "gpt5.2"
        assert call_kwargs["model"] == "gpt-5.2", f"Expected 'gpt-5.2' but API received '{call_kwargs['model']}'"

        # Verify response
        assert result.content == "Test response"
        assert result.model_name == "gpt-5.2"  # Should be the resolved name

    @patch("providers.openai_compatible.OpenAI")
    def test_generate_content_other_aliases(self, mock_openai_class):
        """Test other alias resolutions in generate_content."""
        # Set up mock
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        mock_client.chat.completions.create.return_value = mock_response

        provider = OpenAIModelProvider("test-key")

        # Test o4mini -> o4-mini
        mock_response.model = "o4-mini"
        provider.generate_content(prompt="Test", model_name="o4mini", temperature=1.0)
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "o4-mini"

        # Test mini -> gpt-5.4-mini
        mock_response.model = "gpt-5.4-mini"
        provider.generate_content(prompt="Test", model_name="mini", temperature=1.0)
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-5.4-mini"

    @patch("providers.openai_compatible.OpenAI")
    def test_generate_content_no_alias_passthrough(self, mock_openai_class):
        """Test that full model names pass through unchanged."""
        # Set up mock
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "o3-mini"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        mock_client.chat.completions.create.return_value = mock_response

        provider = OpenAIModelProvider("test-key")

        # Test full model name passes through unchanged
        provider.generate_content(prompt="Test", model_name="o4-mini", temperature=1.0)
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "o4-mini"  # Should be unchanged

    def test_extended_thinking_capabilities(self):
        """Thinking-mode support should be reflected via ModelCapabilities."""
        provider = OpenAIModelProvider("test-key")

        supported_aliases = [
            "gpt-5.4",
            "gpt-5.4-pro",
            "gpt-5.2",
            "gpt-5.2-pro",
            "gpt-5.3-codex",
            "gpt-5.2-codex",
            "gpt5.2",
            "codex",
        ]
        for alias in supported_aliases:
            assert provider.get_capabilities(alias).supports_extended_thinking is True

        unsupported_aliases = ["o4-mini", "o4mini", "gpt-5.4-mini", "mini", "gpt-5.4-nano", "nano"]
        for alias in unsupported_aliases:
            assert provider.get_capabilities(alias).supports_extended_thinking is False

        # Invalid models should not validate, treat as unsupported
        assert not provider.validate_model_name("invalid-model")

    @patch("providers.openai_compatible.OpenAI")
    def test_gpt54_pro_routes_to_responses_endpoint(self, mock_openai_class):
        """Test that gpt-5.4-pro model routes to the /v1/responses endpoint (mock test)."""
        # Set up mock for OpenAI client responses endpoint
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client

        mock_response = MagicMock()
        # gpt-5.4-pro format: direct output_text field
        mock_response.output_text = "4"
        mock_response.model = "gpt-5.4-pro"
        mock_response.id = "test-id"
        mock_response.created_at = 1234567890
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15

        mock_client.responses.create.return_value = mock_response

        provider = OpenAIModelProvider("test-key")

        # Generate content with gpt-5.4-pro
        result = provider.generate_content(prompt="What is 2 + 2?", model_name="gpt-5.4-pro", temperature=1.0)

        # Verify responses.create was called
        mock_client.responses.create.assert_called_once()
        call_args = mock_client.responses.create.call_args[1]
        assert call_args["model"] == "gpt-5.4-pro"
        assert call_args["input"][0]["role"] == "user"
        assert "What is 2 + 2?" in call_args["input"][0]["content"][0]["text"]

        # Verify the response
        assert result.content == "4"
        assert result.model_name == "gpt-5.4-pro"
        assert result.metadata["endpoint"] == "responses"

    @patch("providers.openai_compatible.OpenAI")
    def test_non_responses_api_uses_chat_completions(self, mock_openai_class):
        """Test that non-responses-api models use the standard chat completions endpoint."""
        # Set up mock
        mock_client = MagicMock()
        mock_openai_class.return_value = mock_client
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "o4-mini"
        mock_response.id = "test-id"
        mock_response.created = 1234567890
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 5
        mock_response.usage.total_tokens = 15
        mock_client.chat.completions.create.return_value = mock_response

        provider = OpenAIModelProvider("test-key")

        # Generate content with o4-mini (not using responses endpoint)
        result = provider.generate_content(prompt="Test prompt", model_name="o4-mini", temperature=1.0)

        # Verify chat.completions.create was called
        mock_client.chat.completions.create.assert_called_once()

        # Verify the response
        assert result.content == "Test response"
        assert result.model_name == "o4-mini"
