---
name: "Stage 2: Design"
about: Architecture and state design for your XBuddy agent
title: "[Design] ProjectBuddy"
labels: stage-2
---

## Node diagram

```
START
  │
  ▼
initialize          ← Sets up user_id, thread_id, initial section states
  │
  ▼
router              ← Loads section prompt, builds ContextPacket, checks if finished
  │
  ├─[finished=True, no pending input]──────────────────────────────► END
  │
  ▼
generate_reply      ← Streams LLM response using section system prompt + messages
  │
  ▼
generate_decision   ← Structured LLM call → RouterDirective (stay/next/modify:N)
  │
  ▼
memory_updater      ← Updates SectionState, saves to Supabase, sets flags
  │
  ├─[should_generate_final_output=True]──► implementation ──► END
  │
  └─[otherwise]────────────────────────────────────────────► router (loop)
```

**Conditional edges:**
- `router → generate_reply | END` — if no pending human message and state is awaiting input → END (yield turn to user)
- `memory_updater → implementation | router` — when all 5 sections are DONE → implementation; else loop

## State schema

```python
class SectionID(str, Enum):
    PROJECT_IDEA      = "project_idea"       # Section 1: Project Idea & Goals
    REQUIREMENTS      = "requirements"        # Section 2: Requirements Gathering
    ARCHITECTURE      = "architecture"        # Section 3: Architecture Design
    TECH_STACK        = "tech_stack"          # Section 4: Technology Selection
    IMPLEMENTATION    = "implementation_plan" # Section 5: Implementation Planning


class ProjectBuddyData(BaseModel):
    """Structured data extracted from the user across all 5 sections."""

    # Section 1 — Project Idea & Goals
    one_line_idea: str | None = None
    problem_statement: str | None = None          # what + who + why existing solutions fail
    target_users: list[str] = Field(default_factory=list)
    success_outcome: str | None = None
    hard_constraints: list[str] = Field(default_factory=list)  # time, budget, team, platform

    # Section 2 — Requirements
    functional_requirements: list[str] = Field(default_factory=list)  # verb-noun format
    non_functional_requirements: list[str] = Field(default_factory=list)  # with measurable targets
    user_stories: list[str] = Field(default_factory=list)    # "As a X, I want Y, so that Z"
    system_inputs: list[str] = Field(default_factory=list)
    system_outputs: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)

    # Section 3 — Architecture
    system_components: list[str] = Field(default_factory=list)
    data_flows: list[str] = Field(default_factory=list)
    architecture_style: str | None = None    # e.g. "frontend/backend split", "monolith"
    external_integrations: list[str] = Field(default_factory=list)
    ai_ml_components: list[str] = Field(default_factory=list)  # or ["N/A"]
    storage_strategy: str | None = None

    # Section 4 — Tech Stack
    language_frameworks: dict[str, str] = Field(default_factory=dict)  # component → choice
    database_choice: str | None = None
    deployment_target: str | None = None
    tooling: dict[str, str] = Field(default_factory=dict)    # ci_cd, monitoring, testing

    # Section 5 — Implementation Planning
    mvp_features: list[str] = Field(default_factory=list)
    development_phases: list[dict] = Field(default_factory=list)  # [{phase, deliverables}]
    risks: list[dict] = Field(default_factory=list)               # [{risk, likelihood, mitigation}]
    testing_strategy: str | None = None
    definition_of_done: str | None = None


class ProjectBuddyState(MessagesState):
    """Full LangGraph state for ProjectBuddy."""

    # Identity
    user_id: int = 1
    thread_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # Navigation
    current_section: SectionID = SectionID.PROJECT_IDEA
    context_packet: ContextPacket | None = None
    section_states: dict[str, SectionState] = Field(default_factory=dict)
    router_directive: str = RouterDirective.NEXT
    finished: bool = False

    # Extracted domain data
    user_data: ProjectBuddyData = Field(default_factory=ProjectBuddyData)

    # Conversation window (last N messages for LLM context)
    short_memory: list[BaseMessage] = Field(default_factory=list)

    # Per-turn agent output
    agent_output: ChatAgentOutput | None = None
    awaiting_user_input: bool = False
    awaiting_satisfaction_feedback: bool = False

    # Error tracking
    error_count: int = 0
    last_error: str | None = None

    # Final artifact
    final_output: str | None = None           # Rendered Project Blueprint (Markdown)
    should_generate_final_output: bool = False
```

## Supabase tables

### `project_blueprints`
Stores the final synthesized Project Blueprint Markdown document.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | Auto-generated |
| `user_id` | INTEGER | Identifies the user |
| `thread_id` | TEXT | Unique per conversation |
| `agent_id` | TEXT | `'project-buddy'` |
| `title` | TEXT | Derived from `one_line_idea` |
| `content` | TEXT | Full Markdown blueprint |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |
| UNIQUE | `(user_id, thread_id)` | One blueprint per session |

