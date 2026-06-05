---
name: "Stage 1: Requirements"
about: Define your XBuddy agent's requirements
title: "My Project Buddy"
labels: stage-1
---

## Why this Buddy?

**Domain motivation:**
Project development is consistently unstructured and fragmented. Users start with an idea but lack clarity on requirements, system design, and execution planning. Existing tools (Notion templates, GitHub issue forms, static guides) are passive — they cannot react to incomplete, contradictory, or ambiguous input.

**Why this requires an AI agent, not a form:**

A static template cannot:
- Detect when an answer is too vague and ask a targeted follow-up
- Maintain dependency context across 5 interconnected planning stages
- Adapt the architecture discussion based on what was said in requirements
- Synthesize a coherent final artifact from multi-turn context

This agent is needed specifically because project planning requires:
1. **Iterative clarification** — vague inputs must be probed before advancing
2. **Dependency-aware sequencing** — requirements → architecture → tech stack → execution (order is non-negotiable)
3. **Structured decomposition** — complex systems must be broken into independently reviewable components
4. **Memory across turns** — decisions in Section 1 must constrain and inform choices in Section 4

**LLM-specific capabilities leveraged:**
- Structured output generation (enforced JSON schema for each section artifact)
- Tool use for validation (e.g., checking if proposed stack is consistent with stated constraints)
- Persistent context window for cross-section coherence checks

## Who is the user?

**Primary users:**
- Software engineering students (final year / graduate level) preparing capstone or thesis projects
- Early-career developers (0–3 years experience) building portfolio projects
- AI/ML engineers prototyping system-level applications who understand models but not full-stack architecture
- Startup founders validating technical feasibility before hiring a dev team

**Secondary users:**
- Hackathon participants who need a structured plan in < 24 hours
- Solo indie developers who have shipped code before but never formally planned a system

**Typical profile:**
- Age: 20–35
- Has a project idea but no structured system design experience
- Knows programming basics but struggles to translate ideas into architecture diagrams or requirement lists
- Has previously started projects that stalled due to unclear scope or poor planning
- Time-constrained — needs structured output fast, not a 3-hour consultation

**Core problem:** They can think in ideas but not in systems. They know *what* they want to build but not *how to decompose it* into buildable, testable components.

**What they are NOT:**
- Enterprise architects (too advanced)
- Non-technical founders (too early in the funnel)
- Users looking for boilerplate code generation (wrong tool)

## The 5 conversation sections

**Section 1: Project Idea & Goals**

Collects:
- Core idea (one-sentence description)
- Problem statement (what problem does this solve and for whom)
- Target users (specific personas, not "everyone")
- Expected outcome (what does success look like for the user)
- Hard constraints (time, budget, team size, regulatory, platform)

Why first:
Establishes the north star. Every downstream decision — architecture, stack, MVP scope — is only valid relative to a clearly bounded problem. Without this, Section 2 produces requirements for the wrong system.

Section transition trigger: Agent confirms problem statement, target user, and at least one hard constraint before advancing.

---

**Section 2: Requirements Gathering**

Collects:
- Functional requirements (what the system must do — verb-noun format: "User can log in via email")
- Non-functional requirements (performance, availability, security, scalability targets)
- User stories (as a `<user>`, I want to `<action>`, so that `<benefit>`)
- System inputs and outputs (what data enters and leaves the system)
- Out-of-scope items (explicit exclusions to prevent scope creep)

Why second:
Transforms abstract goals into verifiable system contracts. Architecture cannot be designed without knowing what behaviors must be supported.

Section transition trigger: At least 3 functional requirements listed, at least 1 NFR defined, and scope boundaries stated.

---

**Section 3: Architecture Design**

Collects:
- High-level system components (services, modules, layers)
- Data flow between components (what data moves where and when)
- Backend/frontend separation (or monolith justification)
- External integrations (APIs, third-party services, auth providers)
- AI/ML components if applicable (model type, inference location, data pipeline)
- Data storage strategy (what needs persistence, what is ephemeral)

Why third:
Architecture is the direct translation of requirements into structural decisions. It cannot precede requirements — doing so produces over-engineered or misaligned systems.

Section transition trigger: All major system components named, at least one data flow described, and storage strategy decided.

---

**Section 4: Technology Selection**

Collects:
- Language and framework choices (with brief justification per choice)
- Database selection (type + specific technology, justified against data model)
- Cloud/deployment preferences (managed vs self-hosted, region, provider)
- Tooling (CI/CD, monitoring, testing framework)
- Constraints (budget ceiling, team familiarity, open-source only, etc.)

Why fourth:
Tech stack must be a consequence of architecture, not a precondition. Choosing a stack before knowing the architecture leads to mismatched tools (e.g., picking a relational DB before knowing the data is graph-structured).

Section transition trigger: Every major architectural component has a corresponding technology choice with a stated reason.

---

**Section 5: Implementation Planning**

Collects:
- MVP definition (minimum feature set for first working version)
- Development phases (Phase 1 → 2 → 3 with specific deliverables per phase)
- Milestones and timeline (realistic estimates, not aspirational)
- Risks and mitigations (technical, team, external dependencies)
- Testing strategy (unit, integration, E2E — what gets tested at what stage)
- Definition of done for the overall project

Why last:
Only after full system definition — problem, requirements, architecture, and stack — can execution planning be grounded. Planning before this produces timelines that collapse on first contact with reality.

