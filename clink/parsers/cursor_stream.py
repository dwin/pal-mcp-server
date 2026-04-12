"""Parser for Cursor CLI stream-json (NDJSON) output."""

from __future__ import annotations

import json
from typing import Any

from .base import BaseParser, ParsedCLIResponse, ParserError


class CursorStreamJSONParser(BaseParser):
    """Parse stdout produced by `agent --output-format stream-json`.

    Cursor stream-json emits newline-delimited JSON events:
    - system/init: Session initialization with model, cwd, session_id
    - user: User message
    - thinking/delta: Thinking token deltas (optional)
    - thinking/completed: End of thinking
    - assistant: Complete assistant message
    - result/success: Final result with metrics

    Tested with cursor-agent 2026.01.28-fd13201.
    """

    name = "cursor_stream_json"

    def parse(self, stdout: str, stderr: str) -> ParsedCLIResponse:
        lines = [line.strip() for line in (stdout or "").splitlines() if line.strip()]
        events: list[dict[str, Any]] = []
        session_id: str | None = None
        request_id: str | None = None
        model: str | None = None
        thinking_tokens: list[str] = []
        assistant_content: str | None = None
        result_content: str | None = None
        duration_ms: int | float | None = None
        duration_api_ms: int | float | None = None
        is_error: bool = False

        for line in lines:
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            events.append(event)
            event_type = event.get("type")
            event_subtype = event.get("subtype")

            if event_type == "system" and event_subtype == "init":
                # Extract session info from init event
                sid = event.get("session_id")
                if isinstance(sid, str) and sid:
                    session_id = sid
                mdl = event.get("model")
                if isinstance(mdl, str) and mdl:
                    model = mdl

            elif event_type == "thinking" and event_subtype == "delta":
                # Accumulate thinking tokens
                text = event.get("text")
                if isinstance(text, str):
                    thinking_tokens.append(text)

            elif event_type == "assistant":
                # Extract assistant message content
                message = event.get("message") or {}
                content_list = message.get("content") or []
                for item in content_list:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = item.get("text")
                        if isinstance(text, str) and text.strip():
                            assistant_content = text.strip()
                            break
                # Session ID may also be in assistant event
                sid = event.get("session_id")
                if isinstance(sid, str) and sid and not session_id:
                    session_id = sid

            elif event_type == "result":
                # Extract result and metrics
                result = event.get("result")
                if isinstance(result, str) and result.strip():
                    result_content = result.strip()
                is_error = bool(event.get("is_error"))

                sid = event.get("session_id")
                if isinstance(sid, str) and sid:
                    session_id = sid
                rid = event.get("request_id")
                if isinstance(rid, str) and rid:
                    request_id = rid

                dur = event.get("duration_ms")
                if isinstance(dur, (int, float)):
                    duration_ms = dur
                api_dur = event.get("duration_api_ms")
                if isinstance(api_dur, (int, float)):
                    duration_api_ms = api_dur

        # Prefer result content, fall back to assistant content
        content = result_content or assistant_content
        if not content:
            raise ParserError("Cursor stream-json output did not include a result or assistant message")

        # Build metadata
        metadata: dict[str, Any] = {
            "events": events,
            "is_error": is_error,
        }
        if session_id:
            metadata["session_id"] = session_id
        if request_id:
            metadata["request_id"] = request_id
        if model:
            metadata["model_used"] = model
        if duration_ms is not None:
            metadata["duration_ms"] = duration_ms
        if duration_api_ms is not None:
            metadata["duration_api_ms"] = duration_api_ms
        if thinking_tokens:
            metadata["thinking"] = "".join(thinking_tokens)
        if stderr and stderr.strip():
            metadata["stderr"] = stderr.strip()

        return ParsedCLIResponse(content=content, metadata=metadata)
