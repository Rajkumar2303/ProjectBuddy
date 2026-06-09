## What this PR does

Implements `implementation_node` — the final node that synthesises the Project Blueprint Markdown document when all 5 conversation sections are complete (closes #10).

**Files changed:**
- `src/agents/xbuddy/nodes/implementation.py` — Gathers all section data, calls LLM with `BLUEPRINT_SYNTHESIS_PROMPT`, saves to Supabase, returns `final_output`
- `src/agents/xbuddy/prompts.py` — Added `BLUEPRINT_SYNTHESIS_PROMPT` (16-section Markdown template)
- `src/agents/xbuddy/graph/routes.py` — `route_after_memory_updater` returns `"implementation"` instead of `END`
- `src/agents/xbuddy/graph/builder.py` — Re-added `implementation_node` to the graph with `implementation → END` edge
- `tests/agents/test_pr6_implementation.py` — 4 unit tests

**implementation_node behaviour:**
1. Gathers `plain_text` from all 5 completed `section_states` + structured `ProjectBuddyData`
2. Calls LLM with `BLUEPRINT_SYNTHESIS_PROMPT` → produces a complete 16-section Markdown document
3. Saves the blueprint to Supabase via `save_business_plan()` (best-effort, logs warning if unavailable)
4. Returns `{"final_output": blueprint_markdown, "finished": True}`

**Complete graph flow (all 6 PRs assembled):**

```
START → initialize → router → generate_reply → generate_decision → memory_updater
                                                                          ↓
                                                              implementation → END
```

## LangSmith trace

Trace URL: https://smith.langchain.com/o/73978cd4-2623-4d25-ad61-24d621b74bd5/projects/p/fd1b485c-9e93-4499-a8f3-5de76415baa6?timeModel=%7B%22duration%22%3A%221d%22%7D&peek=20260609T034337Z88c3ee6d-a240-4eb0-91f9-dc3a67c2fdab&peekedConversationId=test-pr6-trace&trace_id=88c3ee6d-a240-4eb0-91f9-dc3a67c2fdab&run_id=20260609T034337Z88c3ee6d-a240-4eb0-91f9-dc3a67c2fdab&peeked_trace=20260609T034337999973Z88c3ee6d-a240-4eb0-91f9-dc3a67c2fdab

## Tradeoff reasoning

**Key decision: LLM-generated Markdown vs template filling**

The alternative was a Python template that fills pre-written Markdown sections with structured data. That would be faster (no LLM call) and deterministic. However, the LLM-generated approach produces significantly better output — it can rephrase, connect ideas across sections, add narrative flow, and handle missing content gracefully. A template would produce mechanical, disconnected text.

The tradeoff: one extra LLM call at the end of the session (cost + latency). Worth it for a deliverable meant to be handed directly to a developer.

Rejected alternative: generating the blueprint incrementally after each section. That would spread the cost but requires maintaining partial state and re-synthesising on each update — more complex with no clear benefit.

## Checklist

- [x] LangSmith trace attached
- [x] Tradeoff reasoning included
- [x] Tests pass locally (`uv run pytest tests/agents/ -v`)
- [x] No placeholder text in prompts