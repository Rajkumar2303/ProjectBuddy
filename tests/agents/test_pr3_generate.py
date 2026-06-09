"""Tests for PR3: generate_reply_node + generate_decision_node.

Covers:
- generate_reply_node: LLM called with correct messages, AIMessage appended
- generate_reply_node: draft content prepended when available
- generate_reply_node: handles missing context_packet
- generate_decision_node: returns NEXT when user satisfied
- generate_decision_node: returns STAY when more info needed
- generate_decision_node: returns MODIFY when user wants to go back
- generate_decision_node: sets finished/should_generate_final_output when all sections done
- generate_decision_node: handles empty messages gracefully
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agents.xbuddy.enums import RouterDirective, SectionID, SectionStatus
from agents.xbuddy.models import (
    ChatAgentDecision,
    ContextPacket,
    ProjectBuddyData,
    SectionContent,
    SectionState,
    XBuddyState,
)
from agents.xbuddy.nodes.generate_reply import generate_reply_node
from agents.xbuddy.nodes.generate_decision import generate_decision_node, _format_messages


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

THREAD_ID = "test-pr3-thread"


def _make_context_packet(
    section_id: SectionID = SectionID.PROJECT_IDEA,
    status: SectionStatus = SectionStatus.PENDING,
    draft_text: str | None = None,
) -> ContextPacket:
    draft = None
    if draft_text:
        draft = SectionContent(content={"type": "doc"}, plain_text=draft_text)
    return ContextPacket(
        section_id=section_id,
        status=status,
        system_prompt=f"You are guiding the user through {section_id.value}.",
        draft=draft,
    )


def _make_state(
    messages: list | None = None,
    current_section: SectionID = SectionID.PROJECT_IDEA,
    context_packet: ContextPacket | None = None,
    section_states: dict[str, SectionState] | None = None,
    user_data: ProjectBuddyData | None = None,
) -> XBuddyState:
    return {
        "messages": messages or [],
        "user_id": 1,
        "thread_id": THREAD_ID,
        "current_section": current_section,
        "context_packet": context_packet or _make_context_packet(current_section),
        "section_states": section_states or {},
        "router_directive": RouterDirective.STAY,
        "finished": False,
        "user_data": user_data or ProjectBuddyData(),
        "short_memory": [],
        "agent_output": None,
        "awaiting_user_input": False,
        "awaiting_satisfaction_feedback": False,
        "error_count": 0,
        "last_error": None,
        "final_output": None,
        "should_generate_final_output": False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# _format_messages helper
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatMessages:
    def test_formats_messages(self):
        msgs = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
        ]
        result = _format_messages(msgs)
        assert "[human]: Hello" in result
        assert "[ai]: Hi there!" in result

    def test_truncates_long_content(self):
        long = "x" * 500
        msgs = [HumanMessage(content=long)]
        result = _format_messages(msgs)
        assert len(result) < 350  # truncated
        assert "..." in result

    def test_empty_list(self):
        assert _format_messages([]) == ""


# ─────────────────────────────────────────────────────────────────────────────
# generate_reply_node
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateReplyNode:
    @pytest.mark.asyncio
    async def test_calls_llm_and_appends_aimessage(self):
        state = _make_state(messages=[HumanMessage(content="I want to build an app")])
        mock_response = AIMessage(content="Great! Let's start with your project idea.")

        with patch("agents.xbuddy.nodes.generate_reply.get_model") as mock_get_model:
            mock_model = AsyncMock()
            mock_model.ainvoke = AsyncMock(return_value=mock_response)
            mock_get_model.return_value = mock_model

            result = await generate_reply_node(state, None)

        updated_msgs = result["messages"]
        assert len(updated_msgs) == 2  # original + AI response
        assert updated_msgs[-1].content == "Great! Let's start with your project idea."

    @pytest.mark.asyncio
    async def test_system_prompt_included(self):
        cp = _make_context_packet(SectionID.REQUIREMENTS)
        state = _make_state(
            messages=[HumanMessage(content="Tell me about requirements")],
            context_packet=cp,
        )
        mock_response = AIMessage(content="Let's gather requirements.")

        with patch("agents.xbuddy.nodes.generate_reply.get_model") as mock_get_model:
            mock_model = AsyncMock()
            mock_model.ainvoke = AsyncMock(return_value=mock_response)
            mock_get_model.return_value = mock_model
            mock_model.ainvoke = AsyncMock(return_value=mock_response)
            mock_get_model.return_value = mock_model

            result = await generate_reply_node(state, None)

        # Verify the LLM was called with a SystemMessage containing the prompt
        call_args = mock_model.ainvoke.call_args[0][0]
        assert any(isinstance(m, SystemMessage) for m in call_args)
        assert any("requirements" in getattr(m, "content", "").lower() for m in call_args)

    @pytest.mark.asyncio
    async def test_draft_prepended_when_available(self):
        cp = _make_context_packet(draft_text="Existing draft content")
        state = _make_state(
            messages=[HumanMessage(content="Let me review")],
            context_packet=cp,
        )
        mock_response = AIMessage(content="OK, reviewing your draft.")

        with patch("agents.xbuddy.nodes.generate_reply.get_model") as mock_get_model:
            mock_model = AsyncMock()
            mock_model.ainvoke = AsyncMock(return_value=mock_response)
            mock_get_model.return_value = mock_model

            await generate_reply_node(state, None)

        call_args = mock_model.ainvoke.call_args[0][0]
        draft_msg = [m for m in call_args if "Existing draft content" in getattr(m, "content", "")]
        assert len(draft_msg) >= 1

    @pytest.mark.asyncio
    async def test_handles_no_context_packet(self):
        state = _make_state(messages=[HumanMessage(content="Hi")])
        state["context_packet"] = None
        mock_response = AIMessage(content="Hello!")

        with patch("agents.xbuddy.nodes.generate_reply.get_model") as mock_get_model:
            mock_model = AsyncMock()
            mock_model.ainvoke = AsyncMock(return_value=mock_response)
            mock_get_model.return_value = mock_model

            result = await generate_reply_node(state, None)

        assert len(result["messages"]) == 2

    @pytest.mark.asyncio
    async def test_updates_short_memory(self):
        state = _make_state(messages=[HumanMessage(content="Hi")])
        mock_response = AIMessage(content="Hello!")

        with patch("agents.xbuddy.nodes.generate_reply.get_model") as mock_get_model:
            mock_model = AsyncMock()
            mock_model.ainvoke = AsyncMock(return_value=mock_response)
            mock_get_model.return_value = mock_model

            result = await generate_reply_node(state, None)

        assert len(result["short_memory"]) == 1
        assert result["short_memory"][0].content == "Hello!"

    @pytest.mark.asyncio
    async def test_sets_awaiting_user_input(self):
        state = _make_state(messages=[HumanMessage(content="Hi")])
        mock_response = AIMessage(content="Hello!")

        with patch("agents.xbuddy.nodes.generate_reply.get_model") as mock_get_model:
            mock_model = AsyncMock()
            mock_model.ainvoke = AsyncMock(return_value=mock_response)
            mock_get_model.return_value = mock_model

            result = await generate_reply_node(state, None)

        assert result["awaiting_user_input"] is True


# ─────────────────────────────────────────────────────────────────────────────
# generate_decision_node
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateDecisionNode:
    def _mock_decision(self, decision: ChatAgentDecision):
        """Helper: patch get_model to return a model that returns the decision as JSON text."""
        mock_model = AsyncMock()
        mock_model.ainvoke = AsyncMock(
            return_value=MagicMock(content=decision.model_dump_json())
        )
        return patch("agents.xbuddy.nodes.generate_decision.get_model", return_value=mock_model)

    @pytest.mark.asyncio
    async def test_returns_next_when_satisfied(self):
        state = _make_state(
            messages=[
                HumanMessage(content="I want to build a task manager"),
                AIMessage(content="Great idea! Let me ask about users."),
                HumanMessage(content="Students and freelancers"),
            ],
        )
        decision = ChatAgentDecision(
            router_directive="next",
            is_satisfied=True,
            should_save_content=True,
        )

        with self._mock_decision(decision):
            result = await generate_decision_node(state, None)

        assert result["router_directive"] == "next"

    @pytest.mark.asyncio
    async def test_returns_stay_when_more_info_needed(self):
        state = _make_state(
            messages=[
                HumanMessage(content="I want to build a project planning tool"),
                AIMessage(content="What problem does it solve?"),
                HumanMessage(content="I'm not sure yet"),
            ],
        )
        decision = ChatAgentDecision(
            router_directive="stay",
            is_satisfied=False,
            should_save_content=False,
        )

        with self._mock_decision(decision):
            result = await generate_decision_node(state, None)

        assert result["router_directive"] == "stay"

    @pytest.mark.asyncio
    async def test_returns_modify_when_user_wants_to_go_back(self):
        state = _make_state(
            current_section=SectionID.TECH_STACK,
            messages=[
                HumanMessage(content="Actually, let me rethink the architecture"),
            ],
        )
        decision = ChatAgentDecision(
            router_directive="modify:architecture",
            is_satisfied=False,
            should_save_content=False,
        )

        with self._mock_decision(decision):
            result = await generate_decision_node(state, None)

        assert result["router_directive"] == "modify:architecture"

    @pytest.mark.asyncio
    async def test_sets_finished_when_all_sections_done(self):
        """When decision says NEXT on the last section and all are done."""
        section_states = {
            sid.value: SectionState(section_id=sid, status=SectionStatus.DONE)
            for sid in [
                SectionID.PROJECT_IDEA,
                SectionID.REQUIREMENTS,
                SectionID.ARCHITECTURE,
                SectionID.TECH_STACK,
            ]
        }
        # IMPLEMENTATION is in progress
        section_states[SectionID.IMPLEMENTATION.value] = SectionState(
            section_id=SectionID.IMPLEMENTATION,
            status=SectionStatus.IN_PROGRESS,
        )

        state = _make_state(
            current_section=SectionID.IMPLEMENTATION,
            messages=[
                HumanMessage(content="I'm done with the plan"),
                AIMessage(content="Great, here's your blueprint."),
                HumanMessage(content="Looks good, I'm satisfied"),
            ],
            section_states=section_states,
        )
        decision = ChatAgentDecision(
            router_directive="next",
            is_satisfied=True,
            should_save_content=True,
        )

        with self._mock_decision(decision):
            result = await generate_decision_node(state, None)

        assert result.get("finished") is True
        assert result.get("should_generate_final_output") is True

    @pytest.mark.asyncio
    async def test_handles_empty_messages_gracefully(self):
        state = _make_state(messages=[])

        result = await generate_decision_node(state, None)

        assert result["router_directive"] == "stay"

    @pytest.mark.asyncio
    async def test_updates_section_state_on_save(self):
        state = _make_state(
            messages=[HumanMessage(content="My idea is a planning tool")],
            section_states={
                "project_idea": SectionState(
                    section_id=SectionID.PROJECT_IDEA,
                    status=SectionStatus.PENDING,
                )
            },
        )
        decision = ChatAgentDecision(
            router_directive="stay",
            is_satisfied=False,
            should_save_content=True,
        )

        with self._mock_decision(decision):
            result = await generate_decision_node(state, None)

        assert "section_states" in result

    @pytest.mark.asyncio
    async def test_marks_section_done_on_next(self):
        state = _make_state(
            messages=[HumanMessage(content="Done with this section")],
            section_states={
                "project_idea": SectionState(
                    section_id=SectionID.PROJECT_IDEA,
                    status=SectionStatus.IN_PROGRESS,
                )
            },
        )
        decision = ChatAgentDecision(
            router_directive="next",
            is_satisfied=True,
            should_save_content=True,
        )

        with self._mock_decision(decision):
            result = await generate_decision_node(state, None)

        section_states = result["section_states"]
        assert section_states["project_idea"].status == SectionStatus.DONE

    @pytest.mark.asyncio
    async def test_sets_agent_output_on_decision(self):
        """ChatAgentDecision should be stored as agent_output in state."""
        state = _make_state(
            messages=[HumanMessage(content="I'm done")],
        )
        decision = ChatAgentDecision(
            router_directive="next",
            is_satisfied=True,
            should_save_content=True,
        )

        with self._mock_decision(decision):
            result = await generate_decision_node(state, None)

        assert result["agent_output"] is not None
        assert result["agent_output"].router_directive == "next"

    @pytest.mark.asyncio
    async def test_does_not_overwrite_already_done_section(self):
        """STAY with no save on an already-DONE section should not modify section_states."""
        section_states = {
            "project_idea": SectionState(
                section_id=SectionID.PROJECT_IDEA,
                status=SectionStatus.DONE,
            )
        }
        state = _make_state(
            messages=[HumanMessage(content="Let me add more details")],
            section_states=section_states,
        )
        decision = ChatAgentDecision(
            router_directive="stay",
            is_satisfied=False,
            should_save_content=False,
        )

        with self._mock_decision(decision):
            result = await generate_decision_node(state, None)

        # section_states should NOT be in the result (no changes to persist)
        assert "section_states" not in result


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateEdgeCases:
    @pytest.mark.asyncio
    async def test_short_memory_capped_at_10(self):
        """generate_reply_node caps short_memory at 10 messages."""
        state = _make_state(messages=[HumanMessage(content=f"msg {i}") for i in range(15)])
        mock_response = AIMessage(content="Reply")

        with patch("agents.xbuddy.nodes.generate_reply.get_model") as mock_get_model:
            mock_model = AsyncMock()
            mock_model.ainvoke = AsyncMock(return_value=mock_response)
            mock_get_model.return_value = mock_model

            result = await generate_reply_node(state, None)

        assert len(result["short_memory"]) <= 10

    @pytest.mark.asyncio
    async def test_reply_preserves_existing_messages(self):
        """Existing messages should be preserved, new AI message appended."""
        existing = [HumanMessage(content="Hi"), AIMessage(content="Hello!")]
        state = _make_state(messages=list(existing))
        mock_response = AIMessage(content="How can I help?")

        with patch("agents.xbuddy.nodes.generate_reply.get_model") as mock_get_model:
            mock_model = AsyncMock()
            mock_model.ainvoke = AsyncMock(return_value=mock_response)
            mock_get_model.return_value = mock_model

            result = await generate_reply_node(state, None)

        assert len(result["messages"]) == 3  # 2 existing + 1 new
        assert result["messages"][0].content == "Hi"
        assert result["messages"][1].content == "Hello!"
        assert result["messages"][2].content == "How can I help?"

    @pytest.mark.asyncio
    async def test_empty_context_packet_uses_fallback(self):
        """When context_packet is None, generate_reply_node should use a generic prompt."""
        state = _make_state(messages=[HumanMessage(content="Hello")])
        state["context_packet"] = None
        mock_response = AIMessage(content="Hi there!")

        with patch("agents.xbuddy.nodes.generate_reply.get_model") as mock_get_model:
            mock_model = AsyncMock()
            mock_model.ainvoke = AsyncMock(return_value=mock_response)
            mock_get_model.return_value = mock_model

            result = await generate_reply_node(state, None)

        assert result["messages"][-1].content == "Hi there!"
