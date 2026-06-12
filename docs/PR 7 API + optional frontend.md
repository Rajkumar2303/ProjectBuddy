## What this PR does

Wires the frontend stubs to the live FastAPI backend and Supabase, completing the full ProjectBuddy pipeline (closes #11).

**Files changed:**
- `frontend/src/app/api/sections/route.ts` — Updated `FOUNDER_BUDDY_SECTIONS` map to `XBUDDY_SECTIONS` with the 5 correct section IDs; changed Supabase queries to filter by `agent_id='project-buddy'`
- `src/agents/xbuddy/nodes/memory_updater.py` — Agent ID set to `"project-buddy"` (consistent with database label)
- `src/agents/xbuddy/nodes/implementation.py` — Agent ID set to `"project-buddy"` for blueprint saves
- `src/integrations/supabase/supabase_client.py` — Default agent ID set to `"project-buddy"`

**FastAPI endpoints (already existing, verified working):**

| Endpoint | Method | Purpose |
|---|---|---|
| `/invoke` | POST | Single-response agent invocation |
| `/{agent_id}/invoke` | POST | Agent-specific single response |
| `/stream` | POST | SSE streaming agent response |
| `/{agent_id}/stream` | POST | Agent-specific SSE streaming |
| `/history` | POST | Retrieve chat history by thread_id |
| `/sync_section/{agent_id}/{section_id}` | POST | Sync edited section content |
| `/refine_section/{agent_id}/{section_id}` | POST | Refine section with AI |
| `/section_states/{agent_id}/{section_id}` | GET | Notify agent of section edits |
| `/info` | GET | Service metadata and available agents |
| `/feedback` | POST | Record LangSmith feedback |

**Frontend components (already existing, wired in previous work):**
- `ChatArea` — Sends `POST /api/chat`, parses SSE stream (tokens → message → final_response)
- `ProgressSidebar` — Calls `POST /api/sections` with `get-all-sections` to show section status
- `SectionDisplayPanel` — Calls `POST /api/sections` with `get-section-content` to display section content
- `BusinessPlanEditor` — Queries Supabase `business_plans` table for the final blueprint
- `ConfigPanel`, `ConversationHistory` — Utility components

**Agent ID convention (consistent across the stack):**
- `xbuddy` — FastAPI route registry key (e.g., `/xbuddy/invoke`)
- `project-buddy` — Supabase database label written by memory_updater and implementation_node

## LangSmith trace

Trace URL: https://smith.langchain.com/o/73978cd4-2623-4d25-ad61-24d621b74bd5/projects/p/fd1b485c-9e93-4499-a8f3-5de76415baa6?timeModel=%7B%22duration%22%3A%221d%22%7D&peek=20260609T042255Zff6f9c90-47bc-484f-a626-82b7b0d305e8&peekedConversationId=test-pr7-check&trace_id=ff6f9c90-47bc-484f-a626-82b7b0d305e8&run_id=20260609T042255Zff6f9c90-47bc-484f-a626-82b7b0d305e8&peeked_trace=20260609T042255523475Zff6f9c90-47bc-484f-a626-82b7b0d305e8

## Tradeoff reasoning

**Key decision: dual agent ID system (`xbuddy` vs `project-buddy`)**

The alternative was forcing a single identifier everywhere. However, the API routing layer (`agents.py`, FastAPI routes) and the database layer serve different purposes:
- The API key (`xbuddy`) identifies which agent graph to invoke — it's a routing concern
- The database label (`project-buddy`) identifies which records belong to this agent — it's a data concern

Keeping them separate means:
- Renaming the agent in the registry doesn't require a database migration
- Multiple agents can share the same database label if needed
- The frontend Supabase queries use `'project-buddy'` which matches exactly what the backend writes

Rejected alternative: changing the database label to match the API key. This would couple two independent concerns and make future multi-agent deployments harder.

## Checklist

- [x] LangSmith trace attached
- [x] Tradeoff reasoning included
- [x] Tests pass locally (`uv run pytest tests/agents/ -v`)
- [x] No placeholder text in prompts
- [x] Frontend runs (`cd frontend && npm run dev`)
- [x] Backend runs (`uv run python src/run_service.py`)
- [x] Full pipeline verified (106 agent tests passing)
