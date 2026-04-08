# XBuddy Template

Starter template for the **AI Engineer Residency**. You'll build your own XBuddy — a conversational AI agent that guides users through a structured multi-section dialogue using LangGraph.

## What you're building

Your XBuddy is a domain-specific agent that:
- Guides users through 5 conversation sections
- Remembers context across turns
- Streams responses in real time
- Persists state to Supabase
- Produces a final output artifact

Choose your domain at signup: **StudentBuddy** / **JobBuddy** / **FitnessBuddy**

## Architecture

Your agent follows the same graph pattern as [FounderBuddy](https://github.com/Victoria824/FounderBuddy):

```
START → initialize → router → generate_reply → generate_decision
                        ↑                             ↓
                        └──────── memory_updater ─────┘
                                       ↓
                               implementation → END
```

## Getting started

### Prerequisites
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- An OpenAI or Anthropic API key

### Setup

```bash
# Install dependencies
uv sync

# Copy environment config
cp .env.example .env
# Edit .env with your API keys

# Run the service
uv run python src/run_service.py
```

The API will be available at `http://localhost:8080`.

### Frontend (optional)

```bash
cd frontend
npm install
cp .env.example .env.local
# Edit .env.local with your Supabase keys
npm run dev
```

## Your first task

**Start with Issue #1** in this repo. Fill in your requirements directly in the issue. When you're done, tag @MOSS in Slack with the issue link.

Don't write any code until MOSS signs off on your requirements.

## Project structure

```
src/
├── agents/
│   ├── agents.py              # Agent registry
│   └── xbuddy/                # Your agent — this is where you work
│       ├── enums.py           # SectionID, SectionStatus, RouterDirective
│       ├── models.py          # XBuddyState, XBuddyData, output models
│       ├── graph/
│       │   ├── builder.py     # StateGraph wiring
│       │   └── routes.py      # Conditional edge functions
│       ├── nodes/
│       │   ├── initialize.py      # PR 1
│       │   ├── router.py          # PR 2
│       │   ├── generate_reply.py  # PR 3
│       │   ├── generate_decision.py # PR 3
│       │   ├── memory_updater.py  # PR 4
│       │   └── implementation.py  # PR 5
│       ├── sections/
│       │   ├── base_prompt.py # Shared rules + SectionTemplate class
│       │   ├── section_1/     # Your sections — rename these
│       │   ├── section_2/
│       │   ├── section_3/
│       │   ├── section_4/
│       │   └── section_5/
│       ├── prompts.py         # Section template mapping + navigation
│       └── tools.py           # get_context tool
├── core/                      # Settings, LLM factory, logging
├── memory/                    # Checkpointer backends (SQLite, Postgres)
├── integrations/supabase/     # Supabase client for persistence
├── schema/                    # Shared types
└── service/                   # FastAPI endpoints (stream, invoke, history)
```

## PR plan

| PR | Scope | Files |
|----|-------|-------|
| PR 1 | State schema + `initialize` node | `models.py`, `enums.py`, `nodes/initialize.py` |
| PR 2 | `router` + section loader | `nodes/router.py`, `prompts.py`, `tools.py`, `sections/*` |
| PR 3 | `generate_reply` + `generate_decision` | `nodes/generate_reply.py`, `nodes/generate_decision.py` |
| PR 4 | `memory_updater` + Supabase | `nodes/memory_updater.py`, Supabase integration |
| PR 5 | `implementation` node (final output) | `nodes/implementation.py` |
| PR 6 | FastAPI `/invoke` `/stream` `/history` | `service/service.py` — already working, customize |

Every PR must include a LangSmith trace URL and tradeoff reasoning.

## Reference materials
- [LangGraph cheatsheet](docs/langgraph-cheatsheet.md)
- [FounderBuddy reference](docs/founderbuddy-reference.md)
- [LangSmith setup](docs/langsmith-setup.md)

## Stack

| Layer | Technology |
|-------|-----------|
| Agent orchestration | LangGraph (StateGraph, conditional edges, loops) |
| LLM interface | LangChain |
| Observability | LangSmith (tracing, evals) |
| API | FastAPI (streaming SSE + sync endpoints) |
| Database | Supabase (agent state persistence) |
| Frontend | Next.js + React |
