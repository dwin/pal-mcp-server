"""
Tests for the main server functionality
"""

import signal

import pytest

import server
from server import handle_call_tool


class TestServerTools:
    """Test server tool handling"""

    def test_register_signal_handlers(self, monkeypatch):
        """Test graceful shutdown and SIGPIPE handlers are registered."""
        registered_handlers = {}

        def fake_signal(sig, handler):
            registered_handlers[sig] = handler

        monkeypatch.setattr(signal, "signal", fake_signal)

        server.register_signal_handlers()

        assert registered_handlers[signal.SIGTERM] is server.shutdown_handler
        assert registered_handlers[signal.SIGINT] is server.shutdown_handler
        if hasattr(signal, "SIGPIPE"):
            assert registered_handlers[signal.SIGPIPE] == signal.SIG_IGN

    def test_shutdown_handler_raises_keyboard_interrupt(self, caplog):
        """Test shutdown signals trigger graceful interruption."""
        with caplog.at_level("INFO"):
            with pytest.raises(KeyboardInterrupt):
                server.shutdown_handler(signal.SIGTERM, None)

        assert "Received SIGTERM; starting graceful shutdown" in caplog.text

    def test_cleanup_providers_does_not_create_registry_during_shutdown(self, monkeypatch):
        """Test cleanup skips registry creation when nothing was initialized."""
        from providers.registry import ModelProviderRegistry

        original_instance = ModelProviderRegistry._instance
        ModelProviderRegistry._instance = None

        def fail_if_called(*args, **kwargs):
            raise AssertionError("cleanup should not create a new registry instance")

        monkeypatch.setattr(ModelProviderRegistry, "__new__", fail_if_called)

        try:
            server.cleanup_providers()
        finally:
            ModelProviderRegistry._instance = original_instance

    @pytest.mark.asyncio
    async def test_handle_call_tool_unknown(self):
        """Test calling an unknown tool"""
        result = await handle_call_tool("unknown_tool", {})
        assert len(result) == 1
        assert "Unknown tool: unknown_tool" in result[0].text

    @pytest.mark.asyncio
    async def test_handle_chat(self):
        """Test chat functionality using real integration testing"""
        import importlib
        import os

        # Set test environment
        os.environ["PYTEST_CURRENT_TEST"] = "test"

        # Save original environment
        original_env = {
            "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
            "DEFAULT_MODEL": os.environ.get("DEFAULT_MODEL"),
        }

        try:
            # Set up environment for real provider resolution
            os.environ["OPENAI_API_KEY"] = "sk-test-key-server-chat-test-not-real"
            os.environ["DEFAULT_MODEL"] = "o3-mini"

            # Clear other provider keys to isolate to OpenAI
            for key in ["GEMINI_API_KEY", "XAI_API_KEY", "OPENROUTER_API_KEY"]:
                os.environ.pop(key, None)

            # Reload config and clear registry
            import config

            importlib.reload(config)
            from providers.registry import ModelProviderRegistry

            ModelProviderRegistry._instance = None

            # Test with real provider resolution
            try:
                result = await handle_call_tool("chat", {"prompt": "Hello Gemini", "model": "o3-mini"})

                # If we get here, check the response format
                assert len(result) == 1
                # Parse JSON response
                import json

                response_data = json.loads(result[0].text)
                assert "status" in response_data

            except Exception as e:
                # Expected: API call will fail with fake key
                error_msg = str(e)
                # Should NOT be a mock-related error
                assert "MagicMock" not in error_msg
                assert "'<' not supported between instances" not in error_msg

                # Should be a real provider error
                assert any(
                    phrase in error_msg
                    for phrase in ["API", "key", "authentication", "provider", "network", "connection"]
                )

        finally:
            # Restore environment
            for key, value in original_env.items():
                if value is not None:
                    os.environ[key] = value
                else:
                    os.environ.pop(key, None)

            # Reload config and clear registry
            importlib.reload(config)
            ModelProviderRegistry._instance = None

    @pytest.mark.asyncio
    async def test_handle_version(self):
        """Test getting version info"""
        result = await handle_call_tool("version", {})
        assert len(result) == 1

        response = result[0].text
        # Parse the JSON response
        import json

        data = json.loads(response)
        assert data["status"] == "success"
        content = data["content"]

        # Check for expected content in the markdown output
        assert "# PAL MCP Server Version" in content
        assert "## Server Information" in content
        assert "## Configuration" in content
        assert "Current Version" in content
