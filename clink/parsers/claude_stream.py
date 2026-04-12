"""Parser for Claude CLI stream-json (NDJSON) output."""

from __future__ import annotations

import json
from typing import Any

from .base import BaseParser, ParsedCLIResponse, ParserError


class ClaudeStreamJSONParser(BaseParser):
    """Parse stdout produced by `claude --output-format stream-json --verbose`.

    Claude stream-json emits newline-delimited JSON events:
    - system/hook_started: Hook execution started
    - system/hook_response: Hook execution completed
    - system/init: Session initialization with model, tools, cwd, session_id
    - assistant: Complete assistant message with usage
    - result/success: Final result with metrics

    Tested with claude 2.1.25.
    """

    name = "claude_stream_json"

    def parse(self, stdout: str, stderr: str) -> ParsedCLIResponse:
        lines = [line.strip() for line in (stdout or "").splitlines() if line.strip()]
        events: list[dict[str, Any]] = []
        session_id: str | None = None
        uuid_field: str | None = None
        model: str | None = None
        assistant_content: str | None = None
        result_content: str | None = None
        duration_ms: int | float | None = None
        duration_api_ms: int | float | None = None
        usage: dict[str, Any] | None = None
        model_usage: dict[str, Any] | None = None
        is_error: bool = False
        total_cost_usd: float | None = None

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

            # Extract session_id from any event that has it
            sid = event.get("session_id")
            if isinstance(sid, str) and sid:
                session_id = sid

            if event_type == "system" and event_subtype == "init":
                # Extract model from init event
                mdl = event.get("model")
                if isinstance(mdl, str) and mdl:
                    model = mdl

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
                # Extract usage from assistant event
                msg_usage = message.get("usage")
                if isinstance(msg_usage, dict):
                    usage = msg_usage

            elif event_type == "result":
                # Extract result and metrics
                result = event.get("result")
                if isinstance(result, str) and result.strip():
                    result_content = result.strip()
                is_error = bool(event.get("is_error"))

                uid = event.get("uuid")
                if isinstance(uid, str) and uid:
                    uuid_field = uid

                dur = event.get("duration_ms")
                if isinstance(dur, (int, float)):
                    duration_ms = dur
                api_dur = event.get("duration_api_ms")
                if isinstance(api_dur, (int, float)):
                    duration_api_ms = api_dur

                cost = event.get("total_cost_usd")
                if isinstance(cost, (int, float)):
                    total_cost_usd = cost

                result_usage = event.get("usage")
                if isinstance(result_usage, dict):
                    usage = result_usage

                result_model_usage = event.get("modelUsage")
                if isinstance(result_model_usage, dict) and result_model_usage:
                    model_usage = result_model_usage
                    # Extract model name from modelUsage keys
                    if not model:
                        model = next(iter(result_model_usage.keys()))

        # Prefer result content, fall back to assistant content
        content = result_content or assistant_content
        if not content:
            raise ParserError("Claude stream-json output did not include a result or assistant message")

        # Build metadata
        metadata: dict[str, Any] = {
            "raw_events": events,
            "is_error": is_error,
        }
        if session_id:
            metadata["session_id"] = session_id
        if uuid_field:
            metadata["uuid"] = uuid_field
        if model:
            metadata["model_used"] = model
        if duration_ms is not None:
            metadata["duration_ms"] = duration_ms
        if duration_api_ms is not None:
            metadata["duration_api_ms"] = duration_api_ms
        if total_cost_usd is not None:
            metadata["total_cost_usd"] = total_cost_usd
        if usage:
            metadata["usage"] = usage
        if model_usage:
            metadata["model_usage"] = model_usage
        if stderr and stderr.strip():
            metadata["stderr"] = stderr.strip()

        return ParsedCLIResponse(content=content, metadata=metadata)
