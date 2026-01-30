"""Parser for Cursor CLI JSON output."""

from __future__ import annotations

import json
from typing import Any

from .base import BaseParser, ParsedCLIResponse, ParserError


class CursorJSONParser(BaseParser):
    """Parse stdout produced by `cursor-agent -p --output-format json`."""

    name = "cursor_json"

    def parse(self, stdout: str, stderr: str) -> ParsedCLIResponse:
        if not stdout.strip():
            raise ParserError("Cursor CLI returned empty stdout while JSON output was expected")

        try:
            payload: dict[str, Any] = json.loads(stdout)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive logging
            raise ParserError(f"Failed to decode Cursor CLI JSON output: {exc}") from exc

        # Expect type: "result" and subtype: "success"
        if payload.get("type") != "result":
            raise ParserError(f"Cursor CLI returned unexpected type: {payload.get('type')}")

        if payload.get("subtype") != "success":
            raise ParserError(f"Cursor CLI returned unsuccessful subtype: {payload.get('subtype')}")

        result = payload.get("result")
        if not isinstance(result, str) or not result.strip():
            if payload.get("is_error"):
                raise ParserError("Cursor CLI reported an error in the response")
            raise ParserError("Cursor CLI response did not contain a textual result")

        content = result.strip()

        # Build metadata from response
        metadata = self._build_metadata(payload, stderr)

        return ParsedCLIResponse(content=content, metadata=metadata)

    def _build_metadata(self, payload: dict[str, Any], stderr: str) -> dict[str, Any]:
        """Extract metadata from Cursor response."""

        metadata: dict[str, Any] = {
            "raw": payload,
            "is_error": bool(payload.get("is_error")),
        }

        duration_ms = payload.get("duration_ms")
        if isinstance(duration_ms, (int, float)):
            metadata["duration_ms"] = duration_ms

        api_duration = payload.get("duration_api_ms")
        if isinstance(api_duration, (int, float)):
            metadata["duration_api_ms"] = api_duration

        session_id = payload.get("session_id")
        if isinstance(session_id, str) and session_id:
            metadata["session_id"] = session_id

        request_id = payload.get("request_id")
        if isinstance(request_id, str) and request_id:
            metadata["request_id"] = request_id

        stderr_text = stderr.strip()
        if stderr_text:
            metadata["stderr"] = stderr_text

        return metadata
