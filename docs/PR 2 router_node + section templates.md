## What this PR does

Implements `router_node` and section templates for ProjectBuddy (closes #6).

**Files changed:**
- `src/agents/xbuddy/sections/project_idea.py` — Section 1: Project Idea & Goals prompt
- `src/agents/xbuddy/sections/requirements.py` — Section 2: Requirements Gathering prompt
- `src/agents/xbuddy/sections/architecture.py` — Section 3: Architecture Design prompt
- `src/agents/xbuddy/sections/tech_stack.py` — Section 4: Technology Selection prompt
- `src/agents/xbuddy/sections/implementation.py` — Section 5: Implementation Planning prompt
- `src/agents/xbuddy/sections/__init__.py` — Exports all section prompts
- `src/agents/xbuddy/sections/base_prompt.py` — Updated BASE_RULES with ProjectBuddy persona
- `src/agents/xbuddy/prompts.py` — Template mapping, `build_system_prompt()`, navigation helpers
- `src/agents/xbuddy/nodes/router.py` — Full `router_node` implementation
- `tests/agents/test_pr2_router.py` — 26 unit tests

**router_node behaviour:**
- **STAY** → keeps current section, builds ContextPacket
- **NEXT** → advances to next section in SECTION_ORDER (stays at last)
- **MODIFY** → parses `"modify:<section_id>"`, jumps to that section (validated)
- **finished=True** → section unchanged (graph routes to END via conditional edge)
- Builds `ContextPacket` with `system_prompt` (base rules + section prompt) and `draft` from persisted section content
- Resets `router_directive` to STAY after processing

## LangSmith trace

Trace URL: https://smith.langchain.com/o/73978cd4-2623-4d25-ad61-24d621b74bd5/projects/p/fd1b485c-9e93-4499-a8f3-5de76415baa6?timeModel=%7B%22duration%22%3A%221d%22%7D&peek=20260608T182719Zf0f4e5a9-6e99-4566-92c0-22ecdaacce2f&peekedConversationId=test-pr2-trace&trace_id=f0f4e5a9-6e99-4566-92c0-22ecdaacce2f&run_id=20260608T182719Zf0f4e5a9-6e99-4566-92c0-22ecdaacce2f&peeked_trace=20260608T182719840225Zf0f4e5a9-6e99-4566-92c0-22ecdaacce2f

## Tradeoff reasoning

**Key decision: file-per-section prompts vs single dict**

The alternative was a single monolithic dict with all 5 prompts in one file. That would be simpler for the machine but worse for the developer — editing one section's prompt means touching a file with all 5 prompts, creating merge conflicts when two people work on different sections, and making it harder to review changes.

File-per-section (`project_idea.py`, `requirements.py`, etc.) means:
- Each prompt is independently editable and reviewable in isolation
- Git history shows exactly which section changed per commit
- The `sections/__init__.py` + `prompts.py` mapping layer is a clean adapter — adding Section 6 would be one new file + one line in the dict
- Each prompt module can independently grow without creating merge conflicts

The tradeoff: more files. Worth it for a project that will have 5 distinct, long-form prompts that will be iterated on independently.

## Checklist

- [x] LangSmith trace attached
- [x] Tradeoff reasoning included
- [x] Tests pass locally (`uv run pytest tests/agents/ -v`)
- [x] No placeholder text in prompts
