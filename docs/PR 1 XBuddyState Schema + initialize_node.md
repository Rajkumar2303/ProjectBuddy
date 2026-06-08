## What this PR does

Implements the full state schema and `initialize_node` for ProjectBuddy (closes #5).

**Files changed:**
- `src/agents/xbuddy/enums.py` — `SectionID` renamed to domain-specific values: `PROJECT_IDEA → REQUIREMENTS → ARCHITECTURE → TECH_STACK → IMPLEMENTATION`
- `src/agents/xbuddy/models.py` — Defines `XBuddyState`, `ProjectBuddyData` (18 typed fields across 5 sections), `SectionState`, `ContextPacket`, `ChatAgentOutput`, `ChatAgentDecision`
- `src/agents/xbuddy/nodes/initialize.py` — Full cold-start + resume implementation with Supabase integration
- `tests/agents/test_pr1_initialize.py` — 25 unit tests covering both paths and all edge cases

**initialize_node behaviour:**
- Reads `thread_id` / `user_id` from `config["configurable"]`, state fallback, or generates a new UUID
- Queries `SupabaseClient.get_section_states(user_id, thread_id)` via `asyncio.to_thread`
- **Resume path** — rebuilds `section_states` from persisted rows, resolves `current_section` to the first non-DONE section, sets `finished=True` if all 5 are DONE
- **Cold start path** — all sections initialised as PENDING, `current_section = SectionID.PROJECT_IDEA`, fresh `ProjectBuddyData()`
- **Edge cases handled** — Supabase unavailable (warning + cold start fallback), corrupted individual rows (skipped, partial recovery), all rows corrupted (cold start), `None` config

## LangSmith trace

<!-- Paste your LangSmith trace URL here. Every PR must include one. -->

Trace URL: https://smith.langchain.com/o/73978cd4-2623-4d25-ad61-24d621b74bd5/projects/p/fd1b485c-9e93-4499-a8f3-5de76415baa6?timeModel=%7B%22duration%22%3A%221d%22%7D&peek=20260608T162532Zd1450fd2-b356-4a25-ba3e-5f715e6b85a9&peekedConversationId=test-pr1-trace&conversationTab=overview&trace_id=d1450fd2-b356-4a25-ba3e-5f715e6b85a9&run_id=20260608T162532Zd1450fd2-b356-4a25-ba3e-5f715e6b85a9&peeked_trace=20260608T162532975755Zd1450fd2-b356-4a25-ba3e-5f715e6b85a9

## Tradeoff reasoning

**Key decision: two-step identity resolution (config → state → generated UUID)**

The alternative was to require `thread_id` to always be passed in `config["configurable"]` and raise if missing. That would be simpler but would crash on first invocation before the caller has a chance to set up a thread ID (e.g. during local development or tests without a full service layer).

The chosen approach degrades gracefully: config is checked first (production path), state is used as fallback (in-graph resume), and a new UUID is generated as last resort (test / dev path). The generated UUID is returned in the state dict so all downstream nodes see a consistent identity regardless of which path fired.

Rejected alternative: merging initialize into `router_node`. The initialize node is a pure setup step — it does I/O (Supabase lookup) and sets defaults. Router is dynamic dispatch that reads the directive and loads section prompts. Keeping them separate makes each node independently testable and keeps side-effects out of the routing logic.

## Checklist

- [x] LangSmith trace attached
- [x] Tradeoff reasoning included
- [x] Tests pass locally (`uv run pytest tests/agents/test_pr1_initialize.py -v`)
- [x] No placeholder text in prompts