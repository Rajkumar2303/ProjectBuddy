# Stage 1 & 2: Requirements + Design — Learning Guide

## What are we building?

**ProjectBuddy** is a conversational AI agent (a "XBuddy") that guides users through a structured 5-section dialogue to produce a **Project Blueprint** — a complete, downloadable Markdown document describing their project idea, requirements, architecture, tech stack, and implementation plan.

Think of it as an AI-powered project planning consultant that lives in a chat interface.

---

## Stage 1: Requirements (Why this agent exists)

### The problem being solved

People have project ideas but lack structured system design experience. They can think **in ideas** but not **in systems**. Existing tools (Notion templates, Google Docs, static forms) are **passive** — they can't react to vague input, ask follow-ups, or maintain context across planning stages.

### Why this needs an AI agent (not a form)

| What a static form does | What this AI agent does |
|---|---|
| Shows blank fields and waits | Detects vague answers and asks targeted follow-ups |
| Treats each section independently | Maintains dependency context across all 5 sections |
| Can't adapt | Adapts the architecture discussion based on what was said in requirements |
| Produces disconnected answers | Synthesises a coherent final artifact from multi-turn conversation |

### The 4 LLM-specific capabilities leveraged

1. **Iterative clarification** — vague inputs are probed before advancing
2. **Dependency-aware sequencing** — requirements → architecture → tech stack → execution (order is non-negotiable)
3. **Structured decomposition** — complex systems are broken into independently reviewable components
4. **Memory across turns** — decisions in Section 1 constrain choices in Section 4

### User personas

**Primary:**
- Software engineering students (final year / grad) preparing capstone projects
- Early-career developers (0–3 years) building portfolio projects
- AI/ML engineers who understand models but not full-stack architecture
- Startup founders validating feasibility before hiring a dev team

**Secondary:**
- Hackathon participants needing a structured plan in < 24 hours
- Solo indie developers with no formal planning experience

### The 5 conversation sections (the core structure)

```
Section 1: Project Idea & Goals
    ↓  (establishes the north star)
Section 2: Requirements Gathering
    ↓  (transforms goals into verifiable contracts)
Section 3: Architecture Design
    ↓  (translates requirements into structural decisions)
Section 4: Technology Selection
    ↓  (tech stack is a consequence of architecture)
Section 5: Implementation Planning
    (only after full system definition can execution be planned)
```

Each section has:
- **What it collects** — specific data points the agent extracts
- **Why it's at this position** — dependency justification
- **Transition trigger** — measurable criteria the agent checks before advancing

### The final output: Project Blueprint

A 16-section Markdown document generated at the end, designed to be handed directly to a developer or committed as `PROJECT_SPEC.md`.

### Guardrails (what the agent must/must not do)

**Must:**
- Complete sections in order 1→5 (no jumping ahead)
- Paraphrase and confirm understanding before advancing
- Ask at most 2–3 questions per turn
- Tell the user when a section is complete and what comes next
- Flag contradictions between sections

**Must not:**
- Generate code (this is a planning tool, not a code generator)
- Accept vague answers like "it depends" without probing
- Skip acceptance criteria
- Propose a tech stack before architecture is complete
- Produce a final blueprint if any section is incomplete

---

## Stage 2: Design (How the architecture works)

### The LangGraph node diagram

```
START
  │
  ▼
initialize          ← Sets up user_id, thread_id, initial section states
  │
  ▼
router              ← Loads section prompt, builds ContextPacket, checks if finished
  │
  ├─[finished=True, no pending input]──────────────────► END
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
  └─[otherwise]────────────────────────────► router (loop back)
```

This is a **StateGraph** — each node receives the full state, modifies it, and returns an updated state. The graph loops until all 5 sections are done, then produces the final blueprint.

### Why these 6 nodes?

| Node | Job | Why separate? |
|---|---|---|
| `initialize` | Cold-start vs resume detection | Pure setup + I/O (Supabase lookup). Keeps side-effects out of routing. |
| `router` | Loads section prompt into ContextPacket | Dynamic dispatch — reads the directive and loads context. Isolated for testability. |
| `generate_reply` | Streams conversational response | Must begin streaming before structured parsing runs (UX requirement). |
| `generate_decision` | Extracts RouterDirective via structured LLM call | Requires full response + JSON parsing, separate from streaming. |
| `memory_updater` | Writes to Supabase, sets flags | Persistence is a side-effect, not a navigation decision. |
| `implementation` | Synthesises the Project Blueprint | Needs all 5 sections fully assembled — run once at end. |

### Why two LLM calls per turn?

`generate_reply` streams the reply immediately so the user sees text appearing in real time. `generate_decision` then runs a second structured LLM call to parse the route directive from the full conversation. Combining them would block streaming until the entire response is generated, destroying the real-time feel.

### Why non-negotiable section order?

```
Project Idea → Requirements → Architecture → Tech Stack → Implementation Plan
```

Each section's output is a required input to the next. You cannot:
- Gather requirements without knowing the problem
- Design architecture without knowing requirements
- Choose a tech stack without knowing the architecture
- Plan implementation phases before the full system is defined

### Supabase tables (what gets persisted)

Three tables:

1. **`section_states`** — Per-section content + status. Supports modifying a prior section and resuming sessions across page reloads.
2. **`project_blueprints`** — The final Markdown blueprint. One row per session (unique on `user_id + thread_id`).
3. **`conversation_messages`** — Full message history. Used by the `/history` API endpoint and for debugging.

---

## Key files and what they define

| File | What it contains |
|---|---|
| `.github/ISSUE_TEMPLATE/01-requirements.md` | Stage 1 requirements doc — the "why" |
| `.github/ISSUE_TEMPLATE/02-design.md` | Stage 2 design doc — the "how" |
| `src/agents/xbuddy/enums.py` | SectionID, SectionStatus, RouterDirective enums |
| `src/agents/xbuddy/models.py` | XBuddyState, ProjectBuddyData, SectionState, ContextPacket, etc. |
| `src/agents/xbuddy/graph/builder.py` | StateGraph wiring — connects all 6 nodes |
| `src/agents/xbuddy/nodes/*.py` | Each node's implementation |
| `src/integrations/supabase/supabase_client.py` | Database CRUD operations |

---

## Expected outputs

1. **A running FastAPI service** with `/invoke`, `/stream`, and `/history` endpoints
2. **A LangGraph agent** that walks users through 5 sections conversationally
3. **A Project Blueprint** — downloadable Markdown document synthesised from the conversation
4. **LangSmith traces** for every graph invocation (debugging + evals)