Section transition trigger: MVP scope defined, at least 2 development phases broken out with deliverables, and at least 2 risks identified with mitigations.

## Acceptance criteria

**Section 1 is complete when:**
- [ ] Problem statement answers: *what*, *who is affected*, and *why current solutions are insufficient*
- [ ] Target user is described with at least role + context (not just "developers")
- [ ] Project scope is bounded — at least one explicit out-of-scope item stated
- [ ] At least one hard constraint identified (time / budget / team / platform)
- [ ] Agent has confirmed understanding by paraphrasing the goal back to the user

**Section 2 is complete when:**
- [ ] Minimum 3 functional requirements listed in verb-noun format
- [ ] Minimum 1 non-functional requirement with a measurable target (e.g., "response time < 200ms")
- [ ] At least 2 user stories written in standard format
- [ ] System inputs and outputs explicitly enumerated
- [ ] At least 1 explicit out-of-scope item documented

**Section 3 is complete when:**
- [ ] All major system components named and their responsibility described
- [ ] At least one data flow path described end-to-end
- [ ] Frontend/backend separation decision made (or monolith justification given)
- [ ] Data storage strategy decided (what persists, what is ephemeral)
- [ ] AI/ML components identified if applicable, or explicitly marked as N/A

**Section 4 is complete when:**
- [ ] Every architectural component has a corresponding technology choice
- [ ] Each major choice has a one-line justification
- [ ] Database type and specific technology selected
- [ ] Deployment target decided (cloud provider, self-hosted, serverless, etc.)
- [ ] No choice contradicts a stated constraint from Sections 1–3

**Section 5 is complete when:**
- [ ] MVP is defined as a specific, minimal feature set (not "basic version")
- [ ] At least 2 development phases defined with concrete deliverables
- [ ] At least 2 risks identified with corresponding mitigations
- [ ] Testing strategy stated (what kind of tests, at what phase)
- [ ] Definition of done documented for the overall project
- [ ] Final blueprint is generated and downloadable as `PROJECT_SPEC.md`

## Key results — how will you know it's working?

**Primary success indicators:**
| Metric | Target |
| Section completion rate (all 5) | ≥ 70% of sessions that start Section 1 |
| Drop-off between S1 → S5 | < 30% |
| Average turns per section | 3–8 turns (< 3 = too shallow, > 8 = agent not guiding) |
| Final blueprint generation rate | ≥ 60% of completed sessions |
| User-reported clarity improvement | ≥ 4/5 on post-session prompt |

**Quality indicators:**
- Final blueprint LLM-evaluated score ≥ 7/10 on completeness rubric
- < 20% of generated blueprints require major rework (missing component, contradictory choices)
- Functional requirements in output use verb-noun format in ≥ 80% of cases (structural compliance)

**Failure signals to monitor:**
- Users repeating the same information across sections (agent not extracting correctly)
- Section 3 or 4 being completed in < 2 turns (agent not probing deeply enough)
- Blueprint output missing architecture or tech stack sections (generation failure)
- High abandonment specifically at Section 3 (likely: agent asking too abstractly about architecture)

## What does the final output look like?

The final output is a **Project Blueprint** — a structured Markdown document generated at the end of a completed 5-section conversation. It is designed to be directly handed to a developer (or used as a GitHub repo README / project spec) without further editing.

**Blueprint structure:**

1. **Executive Summary** — 3–5 sentence overview of the project, problem, and solution approach
2. **Problem Statement** — Clearly scoped problem with affected users and gap analysis
3. **User Personas** — 1–2 personas derived from Section 1 answers
4. **Functional Requirements** — Numbered list in verb-noun format
5. **Non-Functional Requirements** — With measurable targets where applicable
6. **System Architecture** — Textual component breakdown + data flow description
7. **Technology Stack** — Table of component → technology → justification
8. **Database Design Overview** — Schema sketch or entity list with relationships
9. **API Design Overview** — Key endpoints or inter-service contracts
10. **AI/ML Components** — Model choices, data pipeline, inference strategy (or marked N/A)
11. **Implementation Roadmap** — Phased plan with deliverables per phase
12. **Milestone Plan** — Timeline with named milestones
13. **Risk Assessment** — Risk × likelihood × mitigation table
14. **Testing Strategy** — Test types mapped to development phases
15. **Deployment Strategy** — Target environment, CI/CD approach
16. **Future Enhancements** — Post-MVP backlog items

**Output format:** Rendered Markdown, downloadable as `.md`, suitable for direct commit into a GitHub repository as `PROJECT_SPEC.md`.

**Output quality standard:** A reviewer unfamiliar with the original conversation should be able to understand the full system and begin implementation without asking clarifying questions.

---

## Agent Behavioral Constraints (Guardrails)

The agent **must**:
- Always complete sections in order (1 → 2 → 3 → 4 → 5) — no jumping ahead
- Paraphrase and confirm understanding before advancing to the next section
- Ask at most 2–3 questions per turn (not a 10-item questionnaire dump)
- Explicitly tell the user when a section is complete and what section comes next
- Flag contradictions between sections (e.g., "You said no backend in S1 but proposed a REST API in S3")

The agent **must not**:
- Generate code at any point — this is a planning tool, not a code generator
- Accept vague answers like "it depends" or "maybe later" without probing
- Skip the acceptance criteria checklist for any section, even if the user asks to rush
- Propose a tech stack before Section 3 architecture is complete
- Produce a final blueprint if any section is incomplete

