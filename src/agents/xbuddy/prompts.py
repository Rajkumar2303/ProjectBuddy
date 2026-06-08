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
    return SectionTemplate(
        section_id=section_id,
        name=section_id.value.replace("_", " ").title(),
        description=_SECTION_PROMPTS[section_id].strip().split("\n")[0].strip('"').lstrip(": "),
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

