## What this PR does

Implements `memory_updater_node` and Supabase conversation message persistence for ProjectBuddy (closes #8).

**Files changed:**
- `src/agents/xbuddy/nodes/memory_updater.py` — Iterates `section_states`, persists each with content or DONE status via `save_section_state()`; persists the latest `AIMessage` via `save_conversation_message()`; returns `{}` (pure side-effect node)
- `src/integrations/supabase/supabase_client.py` — Added `save_conversation_message()` method; inserts into `conversation_messages` table with role, content, agent_id, metadata
- `tests/agents/test_pr4_memory.py` — 9 unit tests

**memory_updater_node behaviour:**
- Iterates `section_states` in state; calls `save_section_state()` for each section where `content is not None` OR `status == DONE`
- Skips PENDING sections with no content (avoids writing null JSONB rows)
- Saves the latest `AIMessage` (assistant reply) via `save_conversation_message()` with `role="ai"`
- Always passes `agent_id="project-buddy"` to all persistence calls
- Returns empty dict `{}` — pure side-effect node; Supabase errors are logged, never crash the graph

**Supabase schema (already existing in migration):**
- `section_states` — `section_id`, `content` (JSONB), `plain_text`, `status`, `satisfaction_status`
- `conversation_messages` — `role`, `content`, `agent_id`, `metadata` (JSONB)

## LangSmith trace

Trace URL: https://smith.langchain.com/o/73978cd4-2623-4d25-ad61-24d621b74bd5/projects/p/fd1b485c-9e93-4499-a8f3-5de76415baa6?timeModel=%7B%22duration%22%3A%221d%22%7D&peek=20260609T021546Za928aa6f-0c34-4e20-9dc6-4bc3883a6a69&peekedConversationId=test-pr4-trace&trace_id=a928aa6f-0c34-4e20-9dc6-4bc3883a6a69&run_id=20260609T021546Za928aa6f-0c34-4e20-9dc6-4bc3883a6a69&peeked_trace=20260609T021546383895Za928aa6f-0c34-4e20-9dc6-4bc3883a6a69

## Tradeoff reasoning

**Key decision: always-on persistence vs conditional writes**

The alternative was a conditional edge that only runs `memory_updater` when `should_save_content=True` or `router_directive="next"`. That would save a Supabase call on turns where nothing changes. However, it adds complexity to the graph (another conditional edge, more state flags to track) and Supabase upserts are cheap.

The always-on approach means:
- Every turn persists section state and the latest message
- The graph has a fixed `generate_decision → memory_updater → router/implementation` edge — no extra conditional logic
- `initialize_node` always has fresh data to resume from
- The cost is one extra Supabase call per turn that sometimes writes nothing (PENDING sections are skipped)

Rejected alternative: passing `SectionState`/`SectionContent` objects directly to `SupabaseClient`. The client methods take raw primitives (dict, str, etc.), so `memory_updater` does the object-to-primitive mapping. Keeping the client generic avoids coupling it to the agent's model layer.

## Checklist

- [x] LangSmith trace attached
- [x] Tradeoff reasoning included
- [x] Tests pass locally (`uv run pytest tests/agents/ -v`)
- [x] No placeholder text in prompts