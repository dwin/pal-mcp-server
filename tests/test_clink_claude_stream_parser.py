"""Tests for Claude CLI stream-json (NDJSON) parser (claude 2.1.25)."""

import pytest

from clink.parsers.base import ParserError
from clink.parsers.claude_stream import ClaudeStreamJSONParser


def _build_stream_json_output() -> str:
    """Build sample stream-json output matching claude 2.1.25 format."""
    return """{"type":"system","subtype":"init","cwd":"/Users/test/project","session_id":"20b9174b-7e05-4610-a44e-5190c849f2aa","model":"claude-opus-4-5-20251101","permissionMode":"default"}
{"type":"assistant","message":{"model":"claude-opus-4-5-20251101","id":"msg_01CGHMSBFZCzYog4Q5p7uojG","type":"message","role":"assistant","content":[{"type":"text","text":"Hello! I'm ready to help you."}],"usage":{"input_tokens":2,"cache_creation_input_tokens":40514,"output_tokens":57}},"session_id":"20b9174b-7e05-4610-a44e-5190c849f2aa"}
{"type":"result","subtype":"success","is_error":false,"duration_ms":4460,"duration_api_ms":3630,"num_turns":1,"result":"Hello! I'm ready to help you.","session_id":"20b9174b-7e05-4610-a44e-5190c849f2aa","total_cost_usd":0.2546475,"usage":{"input_tokens":2,"cache_creation_input_tokens":40514,"output_tokens":57},"modelUsage":{"claude-opus-4-5-20251101":{"inputTokens":2,"outputTokens":57,"cacheReadInputTokens":0,"cacheCreationInputTokens":40514}},"uuid":"4b9468f3-82e1-4fcd-a086-299103abc9d2"}"""


def test_claude_stream_parser_extracts_session_id():
    """Test session_id extraction from stream-json output."""
    parser = ClaudeStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.metadata["session_id"] == "20b9174b-7e05-4610-a44e-5190c849f2aa"


def test_claude_stream_parser_extracts_result_content():
    """Test result content extraction."""
    parser = ClaudeStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.content == "Hello! I'm ready to help you."


def test_claude_stream_parser_extracts_model():
    """Test model extraction from init event."""
    parser = ClaudeStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.metadata["model_used"] == "claude-opus-4-5-20251101"


def test_claude_stream_parser_extracts_metrics():
    """Test duration and cost metrics extraction."""
    parser = ClaudeStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.metadata["duration_ms"] == 4460
    assert parsed.metadata["duration_api_ms"] == 3630
    assert parsed.metadata["total_cost_usd"] == 0.2546475
    assert parsed.metadata["uuid"] == "4b9468f3-82e1-4fcd-a086-299103abc9d2"


def test_claude_stream_parser_extracts_usage():
    """Test usage metrics extraction."""
    parser = ClaudeStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert "usage" in parsed.metadata
    assert parsed.metadata["usage"]["input_tokens"] == 2
    assert parsed.metadata["usage"]["output_tokens"] == 57


def test_claude_stream_parser_extracts_model_usage():
    """Test modelUsage extraction."""
    parser = ClaudeStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert "model_usage" in parsed.metadata
    assert "claude-opus-4-5-20251101" in parsed.metadata["model_usage"]


def test_claude_stream_parser_extracts_events():
    """Test raw events are preserved."""
    parser = ClaudeStreamJSONParser()
    stdout = _build_stream_json_output()

    parsed = parser.parse(stdout=stdout, stderr="")

    assert "raw_events" in parsed.metadata
    assert len(parsed.metadata["raw_events"]) == 3  # init, assistant, result


def test_claude_stream_parser_uses_assistant_content_without_result():
    """Test fallback to assistant content when result is missing."""
    parser = ClaudeStreamJSONParser()
    stdout = """{"type":"system","subtype":"init","session_id":"abc-123","model":"claude-opus-4-5-20251101"}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hello from assistant"}]}}"""

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.content == "Hello from assistant"


def test_claude_stream_parser_handles_hook_events():
    """Test parser handles hook events without error."""
    parser = ClaudeStreamJSONParser()
    stdout = """{"type":"system","subtype":"hook_started","hook_id":"abc","hook_name":"SessionStart:startup","session_id":"test-session"}
{"type":"system","subtype":"hook_response","hook_id":"abc","output":"{}","exit_code":0,"session_id":"test-session"}
{"type":"system","subtype":"init","session_id":"test-session","model":"claude-opus-4-5-20251101"}
{"type":"result","subtype":"success","result":"Hello","session_id":"test-session"}"""

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.content == "Hello"
    assert parsed.metadata["session_id"] == "test-session"
    assert len(parsed.metadata["raw_events"]) == 4


def test_claude_stream_parser_requires_content():
    """Test parser raises error when no content found."""
    parser = ClaudeStreamJSONParser()
    stdout = """{"type":"system","subtype":"init","session_id":"abc-123"}"""

    with pytest.raises(ParserError):
        parser.parse(stdout=stdout, stderr="")


def test_claude_stream_parser_handles_empty_output():
    """Test parser raises error on empty output."""
    parser = ClaudeStreamJSONParser()

    with pytest.raises(ParserError):
        parser.parse(stdout="", stderr="")


def test_claude_stream_parser_preserves_stderr():
    """Test stderr is preserved in metadata."""
    parser = ClaudeStreamJSONParser()
    stdout = """{"type":"result","subtype":"success","result":"Hello","session_id":"abc-123"}"""

    parsed = parser.parse(stdout=stdout, stderr="Warning: something happened")

    assert parsed.metadata["stderr"] == "Warning: something happened"


def test_claude_stream_parser_handles_error_result():
    """Test is_error flag extraction."""
    parser = ClaudeStreamJSONParser()
    stdout = (
        """{"type":"result","subtype":"error","is_error":true,"result":"API Error occurred","session_id":"abc-123"}"""
    )

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.content == "API Error occurred"
    assert parsed.metadata["is_error"] is True
