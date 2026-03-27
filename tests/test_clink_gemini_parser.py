"""Tests for the Gemini CLI JSON parser."""

import pytest

from clink.parsers.gemini import GeminiJSONParser, ParserError


def _build_rate_limit_stdout() -> str:
    return (
        "{\n"
        '  "response": "",\n'
        '  "stats": {\n'
        '    "models": {\n'
        '      "gemini-3.1-pro-preview": {\n'
        '        "api": {\n'
        '          "totalRequests": 5,\n'
        '          "totalErrors": 5,\n'
        '          "totalLatencyMs": 13319\n'
        "        },\n"
        '        "tokens": {"prompt": 0, "candidates": 0, "total": 0, "cached": 0, "thoughts": 0, "tool": 0}\n'
        "      }\n"
        "    },\n"
        '    "tools": {"totalCalls": 0},\n'
        '    "files": {"totalLinesAdded": 0, "totalLinesRemoved": 0}\n'
        "  }\n"
        "}"
    )


def test_gemini_parser_handles_rate_limit_empty_response():
    parser = GeminiJSONParser()
    stdout = _build_rate_limit_stdout()
    stderr = "Attempt 1 failed with status 429. Retrying with backoff... ApiError: quota exceeded"

    parsed = parser.parse(stdout, stderr)

    assert "429" in parsed.content
    assert parsed.metadata.get("rate_limit_status") == 429
    assert parsed.metadata.get("empty_response") is True
    assert "Attempt 1 failed" in parsed.metadata.get("stderr", "")


def test_gemini_parser_still_errors_when_no_fallback_available():
    parser = GeminiJSONParser()
    stdout = '{"response": "", "stats": {}}'

    with pytest.raises(ParserError):
        parser.parse(stdout, stderr="")


def test_gemini_parser_extracts_session_id():
    """Test session_id extraction (gemini-cli 0.26.0 format)."""
    parser = GeminiJSONParser()
    # Real output format from gemini-cli 0.26.0
    stdout = """{
  "session_id": "988ecb67-d98f-4e7b-84cb-fb42cacd79c4",
  "response": "Hello! How can I help you with your project today?",
  "stats": {
    "models": {
      "gemini-3-flash-preview-lite": {
        "api": {
          "totalRequests": 1,
          "totalErrors": 0,
          "totalLatencyMs": 2371
        },
        "tokens": {
          "input": 3274,
          "prompt": 3274,
          "candidates": 42,
          "total": 3454,
          "cached": 0,
          "thoughts": 138,
          "tool": 0
        }
      }
    },
    "tools": {"totalCalls": 0},
    "files": {"totalLinesAdded": 0, "totalLinesRemoved": 0}
  }
}"""

    parsed = parser.parse(stdout, stderr="")

    assert parsed.content == "Hello! How can I help you with your project today?"
    assert parsed.metadata["session_id"] == "988ecb67-d98f-4e7b-84cb-fb42cacd79c4"
    assert parsed.metadata["model_used"] == "gemini-3-flash-preview-lite"
    assert parsed.metadata["token_usage"]["input"] == 3274