**Why:** The Project Blueprint is the primary user deliverable — it must survive page reloads and be downloadable as `PROJECT_SPEC.md`.

---

### `section_states`
Persists the structured content of each of the 5 sections as it is built up turn by turn.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | INTEGER | |
| `thread_id` | TEXT | |
| `agent_id` | TEXT | `'project-buddy'` |
| `section_id` | TEXT | `project_idea`, `requirements`, `architecture`, `tech_stack`, `implementation_plan` |
| `content` | JSONB | Tiptap JSON — rich text for frontend display |
| `plain_text` | TEXT | Flat version for LLM context windows |
| `status` | TEXT | `pending` / `in_progress` / `done` |
| `satisfaction_status` | TEXT | `satisfied` / `needs_improvement` / null |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |
| UNIQUE | `(user_id, thread_id, section_id)` | One row per section per session |

**Why:** Sections can be revisited via `modify:<section_id>`. Persisting each section separately allows the frontend to display the ProgressSidebar correctly and lets the `router` reload prior content when a user navigates back.

---

### `conversation_messages`
Full message history for `/history` endpoint and LangSmith debugging.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `user_id` | INTEGER | |
| `thread_id` | TEXT | |
| `agent_id` | TEXT | `'project-buddy'` |
| `role` | TEXT | `user` / `assistant` |
| `content` | TEXT | Raw message content |
| `metadata` | JSONB | `run_id`, `section_id`, token counts |
| `created_at` | TIMESTAMPTZ | |

**Why:** The in-memory LangGraph checkpointer is reset on service restart. This table is the durable store for the `/history` API and for post-session LangSmith eval uploads.

## Design decisions

### Why these 6 nodes?

| Node | Responsibility | Alternative considered |
|---|---|---|
| `initialize` | Cold-start vs resume detection; sets `current_section` from persisted data | Merging into `router` — rejected because initialize is stateless setup, router is dynamic dispatch |
| `router` | Loads the section system prompt + prior content into `ContextPacket` | Inline in `generate_reply` — rejected because prompt loading is I/O and should be isolated for testability |
| `generate_reply` | Streams the conversational response to the user | Single combined reply+decision node — rejected because streaming must begin before structured parsing |
| `generate_decision` | Structured LLM call to extract `RouterDirective` + whether to save content | Rule-based parsing — rejected; natural language inputs require LLM to interpret intent |
| `memory_updater` | Writes `ProjectBuddyData` fields + `SectionState` to Supabase, sets `should_generate_final_output` | Inline in `generate_decision` — rejected because persistence is a side-effect, not a navigation decision |
| `implementation` | Synthesizes all 5 `SectionState` contents into the Project Blueprint Markdown | Streaming directly from `memory_updater` — rejected; blueprint generation needs full context assembled cleanly |

### Why this section order?

The 5 sections form a strict **dependency chain** — each section's output is a required input to the next:

```
Project Idea → Requirements → Architecture → Tech Stack → Implementation Plan
```

- You cannot gather **requirements** (Section 2) without knowing the **problem and constraints** (Section 1).
- You cannot design **architecture** (Section 3) without knowing what behaviors must be supported (Section 2).
- You cannot choose a **tech stack** (Section 4) without knowing the architecture — picking tools before knowing the structure leads to mismatched choices (e.g. a relational DB for a graph-structured problem).
- You cannot plan **implementation phases** (Section 5) until the full system is defined — estimates made before this collapse on first contact with reality.

### What happens if a user wants to skip ahead?

The agent enforces section order. The `router` only advances `current_section` when the current section's acceptance criteria are met (via `generate_decision → RouterDirective.NEXT`). A user saying "skip to tech stack" will be acknowledged but not actioned — the agent will explain what information is still missing and continue probing.

The `modify:<section_id>` directive *does* allow returning to a prior section (e.g. to correct a mistake in Section 1 mid-session). It does **not** allow jumping to a future section that has not been reached yet.

### Why two LLM calls per turn (generate_reply + generate_decision)?

Streaming (`generate_reply`) must begin before structured JSON parsing (`generate_decision`) can run. Combining them into a single structured-output call would block the stream until the full response is generated, destroying the real-time feel. The two-node approach lets the user see the reply streaming immediately while the decision is extracted as a follow-up.

### LangSmith tracing

Every graph invocation is traced via LangSmith. Each node emits a named span. The `metadata` column in `conversation_messages` stores the `run_id` so traces can be looked up per message in post-session evals.
