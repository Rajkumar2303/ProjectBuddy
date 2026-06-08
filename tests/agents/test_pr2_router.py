"""Tests for PR2: router_node + section templates.

Covers:
- STAY directive keeps current section
- NEXT directive advances to next section in order
- NEXT at last section stays (no advance)
- MODIFY jumps to a valid section
- MODIFY with invalid section_id stays on current section
- finished=True returns context packet without changing section
- ContextPacket is populated with correct section's system prompt
- Draft is loaded from section_states when content exists
- No draft when section_states has no content
- router_directive is reset to STAY after processing
"""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from agents.xbuddy.enums import RouterDirective, SectionID, SectionStatus
from agents.xbuddy.models import (
    ContextPacket,
    ProjectBuddyData,
    SectionContent,
    SectionState,
    XBuddyState,
)
from agents.xbuddy.nodes.router import _advance_section, _parse_modify_directive, router_node


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_state(
    current_section: SectionID = SectionID.PROJECT_IDEA,
    directive: str = RouterDirective.STAY,
    finished: bool = False,
    section_states: dict[str, SectionState] | None = None,
) -> XBuddyState:
    return {
        "messages": [],
        "user_id": 1,
        "thread_id": "test-thread",
        "current_section": current_section,
        "context_packet": None,
        "section_states": section_states or {},
        "router_directive": directive,
        "finished": finished,
        "user_data": ProjectBuddyData(),
        "short_memory": [],
        "agent_output": None,
        "awaiting_user_input": False,
        "awaiting_satisfaction_feedback": False,
        "error_count": 0,
        "last_error": None,
        "final_output": None,
        "should_generate_final_output": False,
    }


def _pending_section(section_id: SectionID) -> SectionState:
    return SectionState(section_id=section_id, status=SectionStatus.PENDING)


def _done_section(section_id: SectionID) -> SectionState:
    return SectionState(section_id=section_id, status=SectionStatus.DONE)


