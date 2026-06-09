## What this PR does

Completes the full graph assembly and adds end-to-end tests for the XBuddy agent loop (closes #9).

**Files changed:**
- `src/agents/xbuddy/graph/routes.py` — `route_after_memory_updater` now returns `END` instead of routing to the unimplemented `implementation_node`
- `src/agents/xbuddy/graph/builder.py` — Removed `implementation_node` from the graph; added `END: END` to the conditional edge mapping
- `tests/agents/test_pr5_graph.py` — 5 end-to-end graph tests

**Graph structure (fully assembled):**  

```
START → initialize → router → generate_reply → generate_decision
            ^                                          │
            └─────────── memory_updater ←───────────────┘
                                   │
                                   └──→ END  (when finished=True)
```

**What was already built (PRs 1-4) and now connected:**
- `initialize_node` — cold-start vs resume detection
- `router_node` — STAY/NEXT/MODIFY dispatch, builds ContextPacket
- `generate_reply_node` — LLM call with section prompt, appends AIMessage
- `generate_decision_node` — JSON-based decision parsing, sets directive
- `memory_updater_node` — persists section states + messages to Supabase

**New in PR5:**
- `route_after_memory_updater` checks `should_generate_final_output` → routes to `END` (implementation_node will be added in a later PR to synthesise the final Project Blueprint)
- End-to-end tests verify the full cycle: cold start → router → generate_reply → generate_decision → memory_updater → loop back

## LangSmith trace

Trace URL: https://smith.langchain.com/o/73978cd4-2623-4d25-ad61-24d621b74bd5/projects/p/fd1b485c-9e93-4499-a8f3-5de76415baa6?timeModel=%7B%22duration%22%3A%221d%22%7D&peek=20260609T025538Z3ba54b10-8d78-42ad-8c35-9b6400538b6d&peekedConversationId=test-pr5-trace&trace_id=3ba54b10-8d78-42ad-8c35-9b6400538b6d&run_id=20260609T025538Z3ba54b10-8d78-42ad-8c35-9b6400538b6d&peeked_trace=20260609T025538364560Z3ba54b10-8d78-42ad-8c35-9b6400538b6d

## Tradeoff reasoning

**Key decision: routing to END vs routing to implementation_node stub**

The `implementation_node` (which will synthesise the final Project Blueprint Markdown) is not built yet. The two options were:

1. **Keep `implementation_node` in the graph** — would crash on `NotImplementedError` when all 5 sections complete, breaking the user experience
2. **Route to `END` directly** — the graph terminates cleanly when all sections are done; no crash, no partial output

Chose option 2 because a clean termination is strictly better than a crash. The `implementation_node` will be added as a follow-up PR, at which point `route_after_memory_updater` will return `"implementation"` instead of `END` and the graph will produce the final artifact.

Rejected alternative: making `implementation_node` a no-op that passes through. That would silently drop the final blueprint generation rather than failing visibly.

## Checklist

- [x] LangSmith trace attached
- [x] Tradeoff reasoning included
- [x] Tests pass locally (`uv run pytest tests/agents/ -v`)
- [x] No placeholder text in prompts