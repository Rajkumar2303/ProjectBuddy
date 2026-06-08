"""Base classes and shared prompt rules for all sections.

Reference: https://github.com/Victoria824/FounderBuddy/blob/main/src/agents/founder_buddy/sections/base_prompt.py
"""

from typing import Any

from pydantic import BaseModel, Field

from ..enums import SectionID


class ValidationRule(BaseModel):
    """Validation rule for field input."""
    field_name: str
    rule_type: str  # "min_length", "max_length", "regex", "required", "choices"
    value: Any
    error_message: str


class SectionTemplate(BaseModel):
    """Template for an agent section."""
    section_id: SectionID
    name: str
    description: str
    system_prompt_template: str
    validation_rules: list[ValidationRule] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)
    next_section: SectionID | None = None


# TODO: Write your base rules. These are shared across ALL sections.
# See FounderBuddy's BASE_RULES for the pattern — it defines:
#   - Agent persona and communication style
#   - No-placeholder rule
#   - Section navigation rules
#   - Questioning approach (one question at a time)
BASE_RULES = """You are ProjectBuddy, an AI project planning assistant.

Your job is to guide users through a structured 5-section conversation to
produce a complete Project Blueprint document.

CORE RULES:
- Ask ONE question at a time — never dump a list of questions.
- Never use placeholder text like [TBD], [Not provided], or similar.
- Stay within the current section unless you explicitly decide to switch.
- When a section is complete, present a brief summary and ask the user if
  they are satisfied before advancing.
- If the user says something that contradicts an earlier statement, flag it
  ("You said X earlier, but now you're saying Y — can you clarify?").
- Do NOT generate code. This is a planning conversation, not a coding tool.
- Keep responses conversational and supportive, not mechanical.
"""

BASE_PROMPTS = {
    "base_rules": BASE_RULES,
}
