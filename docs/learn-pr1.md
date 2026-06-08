# PR 1: XBuddyState Schema + initialize_node — Learning Guide

## What is PR1?

PR1 is the **foundation** of the entire ProjectBuddy agent. It defines:
1. **What data the agent remembers** (the state schema)
2. **How a conversation starts** (the initialize node)

Everything else (routing, replying, deciding, saving) builds on top of this.

---

## Files changed in PR1

| File | Action | Purpose |
|---|---|---|
| `src/agents/xbuddy/enums.py` | Modified | Renamed generic SectionID values to domain-specific ones |
| `src/agents/xbuddy/models.py` | Modified | Defined all state schemas (XBuddyState, ProjectBuddyData, etc.) |
| `src/agents/xbuddy/nodes/initialize.py` | Modified | Implemented the initialize node (was a `NotImplementedError` stub) |
| `tests/agents/test_pr1_initialize.py` | Created | 36 unit tests covering all paths |
| `tests/agents/conftest.py` | Created | Path setup so pytest can find the `src/` package |
| `pyproject.toml` | Modified | Fixed langgraph version pin, added asyncio_mode |

---

## 1. enums.py — The vocabulary of the agent

### What are enums?

Enums (enumerations) are a way to define a fixed set of named values. Instead of using raw strings like `"project_idea"` or `"done"` scattered throughout the code, we define them in one place so:
- **Type safety** — Python can check you're using a valid value
- **Autocomplete** — your editor shows you the options
- **No typos** — `SectionStatus.DONE` vs `"donne"`

### Three enums defined

```python
class SectionStatus(str, Enum):   # str = enum values are strings
    PENDING = "pending"           # Section not started yet
    IN_PROGRESS = "in_progress"   # Currently being worked on
    DONE = "done"                 # Completed and user is satisfied

class RouterDirective(str, Enum):
    STAY = "stay"                 # Stay in current section
    NEXT = "next"                 # Move to next section
    MODIFY = "modify"             # Go back to a previous section (format: "modify:section_id")

class SectionID(str, Enum):
    PROJECT_IDEA = "project_idea"
    REQUIREMENTS = "requirements"
    ARCHITECTURE = "architecture"
    TECH_STACK = "tech_stack"
    IMPLEMENTATION = "implementation"
```

### What changed from the template

Before PR1, the template had `SECTION_1 = "section_1"` through `SECTION_5 = "section_5"` — generic placeholders. We renamed them to meaningful names that reflect the actual project planning domain.

### Why `str, Enum`?

Because the enum values will be stored in Supabase (a PostgreSQL database), which understands strings. The `str` mixin means `SectionID.PROJECT_IDEA == "project_idea"` evaluates to `True` — they compare directly to strings, so serialisation works without custom logic.

---

## 2. models.py — The data that flows through the graph

### What is the state?

In LangGraph, the **state** is a dictionary that every node can read and write. It's the "memory" of the agent. When you send a message, the graph runs through all the nodes, and each node can:
- Read fields from state (e.g., `state.get("current_section")`)
- Return changes to state (e.g., `return {"current_section": SectionID.REQUIREMENTS}`)

LangGraph merges the returned changes into the state automatically.

### The models (from simplest to most complex)

#### SectionContent
```python
class SectionContent(BaseModel):
    content: dict[str, Any]       # Rich text (for frontend display)
    plain_text: str | None = None # Plain text (for LLM processing)
```
Stores what was discussed in a section in two formats: rich JSON (for the frontend editor) and plain text (for the LLM).

#### SectionState
```python
class SectionState(BaseModel):
    section_id: SectionID
    content: SectionContent | None = None
    satisfaction_status: str | None = None   # "satisfied", "needs_improvement"
    status: SectionStatus = SectionStatus.PENDING
```
Tracks one section's progress. Each of the 5 sections has one of these.

#### ContextPacket
```python
class ContextPacket(BaseModel):
    section_id: SectionID
    status: SectionStatus
    system_prompt: str                    # The prompt for the LLM for this section
    draft: SectionContent | None = None   # Previously saved content
    validation_rules: dict | None = None  # Rules for validating user input
```
A lightweight package the `router` node builds and passes to `generate_reply`. It contains everything the LLM needs to generate a response for the current section.

#### ProjectBuddyData
```python
class ProjectBuddyData(BaseModel):
    # Section 1
    one_line_idea: str | None = None
    problem_statement: str | None = None
    target_users: list[str] = Field(default_factory=list)
    # ... 15 more fields across all 5 sections
```
This is the **structured data** extracted from the conversation. It's the agent's understanding of the user's project. Each field corresponds to something the agent asks about during one of the 5 sections. Fields use `default_factory=list` for list fields so every instance starts with empty lists instead of shared references.

#### ChatAgentDecision & ChatAgentOutput
```python
class ChatAgentDecision(BaseModel):
    router_directive: str            # "stay", "next", or "modify:section_id"
    user_satisfaction_feedback: str | None = None
    is_satisfied: bool | None = None
    should_save_content: bool = False

class ChatAgentOutput(BaseModel):
    reply: str                       # The actual response text
    router_directive: str            # Same as above
    # ... same fields as ChatAgentDecision
```
The `generate_decision` node produces a structured decision. `ChatAgentOutput` bundles both the reply text and the decision together. Both use `@field_validator` to ensure `router_directive` is always one of the three valid values.

#### XBuddyState (the main state)
```python
class XBuddyState(MessagesState):
    user_id: int = 1
    thread_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    current_section: SectionID = SectionID.PROJECT_IDEA
    context_packet: ContextPacket | None = None
    section_states: dict[str, SectionState] = Field(default_factory=dict)
    router_directive: str = RouterDirective.NEXT
    finished: bool = False
    user_data: ProjectBuddyData = Field(default_factory=ProjectBuddyData)
    short_memory: list[BaseMessage] = Field(default_factory=list)
    agent_output: ChatAgentOutput | None = None
    # ... more fields
```
This is the **central state** of the entire agent. It extends `MessagesState` (which provides `messages: list[BaseMessage]` — the conversation history). Every node reads and writes this state.

