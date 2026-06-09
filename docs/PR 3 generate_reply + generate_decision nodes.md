## What this PR does

Implements `generate_reply_node` and `generate_decision_node` for ProjectBuddy (closes #7).

**Files changed:**
- `src/agents/xbuddy/nodes/generate_reply.py` — Calls LLM with `ContextPacket` (system prompt + draft), appends `AIMessage` to state, updates `short_memory`
- `src/agents/xbuddy/nodes/generate_decision.py` — Calls LLM with structured output (`ChatAgentDecision`), handles NEXT/STAY/MODIFY directives, marks sections DONE, triggers final blueprint when all sections complete
- `tests/agents/test_pr3_generate.py` — 21 unit tests

**generate_reply_node behaviour:**
- Reads `context_packet` from state (set by `router_node`)
- Builds messages: `SystemMessage(system_prompt)` → optional draft `HumanMessage` → conversation history
- Calls LLM via `get_model().ainvoke(messages)`
- Appends `AIMessage` to `state["messages"]` and `short_memory` (rolling window of 10)
- Sets `awaiting_user_input = True`

**generate_decision_node behaviour:**
- Reads current section, `context_packet`, and last 6 messages
- Calls LLM with `with_structured_output(ChatAgentDecision)` for structured JSON
- **NEXT** → marks current section as DONE, checks if all sections complete → sets `finished=True`, `should_generate_final_output=True`
- **STAY** → keeps section in progress, optionally saves content
- **MODIFY** → sets `router_directive` to `"modify:<section_id>"`
- Stores the decision in `agent_output`

## LangSmith trace

Trace URL: https://smith.langchain.com/o/73978cd4-2623-4d25-ad61-24d621b74bd5/projects/p/fd1b485c-9e93-4499-a8f3-5de76415baa6?timeModel=%7B%22duration%22%3A%221d%22%7D&peek=20260609T003153Z4fe589b7-6517-40f4-9146-823481a731c6&peekedConversationId=test-pr3-trace&trace_id=4fe589b7-6517-40f4-9146-823481a731c6&run_id=20260609T003153Z4fe589b7-6517-40f4-9146-823481a731c6&peeked_trace=20260609T003153498523Z4fe589b7-6517-40f4-9146-823481a731c6

## Tradeoff reasoning

**Key decision: two separate nodes (generate_reply + generate_decision) vs one combined node**

The alternative was a single node that both generates the reply and decides the next action. That would halve the LLM calls but introduces a critical UX problem: the reply must begin streaming to the user before structured JSON parsing can happen. Combining them means the entire response must be generated before either the reply or the decision is available.

The two-node approach:
- `generate_reply` calls the LLM with a standard chat prompt → the response streams immediately to the user
- `generate_decision` calls the LLM *again* with a structured output schema → produces a machine-parseable `ChatAgentDecision` that the graph uses for routing

The cost is an extra LLM call per turn. The benefit is real-time streaming UX and clean separation of concerns (reply generation vs navigation logic).

Rejected alternative: rule-based decision parsing (e.g., keyword matching on user messages). This would be cheaper but cannot reliably detect satisfaction, handle section transitions, or parse complex "modify" requests from natural language.

## Checklist

- [x] LangSmith trace attached
- [x] Tradeoff reasoning included
- [x] Tests pass locally (`uv run pytest tests/agents/ -v`)
- [x] No placeholder text in prompts