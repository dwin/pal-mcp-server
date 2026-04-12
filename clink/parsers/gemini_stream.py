"""Parser for Gemini CLI stream-json (NDJSON) output."""

from __future__ import annotations

import json
from typing import Any

from .base import BaseParser, ParsedCLIResponse, ParserError


class GeminiStreamJSONParser(BaseParser):
    """Parse stdout produced by `gemini --output-format stream-json`.

    Gemini stream-json emits newline-delimited JSON events:
    - init: Session initialization with session_id, model, timestamp
    - message (role=user): User input
    - message (role=assistant): Assistant response (may have delta=true for streaming)
    - result: Final stats with token usage and duration

    Tested with gemini-cli 0.26.0.
    """

    name = "gemini_stream_json"

    def parse(self, stdout: str, stderr: str) -> ParsedCLIResponse:
        lines = [line.strip() for line in (stdout or "").splitlines() if line.strip()]
        events: list[dict[str, Any]] = []
        session_id: str | None = None
        model: str | None = None
        assistant_content: str | None = None
        stats: dict[str, Any] | None = None
        status: str | None = None

        for line in lines:
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            events.append(event)
            event_type = event.get("type")

            if event_type == "init":
                # Extract session info from init event
                sid = event.get("session_id")
                if isinstance(sid, str) and sid:
                    session_id = sid
                mdl = event.get("model")
                if isinstance(mdl, str) and mdl:
                    model = mdl

            elif event_type == "message":
                role = event.get("role")
                if role == "assistant":
                    # Extract assistant message content
                    content = event.get("content")
                    if isinstance(content, str) and content.strip():
                        # For streaming, later messages may replace earlier ones
                        assistant_content = content.strip()

            elif event_type == "result":
                # Extract final stats
                status = event.get("status")
                result_stats = event.get("stats")
                if isinstance(result_stats, dict):
                    stats = result_stats

        if not assistant_content:
            raise ParserError("Gemini stream-json output did not include an assistant message")

        # Build metadata
        metadata: dict[str, Any] = {
            "events": events,
        }
        if session_id:
            metadata["session_id"] = session_id
        if model:
            metadata["model_used"] = model
        if status:
            metadata["status"] = status
        if stats:
            metadata["stats"] = stats
            # Extract commonly accessed fields
            duration_ms = stats.get("duration_ms")
            if isinstance(duration_ms, (int, float)):
                metadata["latency_ms"] = duration_ms
            # Token usage
            token_usage = {}
            for key in ["input_tokens", "output_tokens", "total_tokens", "cached"]:
                val = stats.get(key)
                if isinstance(val, (int, float)):
                    token_usage[key] = val
            if token_usage:
                metadata["token_usage"] = token_usage
        if stderr and stderr.strip():
            metadata["stderr"] = stderr.strip()

        return ParsedCLIResponse(content=assistant_content, metadata=metadata)
