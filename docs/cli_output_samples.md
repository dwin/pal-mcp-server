# CLI Output Samples for Session Resumption

Captured on: 2026-01-29

## CLI Versions

| CLI | Command | Version |
|-----|---------|---------|
| Claude | `claude` | 2.1.25 (Claude Code) |
| Gemini | `gemini` | 0.26.0 |
| Codex | `codex` | 0.91.0 |
| Cursor | `agent` | 2026.01.28-fd13201 |

## Session ID Fields

| CLI | Field Name | Location | Resume Flag | Output Format |
|-----|------------|----------|-------------|---------------|
| Claude | `session_id` | In `system/init` event | `--resume <session_id>` | stream-json (NDJSON) |
| Gemini | `session_id` | In `init` event | `--resume <session_id>` | stream-json (NDJSON) |
| Codex | `thread_id` | In `thread.started` event | `codex exec resume <thread_id>` | NDJSON |
| Cursor | `session_id` | In `system/init` event | `--resume <session_id>` | stream-json (NDJSON) |

## Sample Outputs

### Claude CLI

Claude outputs stream-json (NDJSON) format with multiple event types (requires `--verbose` flag):

```json
{"type":"system","subtype":"init","cwd":"/Users/test/project","session_id":"20b9174b-7e05-4610-a44e-5190c849f2aa","model":"claude-opus-4-5-20251101","permissionMode":"default","tools":["Task","Bash","Read","Edit",...]}
{"type":"assistant","message":{"model":"claude-opus-4-5-20251101","role":"assistant","content":[{"type":"text","text":"Hello! I'm ready to help you."}],"usage":{"input_tokens":2,"output_tokens":57}},"session_id":"20b9174b-7e05-4610-a44e-5190c849f2aa"}
{"type":"result","subtype":"success","is_error":false,"duration_ms":4460,"duration_api_ms":3630,"result":"Hello! I'm ready to help you.","session_id":"20b9174b-7e05-4610-a44e-5190c849f2aa","total_cost_usd":0.2546475,"usage":{"input_tokens":2,"output_tokens":57},"modelUsage":{"claude-opus-4-5-20251101":{"inputTokens":2,"outputTokens":57}},"uuid":"4b9468f3-82e1-4fcd-a086-299103abc9d2"}
```

**Event types:**
- `system/hook_started`: Hook execution started (optional)
- `system/hook_response`: Hook execution completed (optional)
- `system/init`: Session initialization with model, tools, cwd, session_id (available immediately)
- `assistant`: Complete assistant message with usage
- `result/success`: Final result with metrics, cost, and uuid

### Gemini CLI

Gemini outputs stream-json (NDJSON) format with multiple event types:

```json
{"type":"init","timestamp":"2026-01-30T04:28:26.132Z","session_id":"7bffa130-8c69-4cf8-ac8a-0d36b2d99f53","model":"auto-gemini-3"}
{"type":"message","timestamp":"2026-01-30T04:28:26.132Z","role":"user","content":"Say hello"}
{"type":"message","timestamp":"2026-01-30T04:28:30.825Z","role":"assistant","content":"Hello! How can I help you today?","delta":true}
{"type":"result","timestamp":"2026-01-30T04:28:30.837Z","status":"success","stats":{"total_tokens":11785,"input_tokens":11598,"output_tokens":69,"cached":0,"duration_ms":4705,"tool_calls":0}}
```

**Event types:**
- `init`: Session initialization with session_id, model, timestamp (available immediately)
- `message` (role=user): User input
- `message` (role=assistant): Assistant response (delta=true for streaming)
- `result`: Final stats with token usage and duration

### Codex CLI

Codex outputs newline-delimited JSON events:

```json
{"type":"thread.started","thread_id":"019c0cf5-ee41-7b41-8cfb-9669a8dedf99"}
{"type":"turn.started"}
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"Hello!"}}
{"type":"turn.completed","usage":{"input_tokens":21688,"cached_input_tokens":4608,"output_tokens":19}}
```

**Note**: Session ID is `thread_id` in the `thread.started` event.

### Cursor (agent) CLI

Cursor outputs stream-json (NDJSON) format with multiple event types:

```json
{"type":"system","subtype":"init","apiKeySource":"login","cwd":"/Users/test/project","session_id":"fdc86797-fa4a-4660-8737-8ab3dbb42f70","model":"Claude 4.5 Opus (Thinking)","permissionMode":"default"}
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"Say hello"}]},"session_id":"fdc86797-fa4a-4660-8737-8ab3dbb42f70"}
{"type":"thinking","subtype":"delta","text":"The user is asking...","session_id":"fdc86797-fa4a-4660-8737-8ab3dbb42f70","timestamp_ms":1769745826555}
{"type":"thinking","subtype":"completed","session_id":"fdc86797-fa4a-4660-8737-8ab3dbb42f70","timestamp_ms":1769745827161}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Hello! I'm ready to help you."}]},"session_id":"fdc86797-fa4a-4660-8737-8ab3dbb42f70"}
{"type":"result","subtype":"success","duration_ms":4828,"duration_api_ms":4828,"is_error":false,"result":"Hello! I'm ready to help you.","session_id":"fdc86797-fa4a-4660-8737-8ab3dbb42f70","request_id":"a5e65011-58e7-43ed-a65e-81cd4ae19b08"}
```

**Event types:**
- `system/init`: Session initialization with model, cwd, session_id (available immediately)
- `user`: User message
- `thinking/delta`: Thinking token deltas (streaming)
- `thinking/completed`: End of thinking
- `assistant`: Complete assistant message
- `result/success`: Final result with metrics