def _section_with_draft(section_id: SectionID, text: str = "existing draft") -> SectionState:
    return SectionState(
        section_id=section_id,
        status=SectionStatus.IN_PROGRESS,
        content=SectionContent(content={"type": "doc"}, plain_text=text),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helper tests
# ─────────────────────────────────────────────────────────────────────────────

class TestHelpers:
    def test_advance_section_first_to_second(self):
        assert _advance_section(SectionID.PROJECT_IDEA) == SectionID.REQUIREMENTS

    def test_advance_section_middle(self):
        assert _advance_section(SectionID.ARCHITECTURE) == SectionID.TECH_STACK

    def test_advance_section_last_returns_none(self):
        assert _advance_section(SectionID.IMPLEMENTATION) is None

    def test_parse_modify_valid(self):
        assert _parse_modify_directive("modify:project_idea") == SectionID.PROJECT_IDEA
        assert _parse_modify_directive("modify:architecture") == SectionID.ARCHITECTURE

    def test_parse_modify_invalid_section(self):
        assert _parse_modify_directive("modify:nonexistent") is None

    def test_parse_modify_malformed(self):
        assert _parse_modify_directive("modify") is None
        assert _parse_modify_directive("bad_format") is None


# ─────────────────────────────────────────────────────────────────────────────
# router_node — STAY
# ─────────────────────────────────────────────────────────────────────────────

class TestRouterStay:
    async def test_stay_keeps_current_section(self):
        state = _make_state(current_section=SectionID.REQUIREMENTS, directive=RouterDirective.STAY)
        result = await router_node(state, None)

        assert result["current_section"] == SectionID.REQUIREMENTS

    async def test_stay_resets_directive(self):
        state = _make_state(directive=RouterDirective.STAY)
        result = await router_node(state, None)

        assert result["router_directive"] == RouterDirective.STAY

    async def test_stay_builds_context_packet(self):
        state = _make_state(current_section=SectionID.ARCHITECTURE)
        result = await router_node(state, None)

        cp: ContextPacket = result["context_packet"]
        assert cp.section_id == SectionID.ARCHITECTURE
        assert cp.status == SectionStatus.PENDING
        assert "architecture" in cp.system_prompt.lower()


# ─────────────────────────────────────────────────────────────────────────────
# router_node — NEXT
# ─────────────────────────────────────────────────────────────────────────────

class TestRouterNext:
    async def test_next_advances_to_next_section(self):
        state = _make_state(current_section=SectionID.PROJECT_IDEA, directive=RouterDirective.NEXT)
        result = await router_node(state, None)

        assert result["current_section"] == SectionID.REQUIREMENTS

    async def test_next_from_middle(self):
        state = _make_state(current_section=SectionID.ARCHITECTURE, directive=RouterDirective.NEXT)
        result = await router_node(state, None)

        assert result["current_section"] == SectionID.TECH_STACK

    async def test_next_at_last_section_stays(self):
        state = _make_state(current_section=SectionID.IMPLEMENTATION, directive=RouterDirective.NEXT)
        result = await router_node(state, None)

        assert result["current_section"] == SectionID.IMPLEMENTATION

    async def test_next_resets_directive(self):
        state = _make_state(directive=RouterDirective.NEXT)
        result = await router_node(state, None)

        assert result["router_directive"] == RouterDirective.STAY


# ─────────────────────────────────────────────────────────────────────────────
# router_node — MODIFY
# ─────────────────────────────────────────────────────────────────────────────

class TestRouterModify:
    async def test_modify_jumps_to_valid_section(self):
        state = _make_state(
            current_section=SectionID.IMPLEMENTATION,
            directive="modify:requirements",
        )
        result = await router_node(state, None)

        assert result["current_section"] == SectionID.REQUIREMENTS

    async def test_modify_jumps_backward(self):
        state = _make_state(
            current_section=SectionID.TECH_STACK,
            directive="modify:project_idea",
        )
        result = await router_node(state, None)

        assert result["current_section"] == SectionID.PROJECT_IDEA

    async def test_modify_invalid_section_id_stays(self):
        state = _make_state(
            current_section=SectionID.ARCHITECTURE,
            directive="modify:nonexistent",
        )
        result = await router_node(state, None)

        assert result["current_section"] == SectionID.ARCHITECTURE

    async def test_modify_malformed_string_stays(self):
        state = _make_state(current_section=SectionID.REQUIREMENTS, directive="modify")
        result = await router_node(state, None)

        assert result["current_section"] == SectionID.REQUIREMENTS


# ─────────────────────────────────────────────────────────────────────────────
# router_node — FINISHED
# ─────────────────────────────────────────────────────────────────────────────

class TestRouterFinished:
    async def test_finished_keeps_section(self):
        state = _make_state(
            current_section=SectionID.IMPLEMENTATION,
            directive=RouterDirective.NEXT,
            finished=True,
        )
        result = await router_node(state, None)

        # Should NOT advance because finished=True takes priority
        assert result["current_section"] == SectionID.IMPLEMENTATION

    async def test_finished_still_builds_context_packet(self):
        state = _make_state(finished=True)
        result = await router_node(state, None)

        assert result["context_packet"] is not None
        assert result["context_packet"].section_id == SectionID.PROJECT_IDEA


# ─────────────────────────────────────────────────────────────────────────────
# router_node — ContextPacket content
# ─────────────────────────────────────────────────────────────────────────────

class TestContextPacketContent:
    async def test_system_prompt_matches_section(self):
        state = _make_state(current_section=SectionID.PROJECT_IDEA)
        result = await router_node(state, None)

        prompt = result["context_packet"].system_prompt
        assert "Project Idea" in prompt or "project idea" in prompt.lower()

    async def test_system_prompt_for_requirements(self):
        state = _make_state(current_section=SectionID.REQUIREMENTS)
        result = await router_node(state, None)

        prompt = result["context_packet"].system_prompt
        assert "Section 2" in prompt or "Requirements" in prompt

    async def test_draft_loaded_when_exists(self):
        states = {"project_idea": _section_with_draft(SectionID.PROJECT_IDEA, "My awesome idea")}
        state = _make_state(
            current_section=SectionID.PROJECT_IDEA,
            section_states=states,
        )
        result = await router_node(state, None)

        assert result["context_packet"].draft is not None
        assert result["context_packet"].draft.plain_text == "My awesome idea"

    async def test_draft_none_when_no_content(self):
        states = {"project_idea": _pending_section(SectionID.PROJECT_IDEA)}
        state = _make_state(
            current_section=SectionID.PROJECT_IDEA,
            section_states=states,
        )
        result = await router_node(state, None)

        assert result["context_packet"].draft is None

    async def test_draft_none_when_section_missing(self):
        state = _make_state(current_section=SectionID.PROJECT_IDEA)
        result = await router_node(state, None)

        assert result["context_packet"].draft is None

    async def test_context_packet_status_matches_section_state(self):
        states = {"requirements": _done_section(SectionID.REQUIREMENTS)}
        state = _make_state(
            current_section=SectionID.REQUIREMENTS,
            section_states=states,
        )
        result = await router_node(state, None)

        assert result["context_packet"].status == SectionStatus.DONE
