"""Section prompts and navigation helpers.

Maps each SectionID to its SectionTemplate, including the system prompt,
validation rules, and navigation order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .enums import SectionID
from .sections import (
    BASE_RULES,
    SECTION_1_SYSTEM_PROMPT,
    SECTION_2_SYSTEM_PROMPT,
    SECTION_3_SYSTEM_PROMPT,
    SECTION_4_SYSTEM_PROMPT,
    SECTION_5_SYSTEM_PROMPT,
)
from .sections.base_prompt import SectionTemplate

if TYPE_CHECKING:
    from .models import SectionState


# ── Section ordering (dependency chain) ──────────────────────────────────
SECTION_ORDER: list[SectionID] = [
    SectionID.PROJECT_IDEA,
    SectionID.REQUIREMENTS,
    SectionID.ARCHITECTURE,
    SectionID.TECH_STACK,
    SectionID.IMPLEMENTATION,
]

# ── System prompt lookup ─────────────────────────────────────────────────
_SECTION_PROMPTS: dict[SectionID, str] = {
    SectionID.PROJECT_IDEA: SECTION_1_SYSTEM_PROMPT,
    SectionID.REQUIREMENTS: SECTION_2_SYSTEM_PROMPT,
    SectionID.ARCHITECTURE: SECTION_3_SYSTEM_PROMPT,
    SectionID.TECH_STACK: SECTION_4_SYSTEM_PROMPT,
    SectionID.IMPLEMENTATION: SECTION_5_SYSTEM_PROMPT,
}


def build_system_prompt(section_id: SectionID) -> str:
    """Build the full system prompt for a section = base rules + section prompt."""
    section_prompt = _SECTION_PROMPTS[section_id]
    return f"{BASE_RULES}\n\n---\n\n{section_prompt}"


def get_section_template(section_id: SectionID) -> SectionTemplate:
    """Return the template for a given section."""
    system_prompt = build_system_prompt(section_id)
    # NOTE: description is derived by taking the first line of the section
    # prompt and stripping docstring markers. This works while prompts
    # follow the convention of a short goal line on line 1. If a prompt's
    # first line format changes, the description may become garbled.
    first_line = _SECTION_PROMPTS[section_id].strip().split("\n")[0].strip('"').lstrip(": ")
    return SectionTemplate(
        section_id=section_id,
        name=section_id.value.replace("_", " ").title(),
        description=first_line,
        system_prompt_template=system_prompt,
        next_section=get_next_section(section_id),
    )


def get_next_section(current: SectionID) -> SectionID | None:
    """Return the next section in sequence, or None if current is the last."""
    idx = SECTION_ORDER.index(current)
    if idx + 1 < len(SECTION_ORDER):
        return SECTION_ORDER[idx + 1]
    return None


def get_next_unfinished_section(section_states: dict[str, SectionState]) -> SectionID | None:
    """Find the first section that is not DONE."""
    for section_id in SECTION_ORDER:
        state = section_states.get(section_id.value)
        if not state or state.status != "done":
            return section_id
    return None


BLUEPRINT_SYNTHESIS_PROMPT = """You are synthesising a Project Blueprint from a structured planning conversation.

You will receive the collected content from all 5 sections of a project planning
session. Your job is to produce a polished, complete Markdown document that can
be handed directly to a developer or used as a project specification.

Structure the output as follows:

# Project Blueprint: <Project Title>

## 1. Executive Summary
3-5 sentence overview of the project, problem, and solution approach.

## 2. Problem Statement
Clearly scoped problem with affected users and gap analysis.

## 3. User Personas
1-2 personas derived from the target users.

## 4. Functional Requirements
Numbered list in verb-noun format.

## 5. Non-Functional Requirements
With measurable targets where applicable.

## 6. System Architecture
Component breakdown + data flow description.

## 7. Technology Stack
Table of component | technology | justification.

## 8. Database Design Overview
Schema sketch or entity list with relationships.

## 9. API Design Overview
Key endpoints or inter-service contracts (if applicable).

## 10. AI/ML Components
Model choices, data pipeline, inference strategy (or N/A).

## 11. Implementation Roadmap
Phased plan with deliverables per phase.

## 12. Milestone Plan
Timeline with named milestones.

## 13. Risk Assessment
Risk × likelihood × mitigation table.

## 14. Testing Strategy
Test types mapped to development phases.

## 15. Deployment Strategy
Target environment, CI/CD approach.

## 16. Future Enhancements
Post-MVP backlog items.

RULES:
- Use the actual content provided — do NOT invent details or use placeholders
- If a section has no content, write "Not specified" rather than leaving it blank
- Keep the language professional and actionable
- The document must be self-contained — a reader unfamiliar with the conversation
  should understand the full system and begin implementation
"""

