"""Tests for Cursor CLI stream-json (NDJSON) parser (agent 2026.01.28-fd13201)."""

import pytest

from clink.parsers.base import ParserError
from clink.parsers.cursor_stream import CursorStreamJSONParser


def _build_stream_json_output() -> str:
    """Build sample stream-json output matching cursor-agent 2026.01.28-fd13201 format."""
    return """{"type":"system","subtype":"init","apiKeySource":"login","cwd":"/Users/test/project","session_id":"fdc86797-fa4a-4660-8737-8ab3dbb42f70","model":"Claude 4.5 Opus (Thinking)","permissionMode":"default"}
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"Say hello"}]},"session_id":"fdc86797-fa4a-4660-8737-8ab3dbb42f70"}
{"type":"thinking","subtype":"delta","text":"The user is","session_id":"fdc86797-fa4a-4660-8737-8ab3dbb42f70","timestamp_ms":1769745826555}
{"type":"thinking","subtype":"delta","text":" asking me to say","session_id":"fdc86797-fa4a-4660-8737-8ab3dbb42f70","timestamp_ms":1769745826620}
{"type":"thinking","subtype":"delta","text":" hello.","session_id":"fdc86797-fa4a-4660-8737-8ab3dbb42f70","timestamp_ms":1769745826620}
{"type":"thinking","subtype":"completed","session_id":"fdc86797-fa4a-4660-8737-8ab3dbb42f70","timestamp_ms":1769745827161}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hello! I'm ready to help you."}]},"session_id":"fdc86797-fa4a-4660-8737-8ab3dbb42f70"}
{"type":"result","subtype":"success","duration_ms":4828,"duration_api_ms":4828,"is_error":false,"result":"Hello! I'm ready to help you.","session_id":"fdc86797-fa4a-4660-8737-8ab3dbb42f70","request_id":"a5e65011-58e7-43ed-a65e-81cd4ae19b08"}"""


def test_cursor_stream_parser_extracts_session_id():
    """Test session_id extraction from stream-json output."""
    parser = CursorStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.metadata["session_id"] == "fdc86797-fa4a-4660-8737-8ab3dbb42f70"


def test_cursor_stream_parser_extracts_result_content():
    """Test result content extraction."""
    parser = CursorStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.content == "Hello! I'm ready to help you."


def test_cursor_stream_parser_extracts_model():
    """Test model extraction from init event."""
    parser = CursorStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.metadata["model_used"] == "Claude 4.5 Opus (Thinking)"


def test_cursor_stream_parser_extracts_thinking():
    """Test thinking tokens are accumulated."""
    parser = CursorStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert "thinking" in parsed.metadata
    assert parsed.metadata["thinking"] == "The user is asking me to say hello."


def test_cursor_stream_parser_extracts_metrics():
    """Test duration metrics extraction."""
    parser = CursorStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.metadata["duration_ms"] == 4828
    assert parsed.metadata["duration_api_ms"] == 4828
    assert parsed.metadata["request_id"] == "a5e65011-58e7-43ed-a65e-81cd4ae19b08"


def test_cursor_stream_parser_extracts_events():
    """Test raw events are preserved."""
    parser = CursorStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert "events" in parsed.metadata
    assert len(parsed.metadata["events"]) == 8  # system, user, 4x thinking, assistant, result


def test_cursor_stream_parser_handles_no_thinking():
    """Test parsing works without thinking events."""
    parser = CursorStreamJSONParser()
    stdout = """{"type":"system","subtype":"init","session_id":"abc-123","model":"Test Model"}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hello"}]}}
{"type":"result","subtype":"success","result":"Hello","session_id":"abc-123"}"""

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.content == "Hello"
    assert parsed.metadata["session_id"] == "abc-123"
    assert "thinking" not in parsed.metadata


def test_cursor_stream_parser_uses_assistant_content_without_result():
    """Test fallback to assistant content when result is missing."""
    parser = CursorStreamJSONParser()
    stdout = """{"type":"system","subtype":"init","session_id":"abc-123"}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hello from assistant"}]}}"""

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.content == "Hello from assistant"


def test_cursor_stream_parser_requires_content():
    """Test parser raises error when no content found."""
    parser = CursorStreamJSONParser()
    stdout = """{"type":"system","subtype":"init","session_id":"abc-123"}
{"type":"user","message":{"role":"user","content":[]}}"""

    with pytest.raises(ParserError):
        parser.parse(stdout=stdout, stderr="")


def test_cursor_stream_parser_handles_empty_output():
    """Test parser raises error on empty output."""
    parser = CursorStreamJSONParser()

    with pytest.raises(ParserError):
        parser.parse(stdout="", stderr="")


def test_cursor_stream_parser_preserves_stderr():
    """Test stderr is preserved in metadata."""
    parser = CursorStreamJSONParser()
    stdout = """{"type":"result","subtype":"success","result":"Hello","session_id":"abc-123"}"""

    parsed = parser.parse(stdout=stdout, stderr="Warning: something happened")

    assert parsed.metadata["stderr"] == "Warning: something happened"
