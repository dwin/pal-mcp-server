# Issue: Optimize Conversation Memory Performance

**Labels**: `performance`, `v10`
**Priority**: HIGH
**Estimated impact**: 40-60% reduction in conversation handling overhead

## Problem

`utils/conversation_memory.py` has 5 compounding inefficiencies that worsen with long conversations (50+ turns) and multi-tool sessions:

### 1. Full context serialization on every turn (HIGH)
Every `add_turn()` call serializes the **entire** ThreadContext to JSON (all previous turns + metadata). With 2 serializations per tool call (user + assistant), a 50-turn conversation does ~1.5-2.0 MB of serialization per tool call.

### 2. Redundant token counting — 3 passes on same content (HIGH)
`build_conversation_history()` counts tokens 3 times: during file embedding planning, per-turn collection, and final history estimation. 60-70% of token counting is duplicative.

### 3. File list re-computed on every tool call (MEDIUM)
`get_conversation_file_list()` re-walks all turns every time `build_conversation_history()` is called. In a 3-tool session, this means 150 turn-walks for the same file set.

### 4. Duplicate file filtering (MEDIUM)
`reconstruct_thread_context()` computes the file list, then the tool calls `filter_new_files()` which computes it **again** via a separate code path.

### 5. Reverse + reverse in turn presentation (LOW)
Turns collected newest-first for budgeting, then reversed back to chronological. Could use `deque.appendleft()` instead.

### 6. String building with intermediate joins (LOW)
Multiple concatenation operations could use `io.StringIO`.

## Key Files

- `utils/conversation_memory.py` (lines 265, 384, 433-502, 797-1014, 915-988)
- `tools/shared/base_tool.py` (lines 760-849)

## Proposed Solution

1. Replace full serialization with append-only turn logging (O(n) -> O(1) per turn)
2. Implement `ConversationHistoryBuilder` class that tracks tokens in a single pass with cache
3. Cache file list in ThreadContext metadata, invalidate when turns change
4. Pass already-computed file list through context so tools don't re-derive it
5. Use `deque.appendleft()` to avoid reverse operations
6. Use `io.StringIO` for string building

## Related Findings

- Audit Report 03 (Data Flow Analyst): All findings (1-6)
