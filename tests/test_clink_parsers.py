import pytest

from clink.parsers.base import ParserError
from clink.parsers.codex import CodexJSONLParser


def test_codex_parser_success():
    """Test parsing Codex JSONL output (codex-cli 0.91.0 format)."""
    parser = CodexJSONLParser()
    # Real output format from codex-cli 0.91.0
    stdout = """
{"type":"thread.started","thread_id":"019c0cf5-ee41-7b41-8cfb-9669a8dedf99"}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"Hello!"}}
{"type":"turn.completed","usage":{"input_tokens":21688,"cached_input_tokens":4608,"output_tokens":19}}
"""
    parsed = parser.parse(stdout=stdout, stderr="")
    assert parsed.content == "Hello!"
    assert parsed.metadata["usage"]["output_tokens"] == 19
    assert parsed.metadata["usage"]["cached_input_tokens"] == 4608
    # Session ID should be extracted from thread_id
    assert parsed.metadata["session_id"] == "019c0cf5-ee41-7b41-8cfb-9669a8dedf99"


def test_codex_parser_requires_agent_message():
    parser = CodexJSONLParser()
    stdout = '{"type":"turn.completed"}'
    with pytest.raises(ParserError):
        parser.parse(stdout=stdout, stderr="")
