"""Tests for PR1: XBuddyState schema + initialize_node.

Covers:
- SectionID enum values and ordering
- ProjectBuddyData, SectionState, ContextPacket, ChatAgentOutput model construction
- initialize_node cold-start path
- initialize_node resume path (mocked Supabase rows)
- initialize_node Supabase-unavailable fallback
- initialize_node corrupted row handling
- initialize_node missing thread_id fallback
"""

import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from agents.xbuddy.enums import RouterDirective, SectionID, SectionStatus
from agents.xbuddy.models import (
    ChatAgentDecision,
    ChatAgentOutput,
    ContextPacket,
    ProjectBuddyData,
    SectionContent,
    SectionState,
    XBuddyState,
)
from agents.xbuddy.nodes.initialize import (
    SECTION_ORDER,
    _all_sections_done,
    _build_section_state,
    _first_incomplete_section,
    initialize_node,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

THREAD_ID = "test-thread-" + str(uuid.uuid4())
USER_ID = 42


def _make_config(thread_id: str = THREAD_ID, user_id: int = USER_ID) -> dict:
    return {"configurable": {"thread_id": thread_id, "user_id": user_id}}


def _supabase_row(section_id: str, status: str = "pending") -> dict[str, Any]:
    return {
        "section_id": section_id,
        "status": status,
        "content": {"type": "doc", "content": []},
        "plain_text": "some text",
        "satisfaction_status": None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# enums.py
# ─────────────────────────────────────────────────────────────────────────────

class TestSectionID:
    def test_all_five_values_present(self):
        values = {s.value for s in SectionID}
        assert values == {
            "project_idea",
            "requirements",
            "architecture",
            "tech_stack",
            "implementation",
        }

    def test_section_order_matches_dependency_chain(self):
        assert SECTION_ORDER == [
            SectionID.PROJECT_IDEA,
            SectionID.REQUIREMENTS,
            SectionID.ARCHITECTURE,
            SectionID.TECH_STACK,
            SectionID.IMPLEMENTATION,
        ]

    def test_section_id_is_str_serialisable(self):
        # str,Enum members compare equal to their value string directly
        assert SectionID.PROJECT_IDEA == "project_idea"
        assert SectionID.PROJECT_IDEA.value == "project_idea"

    def test_router_directive_values(self):
        assert RouterDirective.STAY == "stay"
        assert RouterDirective.NEXT == "next"
        assert RouterDirective.MODIFY == "modify"

    def test_section_status_values(self):
        assert SectionStatus.PENDING == "pending"
        assert SectionStatus.IN_PROGRESS == "in_progress"
        assert SectionStatus.DONE == "done"


# ─────────────────────────────────────────────────────────────────────────────
# models.py
# ─────────────────────────────────────────────────────────────────────────────

class TestProjectBuddyData:
    def test_empty_construction(self):
        data = ProjectBuddyData()
        assert data.one_line_idea is None
        assert data.functional_requirements == []
        assert data.risks == []

    def test_partial_population(self):
        data = ProjectBuddyData(
            one_line_idea="A planning agent",
            target_users=["developers", "students"],
            functional_requirements=["User can start a session"],
        )
        assert data.one_line_idea == "A planning agent"
        assert len(data.target_users) == 2
        assert len(data.functional_requirements) == 1

    def test_json_serialisable(self):
        data = ProjectBuddyData(mvp_features=["Feature A"])
        dumped = data.model_dump()
        assert isinstance(dumped, dict)
        assert dumped["mvp_features"] == ["Feature A"]


class TestSectionState:
    def test_default_status_is_pending(self):
        s = SectionState(section_id=SectionID.PROJECT_IDEA)
        assert s.status == SectionStatus.PENDING
        assert s.content is None

    def test_with_content(self):
        content = SectionContent(content={"type": "doc"}, plain_text="hello")
        s = SectionState(
            section_id=SectionID.REQUIREMENTS,
            content=content,
            status=SectionStatus.DONE,
            satisfaction_status="satisfied",
        )
        assert s.status == SectionStatus.DONE
        assert s.content.plain_text == "hello"


class TestContextPacket:
    def test_construction(self):
        cp = ContextPacket(
            section_id=SectionID.ARCHITECTURE,
            status=SectionStatus.IN_PROGRESS,
            system_prompt="You are a helpful agent.",
        )
        assert cp.section_id == SectionID.ARCHITECTURE
        assert cp.draft is None
        assert cp.validation_rules is None


class TestChatAgentOutput:
    def test_valid_stay_directive(self):
        out = ChatAgentOutput(reply="Tell me more.", router_directive="stay")
        assert out.router_directive == "stay"

    def test_valid_next_directive(self):
        out = ChatAgentOutput(reply="Great!", router_directive="next")
        assert out.router_directive == "next"

    def test_valid_modify_directive(self):
        out = ChatAgentOutput(reply="Let me revisit.", router_directive="modify:project_idea")
        assert out.router_directive == "modify:project_idea"

    def test_invalid_directive_raises(self):
        with pytest.raises(Exception):
            ChatAgentOutput(reply="Bad", router_directive="jump")


class TestXBuddyState:
    def test_default_current_section_is_project_idea(self):
        # XBuddyState is a TypedDict-style MessagesState — instantiate as dict
        state: XBuddyState = {
            "messages": [],
            "user_id": 1,
            "thread_id": str(uuid.uuid4()),
            "current_section": SectionID.PROJECT_IDEA,
            "context_packet": None,
            "section_states": {},
            "router_directive": RouterDirective.NEXT,
            "finished": False,
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
        assert state["current_section"] == SectionID.PROJECT_IDEA


# ─────────────────────────────────────────────────────────────────────────────
# initialize_node helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestHelpers:
    def test_first_incomplete_all_pending(self):
        section_states = {
            sid.value: SectionState(section_id=sid, status=SectionStatus.PENDING)
            for sid in SECTION_ORDER
        }
        assert _first_incomplete_section(section_states) == SectionID.PROJECT_IDEA

    def test_first_incomplete_first_two_done(self):
        section_states = {
            SectionID.PROJECT_IDEA.value: SectionState(
                section_id=SectionID.PROJECT_IDEA, status=SectionStatus.DONE
            ),
            SectionID.REQUIREMENTS.value: SectionState(
                section_id=SectionID.REQUIREMENTS, status=SectionStatus.DONE
            ),
        }
        assert _first_incomplete_section(section_states) == SectionID.ARCHITECTURE

    def test_first_incomplete_all_done_returns_last(self):
        section_states = {
            sid.value: SectionState(section_id=sid, status=SectionStatus.DONE)
            for sid in SECTION_ORDER
        }
        assert _first_incomplete_section(section_states) == SECTION_ORDER[-1]

    def test_all_sections_done_false_when_pending(self):
        section_states = {
            sid.value: SectionState(section_id=sid, status=SectionStatus.PENDING)
            for sid in SECTION_ORDER
        }
        assert _all_sections_done(section_states) is False

    def test_all_sections_done_true(self):
        section_states = {
            sid.value: SectionState(section_id=sid, status=SectionStatus.DONE)
            for sid in SECTION_ORDER
        }
        assert _all_sections_done(section_states) is True

    def test_build_section_state_valid_row(self):
        row = _supabase_row("project_idea", "in_progress")
        s = _build_section_state(row)
        assert s.section_id == SectionID.PROJECT_IDEA
        assert s.status == SectionStatus.IN_PROGRESS
        assert s.content is not None

    def test_build_section_state_unknown_section_id_raises(self):
        row = _supabase_row("nonexistent_section", "pending")
        with pytest.raises(ValueError):
            _build_section_state(row)

    def test_build_section_state_null_content(self):
        row = {"section_id": "requirements", "status": "pending", "content": None}
        s = _build_section_state(row)
        assert s.content is None


# ─────────────────────────────────────────────────────────────────────────────
# initialize_node — cold start
# ─────────────────────────────────────────────────────────────────────────────

class TestInitializeNodeColdStart:
    @pytest.mark.asyncio
    async def test_cold_start_sets_project_idea(self):
        state: dict = {}
        with patch(
            "agents.xbuddy.nodes.initialize.asyncio.to_thread",
            new=AsyncMock(return_value=[]),  # no rows → cold start
        ):
            result = await initialize_node(state, _make_config())

        assert result["current_section"] == SectionID.PROJECT_IDEA
        assert result["finished"] is False
        assert isinstance(result["user_data"], ProjectBuddyData)

    @pytest.mark.asyncio
    async def test_cold_start_initialises_all_sections_as_pending(self):
        state: dict = {}
        with patch(
            "agents.xbuddy.nodes.initialize.asyncio.to_thread",
            new=AsyncMock(return_value=[]),
        ):
            result = await initialize_node(state, _make_config())

        section_states = result["section_states"]
        assert set(section_states.keys()) == {sid.value for sid in SECTION_ORDER}
        for s in section_states.values():
            assert s.status == SectionStatus.PENDING

    @pytest.mark.asyncio
    async def test_cold_start_uses_config_thread_id(self):
        state: dict = {}
        with patch(
            "agents.xbuddy.nodes.initialize.asyncio.to_thread",
            new=AsyncMock(return_value=[]),
        ):
            result = await initialize_node(state, _make_config(thread_id="explicit-tid"))

        assert result["thread_id"] == "explicit-tid"

    @pytest.mark.asyncio
    async def test_cold_start_generates_thread_id_when_missing(self):
        state: dict = {}
        config: dict = {"configurable": {}}  # no thread_id
        with patch(
            "agents.xbuddy.nodes.initialize.asyncio.to_thread",
            new=AsyncMock(return_value=[]),
        ):
            result = await initialize_node(state, config)

        assert result["thread_id"]  # must not be empty
        # Should be a valid UUID
        uuid.UUID(result["thread_id"])

    @pytest.mark.asyncio
    async def test_cold_start_error_count_reset(self):
        state: dict = {"error_count": 5}
        with patch(
            "agents.xbuddy.nodes.initialize.asyncio.to_thread",
            new=AsyncMock(return_value=[]),
        ):
            result = await initialize_node(state, _make_config())

        assert result["error_count"] == 0
        assert result["last_error"] is None


# ─────────────────────────────────────────────────────────────────────────────
# initialize_node — resume
# ─────────────────────────────────────────────────────────────────────────────

class TestInitializeNodeResume:
    @pytest.mark.asyncio
    async def test_resume_restores_section_states(self):
        rows = [
            _supabase_row("project_idea", "done"),
            _supabase_row("requirements", "in_progress"),
        ]
        state: dict = {}
        with patch(
            "agents.xbuddy.nodes.initialize.asyncio.to_thread",
            new=AsyncMock(return_value=rows),
        ):
            result = await initialize_node(state, _make_config())

        assert "project_idea" in result["section_states"]
        assert result["section_states"]["project_idea"].status == SectionStatus.DONE

    @pytest.mark.asyncio
    async def test_resume_sets_current_section_to_first_incomplete(self):
        rows = [
            _supabase_row("project_idea", "done"),
            _supabase_row("requirements", "done"),
            _supabase_row("architecture", "in_progress"),
        ]
        state: dict = {}
        with patch(
            "agents.xbuddy.nodes.initialize.asyncio.to_thread",
            new=AsyncMock(return_value=rows),
        ):
            result = await initialize_node(state, _make_config())

        assert result["current_section"] == SectionID.ARCHITECTURE

    @pytest.mark.asyncio
    async def test_resume_finished_true_when_all_done(self):
        rows = [_supabase_row(sid.value, "done") for sid in SECTION_ORDER]
        state: dict = {}
        with patch(
            "agents.xbuddy.nodes.initialize.asyncio.to_thread",
            new=AsyncMock(return_value=rows),
        ):
            result = await initialize_node(state, _make_config())

        assert result["finished"] is True


# ─────────────────────────────────────────────────────────────────────────────
# initialize_node — edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestInitializeNodeEdgeCases:
    @pytest.mark.asyncio
    async def test_supabase_unavailable_falls_back_to_cold_start(self):
        state: dict = {}
        with patch(
            "agents.xbuddy.nodes.initialize.asyncio.to_thread",
            side_effect=Exception("connection refused"),
        ):
            result = await initialize_node(state, _make_config())

        assert result["current_section"] == SectionID.PROJECT_IDEA
        assert result["finished"] is False

    @pytest.mark.asyncio
    async def test_all_corrupted_rows_falls_back_to_cold_start(self):
        rows = [{"section_id": "unknown_garbage", "status": "pending", "content": None}]
        state: dict = {}
        with patch(
            "agents.xbuddy.nodes.initialize.asyncio.to_thread",
            new=AsyncMock(return_value=rows),
        ):
            result = await initialize_node(state, _make_config())

        # All corrupted → cold start
        assert result["current_section"] == SectionID.PROJECT_IDEA
        all_pending = all(
            s.status == SectionStatus.PENDING
            for s in result["section_states"].values()
        )
        assert all_pending

    @pytest.mark.asyncio
    async def test_partial_corruption_skips_bad_rows(self):
        rows = [
            _supabase_row("project_idea", "done"),
            {"section_id": "bad_id", "status": "pending", "content": None},  # corrupted
            _supabase_row("requirements", "in_progress"),
        ]
        state: dict = {}
        with patch(
            "agents.xbuddy.nodes.initialize.asyncio.to_thread",
            new=AsyncMock(return_value=rows),
        ):
            result = await initialize_node(state, _make_config())

        assert "project_idea" in result["section_states"]
        assert "requirements" in result["section_states"]
        assert "bad_id" not in result["section_states"]

    @pytest.mark.asyncio
    async def test_none_config_handled(self):
        state: dict = {"thread_id": THREAD_ID, "user_id": USER_ID}
        with patch(
            "agents.xbuddy.nodes.initialize.asyncio.to_thread",
            new=AsyncMock(return_value=[]),
        ):
            result = await initialize_node(state, None)  # type: ignore

        assert result["thread_id"] == THREAD_ID
