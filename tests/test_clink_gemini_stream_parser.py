"""Tests for Gemini CLI stream-json (NDJSON) parser (gemini-cli 0.26.0)."""

import pytest

from clink.parsers.base import ParserError
from clink.parsers.gemini_stream import GeminiStreamJSONParser


def _build_stream_json_output() -> str:
    """Build sample stream-json output matching gemini-cli 0.26.0 format."""
    return """{"type":"init","timestamp":"2026-01-30T04:28:26.132Z","session_id":"7bffa130-8c69-4cf8-ac8a-0d36b2d99f53","model":"auto-gemini-3"}
{"type":"message","timestamp":"2026-01-30T04:28:26.132Z","role":"user","content":"Say hello"}
{"type":"message","timestamp":"2026-01-30T04:28:30.825Z","role":"assistant","content":"Hello! How can I help you today?","delta":true}
{"type":"result","timestamp":"2026-01-30T04:28:30.837Z","status":"success","stats":{"total_tokens":11785,"input_tokens":11598,"output_tokens":69,"cached":0,"duration_ms":4705,"tool_calls":0}}"""


def test_gemini_stream_parser_extracts_session_id():
    """Test session_id extraction from stream-json output."""
    parser = GeminiStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.metadata["session_id"] == "7bffa130-8c69-4cf8-ac8a-0d36b2d99f53"


def test_gemini_stream_parser_extracts_content():
    """Test assistant content extraction."""
    parser = GeminiStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.content == "Hello! How can I help you today?"


def test_gemini_stream_parser_extracts_model():
    """Test model extraction from init event."""
    parser = GeminiStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.metadata["model_used"] == "auto-gemini-3"


def test_gemini_stream_parser_extracts_stats():
    """Test stats extraction from result event."""
    parser = GeminiStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert "stats" in parsed.metadata
    assert parsed.metadata["stats"]["total_tokens"] == 11785
    assert parsed.metadata["stats"]["input_tokens"] == 11598
    assert parsed.metadata["stats"]["output_tokens"] == 69


def test_gemini_stream_parser_extracts_latency():
    """Test latency extraction."""
    parser = GeminiStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.metadata["latency_ms"] == 4705


def test_gemini_stream_parser_extracts_token_usage():
    """Test token usage extraction."""
    parser = GeminiStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert "token_usage" in parsed.metadata
    assert parsed.metadata["token_usage"]["input_tokens"] == 11598
    assert parsed.metadata["token_usage"]["output_tokens"] == 69
    assert parsed.metadata["token_usage"]["total_tokens"] == 11785


def test_gemini_stream_parser_extracts_status():
    """Test status extraction."""
    parser = GeminiStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.metadata["status"] == "success"


def test_gemini_stream_parser_extracts_events():
    """Test raw events are preserved."""
    parser = GeminiStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert "events" in parsed.metadata
    assert len(parsed.metadata["events"]) == 4  # init, user message, assistant message, result


def test_gemini_stream_parser_handles_multiple_assistant_messages():
    """Test parser uses latest assistant message (streaming scenario)."""
    parser = GeminiStreamJSONParser()
    stdout = """{"type":"init","session_id":"abc-123","model":"gemini-3-flash-preview"}
{"type":"message","role":"assistant","content":"Hello","delta":true}
{"type":"message","role":"assistant","content":"Hello! How can I help?","delta":true}
{"type":"result","status":"success","stats":{}}"""

    parsed = parser.parse(stdout=stdout, stderr="")

    # Should use the latest (complete) message
    assert parsed.content == "Hello! How can I help?"


def test_gemini_stream_parser_requires_assistant_message():
    """Test parser raises error when no assistant message found."""
    parser = GeminiStreamJSONParser()
    stdout = """{"type":"init","session_id":"abc-123"}
{"type":"message","role":"user","content":"Hello"}
{"type":"result","status":"success"}"""

    with pytest.raises(ParserError):
        parser.parse(stdout=stdout, stderr="")


def test_gemini_stream_parser_handles_empty_output():
    """Test parser raises error on empty output."""
    parser = GeminiStreamJSONParser()

    with pytest.raises(ParserError):
        parser.parse(stdout="", stderr="")


def test_gemini_stream_parser_preserves_stderr():
    """Test stderr is preserved in metadata."""
    parser = GeminiStreamJSONParser()
    stdout = """{"type":"init","session_id":"abc-123"}
{"type":"message","role":"assistant","content":"Hello"}
{"type":"result","status":"success"}"""

    parsed = parser.parse(stdout=stdout, stderr="Warning: rate limit approaching")

    assert parsed.metadata["stderr"] == "Warning: rate limit approaching"


def test_gemini_stream_parser_skips_non_json_lines():
    """Test parser skips stderr lines mixed in stdout."""
    parser = GeminiStreamJSONParser()
    stdout = """Loaded cached credentials.
Hook registry initialized with 0 hook entries
{"type":"init","session_id":"abc-123","model":"gemini-3-flash-preview"}
{"type":"message","role":"assistant","content":"Hello!"}
{"type":"result","status":"success","stats":{}}"""

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.content == "Hello!"
    assert parsed.metadata["session_id"] == "abc-123"