Key design choices:
- `thread_id` auto-generates as a UUID if not provided (supports both production and test scenarios)
- `current_section` defaults to `PROJECT_IDEA` — the conversation always starts at the beginning
- `section_states` is a dict keyed by section ID string (e.g. `"project_idea"`) for fast lookup

---

## 3. initialize_node — How a conversation starts

### What the node needs to do

When a user starts talking to ProjectBuddy, one of two things can happen:

1. **Cold start** — New conversation, no history exists. Set everything to defaults.
2. **Resume** — User is returning to an existing conversation. Load the saved state from Supabase.

### Step-by-step logic

```
initialize_node(state, config)
    │
    ├── 1. Resolve identity
    │     ├── Check config["configurable"]["thread_id"]     ← production path
    │     ├── Fall back to state["thread_id"]                ← in-graph resume
    │     └── Generate new UUID                              ← test/dev path
    │
    ├── 2. Try Supabase lookup
    │     ├── Success with rows → RESUME path
    │     ├── Success with empty → COLD START path
    │     └── Exception → log warning, COLD START fallback
    │
    ├── 3a. RESUME
    │     ├── Rebuild section_states from persisted rows
    │     ├── Skip corrupted rows (log warning)
    │     ├── Find first incomplete section → set current_section
    │     ├── Check if all done → set finished=True
    │     └── Return updated state (partial dict)
    │
    └── 3b. COLD START
          ├── Set current_section = PROJECT_IDEA
          ├── Init all 5 section_states as PENDING
          ├── Create empty ProjectBuddyData()
          ├── Set finished = False
          └── Return updated state (partial dict)
```

### Why return a partial dict (not the full state)?

LangGraph's `StateGraph` **merges** the returned dictionary into the existing state. This means:
- `initialize_node` only returns the fields it changes
- Fields like `messages` or `agent_output` are left untouched
- If a field is not returned, its previous value is preserved

This is a key pattern in LangGraph — nodes are **incremental**, not wholesale.

### Edge cases handled

| Scenario | What happens |
|---|---|
| No `thread_id` in config or state | A new UUID is generated |
| Supabase is down or unreachable | Warning logged, cold start used |
| Corrupted row (unknown section_id) | Row skipped with warning, valid rows still used |
| All rows corrupted | Falls through to cold start |
| `config` is `None` | Treated as empty dict, falls back to state/generated values |
| `error_count` was high from previous run | Reset to 0 on cold start |

### Private helper functions

```python
SECTION_ORDER = [
    SectionID.PROJECT_IDEA, SectionID.REQUIREMENTS,
    SectionID.ARCHITECTURE, SectionID.TECH_STACK, SectionID.IMPLEMENTATION
]
```

- **`_build_section_state(row)`** — Converts a raw Supabase row dict into a `SectionState` object. Handles null content, validates the section_id, and raises `ValueError` for unknown values.
- **`_first_incomplete_section(states)`** — Walks `SECTION_ORDER` in order and returns the first section whose status is not DONE. If all are somehow DONE, returns the last one.
- **`_all_sections_done(states)`** — Returns True only if every section in `SECTION_ORDER` has status DONE.
- **`_fetch_section_states(user_id, thread_id)`** — Lazy-imports `SupabaseClient` and calls `get_section_states()`. This is wrapped in `asyncio.to_thread()` because the Supabase client is synchronous.

### Why lazy import for SupabaseClient?

```python
def _fetch_section_states(user_id: int, thread_id: str) -> list[dict[str, Any]]:
    from integrations.supabase.supabase_client import SupabaseClient  # lazy import
    return SupabaseClient().get_section_states(user_id, thread_id)
```

The `initialize_node` is imported by `graph/builder.py`, which runs at module load time. If `SupabaseClient` raised an error at import (e.g., missing env vars), the entire graph would fail to build. The lazy import defers the Supabase import until the node is actually executed.

---

## What was NOT done in PR1 (and why)

| Thing | Why NOT in PR1 |
|---|---|
| Router logic | PR2's job — reads the directive and loads section prompts |
| LLM calls | PR3's job — `generate_reply` and `generate_decision` |
| Supabase persistence | PR4's job — `memory_updater` writes state to DB |
| Final blueprint generation | PR5's job — `implementation_node` |
| API endpoints | PR6's job — FastAPI `/invoke`, `/stream`, `/history` |
| Section prompts | PR2's job — defined per-section in `sections/` directory |

PR1 is deliberately narrow: define the state, and start the conversation.

---

## How to verify PR1

1. **Tests pass**: `uv run pytest tests/agents/test_pr1_initialize.py -v` → 36/36 passed
2. **Imports work**: The module can be imported without errors
3. **Cold start produces correct defaults**: `current_section = PROJECT_IDEA`, all sections PENDING
4. **Resume restores correctly**: Given mock Supabase rows, the node rebuilds section_states and finds the right section

---

## Key files reference

| File | Purpose |
|---|---|
| `src/agents/xbuddy/enums.py` | SectionID, SectionStatus, RouterDirective |
| `src/agents/xbuddy/models.py` | All Pydantic models (state schemas) |
| `src/agents/xbuddy/nodes/initialize.py` | Initialize node implementation |
| `src/agents/xbuddy/graph/builder.py` | Wires all nodes into a StateGraph |
| `tests/agents/test_pr1_initialize.py` | 36 tests for PR1 |
| `conftest.py` | Root pytest config for path setup |
