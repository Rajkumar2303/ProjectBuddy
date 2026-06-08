"""Pydantic models for your XBuddy Agent.

Study FounderBuddy's models.py to understand how these work:
https://github.com/Victoria824/FounderBuddy/blob/main/src/agents/founder_buddy/models.py
"""

import uuid
from typing import Any

from langchain_core.messages import BaseMessage
from langgraph.graph import MessagesState
from pydantic import BaseModel, Field, field_validator

from .enums import RouterDirective, SectionID, SectionStatus
from .sections.base_prompt import SectionTemplate, ValidationRule


class SectionContent(BaseModel):
    """Content for an agent section."""
    content: dict[str, Any]  # Rich text content (Tiptap JSON format)
    plain_text: str | None = None  # Plain text version for LLM processing


class SectionState(BaseModel):
    """State of a single section."""
    section_id: SectionID
    content: SectionContent | None = None
    satisfaction_status: str | None = None  # satisfied, needs_improvement, or None
    status: SectionStatus = SectionStatus.PENDING


class ContextPacket(BaseModel):
    """Context packet loaded by the router for the current section."""
    section_id: SectionID
    status: SectionStatus
    system_prompt: str
    draft: SectionContent | None = None
    validation_rules: dict[str, Any] | None = None


class ProjectBuddyData(BaseModel):
    """Structured project data extracted from the user across all 5 sections.

    Fields are populated incrementally by memory_updater after each section
    completes. initialize_node starts with an empty instance; the final
    implementation_node reads all fields to synthesise the Project Blueprint.
    """

    # ── Section 1: Project Idea & Goals ────────────────────────────────────
    one_line_idea: str | None = None
    problem_statement: str | None = None          # what + who + why existing solutions fail
    target_users: list[str] = Field(default_factory=list)
    success_outcome: str | None = None
    hard_constraints: list[str] = Field(default_factory=list)  # time, budget, team, platform

    # ── Section 2: Requirements ─────────────────────────────────────────────
    functional_requirements: list[str] = Field(default_factory=list)   # verb-noun format
    non_functional_requirements: list[str] = Field(default_factory=list)  # measurable targets
    user_stories: list[str] = Field(default_factory=list)    # "As a X, I want Y, so that Z"
    system_inputs: list[str] = Field(default_factory=list)
    system_outputs: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)

    # ── Section 3: Architecture ─────────────────────────────────────────────
    system_components: list[str] = Field(default_factory=list)
    data_flows: list[str] = Field(default_factory=list)
    architecture_style: str | None = None          # e.g. "frontend/backend split", "monolith"
    external_integrations: list[str] = Field(default_factory=list)
    ai_ml_components: list[str] = Field(default_factory=list)  # or ["N/A"]
    storage_strategy: str | None = None

    # ── Section 4: Technology Selection ────────────────────────────────────
    language_frameworks: dict[str, str] = Field(default_factory=dict)  # component → choice
    database_choice: str | None = None
    deployment_target: str | None = None
    tooling: dict[str, str] = Field(default_factory=dict)    # ci_cd, monitoring, testing

    # ── Section 5: Implementation Planning ─────────────────────────────────
    mvp_features: list[str] = Field(default_factory=list)
    development_phases: list[dict[str, Any]] = Field(default_factory=list)  # [{phase, deliverables}]
    risks: list[dict[str, Any]] = Field(default_factory=list)               # [{risk, likelihood, mitigation}]
    testing_strategy: str | None = None
    definition_of_done: str | None = None


class ChatAgentDecision(BaseModel):
    """Structured decision from the generate_decision node."""
    router_directive: str = Field(
        ...,
        description="Navigation control: 'stay', 'next', or 'modify:<section_id>'",
    )
    user_satisfaction_feedback: str | None = Field(
        None, description="User's feedback about satisfaction with the section."
    )
    is_satisfied: bool | None = Field(
        None, description="Whether the user is satisfied with the current section."
    )
    should_save_content: bool = Field(
        False,
        description="Whether to save the current section content.",
    )

    @field_validator("router_directive")
    def validate_router_directive(cls, v):
        if v not in ["stay", "next"] and not v.startswith("modify:"):
            raise ValueError("router_directive must be 'stay', 'next', or 'modify:<section_id>'")
        return v


class ChatAgentOutput(BaseModel):
    """Complete output from the generate_reply + generate_decision nodes."""
    reply: str = Field(..., description="Conversational response to the user.")
    router_directive: str = Field(
        ...,
        description="Navigation control: 'stay', 'next', or 'modify:<section_id>'",
    )
    user_satisfaction_feedback: str | None = None
    is_satisfied: bool | None = None
    should_save_content: bool = False

    @field_validator("router_directive")
    def validate_router_directive(cls, v):
        if v not in ["stay", "next"] and not v.startswith("modify:"):
            raise ValueError("router_directive must be 'stay', 'next', or 'modify:<section_id>'")
        return v


class XBuddyState(MessagesState):
    """State for your XBuddy agent.

    Extends MessagesState (which provides `messages: list[BaseMessage]`).
    Study FounderBuddyState to understand each field's role in the graph.
    """
    # User and conversation identification
    user_id: int = 1
    thread_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # Navigation and progress
    current_section: SectionID = SectionID.PROJECT_IDEA
    context_packet: ContextPacket | None = None
    section_states: dict[str, SectionState] = Field(default_factory=dict)
    router_directive: str = RouterDirective.NEXT
    finished: bool = False

    # Structured project data — populated incrementally by memory_updater
    user_data: ProjectBuddyData = Field(default_factory=ProjectBuddyData)

    # Memory management
    short_memory: list[BaseMessage] = Field(default_factory=list)

    # Agent output
    agent_output: ChatAgentOutput | None = None
    awaiting_user_input: bool = False
    awaiting_satisfaction_feedback: bool = False

    # Error tracking
    error_count: int = 0
    last_error: str | None = None

    # Final output — Project Blueprint Markdown (generated by implementation_node)
    final_output: str | None = None
    should_generate_final_output: bool = False
