"""Section definitions for ProjectBuddy — one prompt per conversation section."""

from .project_idea import SECTION_1_SYSTEM_PROMPT
from .requirements import SECTION_2_SYSTEM_PROMPT
from .architecture import SECTION_3_SYSTEM_PROMPT
from .tech_stack import SECTION_4_SYSTEM_PROMPT
from .implementation import SECTION_5_SYSTEM_PROMPT

from .base_prompt import BASE_RULES, BASE_PROMPTS, SectionTemplate, ValidationRule

__all__ = [
    "SECTION_1_SYSTEM_PROMPT",
    "SECTION_2_SYSTEM_PROMPT",
    "SECTION_3_SYSTEM_PROMPT",
    "SECTION_4_SYSTEM_PROMPT",
    "SECTION_5_SYSTEM_PROMPT",
    "BASE_RULES",
    "BASE_PROMPTS",
    "SectionTemplate",
    "ValidationRule",
]
