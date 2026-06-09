"""End-to-end tests for the compiled XBuddy graph (PR 5).

Tests the full graph assembly: all nodes connected, edges route correctly,
memory_updater fires on every turn, and the loop terminates when finished.

Graph structure under test::

    START → initialize → router → generate_reply → generate_decision
                ^                                          │
                └──────────── memory_updater ←─────────────┘
                                     │
                                     └──→ END  (when finished=True)
"""

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agents.xbuddy.agent import graph as xbuddy_graph
from agents.xbuddy.enums import RouterDirective, SectionID, SectionStatus
from agents.xbuddy.models import (
    ChatAgentDecision,
    ProjectBuddyData,
    SectionContent,
    SectionState,
    XBuddyState,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

THREAD_ID = "test-e2e-" + str(uuid.uuid4())
USER_ID = 1


def _initial_state() -> dict[str, Any]:
    return {
        "messages": [HumanMessage(content="I want to build a task management app")],
        "user_id": USER_ID,
        "thread_id": THREAD_ID,
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


def _e2e_mocks():
    """Patch everything external: Supabase, LLM, and asyncio.to_thread.

    Returns a dict of mock objects for assertions.
    """
    # Mock LLM for generate_reply
    mock_reply_model = AsyncMock()
    mock_reply_model.ainvoke = AsyncMock(
        return_value=AIMessage(content="Great! Let's start with your project idea. What exactly do you want to build?")
    )

    # Mock LLM for generate_decision — returns JSON that ChatAgentDecision can parse
    mock_decision_response = MagicMock()
    mock_decision_response.content = json.dumps({
        "router_directive": "stay",
        "user_satisfaction_feedback": None,
        "is_satisfied": False,
        "should_save_content": True,
    })

    mock_decision_model = AsyncMock()
    mock_decision_model.ainvoke = AsyncMock(return_value=mock_decision_response)

    # Mock Supabase
    mock_supabase = MagicMock()
    mock_supabase.save_section_state.return_value = {"success": True}
    mock_supabase.save_conversation_message.return_value = {"success": True}
    mock_supabase.get_section_states.return_value = []  # Cold start — no persisted data

    mocks = {
        "supabase_client": mock_supabase,
        "reply_model": mock_reply_model,
        "decision_model": mock_decision_model,
    }

    patches = [
        # All to_thread shims need to be async so await works
        patch("agents.xbuddy.nodes.initialize.asyncio.to_thread", new=_async_shim),
        patch("agents.xbuddy.nodes.generate_reply.get_model", return_value=mock_reply_model),
        patch("agents.xbuddy.nodes.generate_decision.get_model", return_value=mock_decision_model),
        patch("agents.xbuddy.nodes.memory_updater.asyncio.to_thread", new=_async_shim),
        patch("integrations.supabase.supabase_client.SupabaseClient", return_value=mock_supabase),
    ]

    return mocks, patches


async def _async_shim(fn, *args, **kwargs):
    """Async shim for ``asyncio.to_thread`` — calls fn and returns its result as an awaitable."""
    return fn(*args, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Graph tests
# ─────────────────────────────────────────────────────────────────────────────

class TestGraphEndToEnd:
    @pytest.mark.asyncio
    async def test_cold_start_full_turn(self):
        """Cold start: runs initialize → router → generate_reply → generate_decision → memory_updater, loops back to router.

        Note: the initial state has ``router_directive: NEXT``, so the router
        advances from PROJECT_IDEA to REQUIREMENTS on the first pass (before
        generate_decision has a chance to say "stay"). This is correct — the
        decision on the NEXT turn will determine if we advance further.
        """
        mocks, patches = _e2e_mocks()
        state = _initial_state()

        for p in patches:
            p.start()

        try:
            # Invoke the graph — runs one full cycle
            result = await xbuddy_graph.ainvoke(state, {"configurable": {"thread_id": THREAD_ID, "user_id": USER_ID}})
        finally:
            for p in patches:
                p.stop()

        # After one full turn, the graph should have:
        # - An AI message in messages (from generate_reply)
        assert len(result.get("messages", [])) >= 1
        last_msg = result["messages"][-1]
        assert isinstance(last_msg, AIMessage)
        assert "project" in last_msg.content.lower()

        # - current_section advanced to REQUIREMENTS (initial directive was NEXT)
        assert result["current_section"] == SectionID.REQUIREMENTS

        # - router_directive was reset to STAY
        assert result["router_directive"] == RouterDirective.STAY

        # - memory_updater was called — the AI message was persisted.
        # Section states are skipped on cold start (PENDING, no content).
        assert mocks["supabase_client"].save_conversation_message.call_count >= 1

        # - finished is False (all sections not done yet)
        assert result.get("finished") is False

    @pytest.mark.asyncio
    async def test_graph_loops_back_to_router(self):
        """After one turn, the graph should loop back to router (not END)."""
        mocks, patches = _e2e_mocks()
        state = _initial_state()

        for p in patches:
            p.start()

        try:
            result = await xbuddy_graph.ainvoke(state, {"configurable": {"thread_id": THREAD_ID, "user_id": USER_ID}})
        finally:
            for p in patches:
                p.stop()

        # The graph should NOT have finished
        assert result.get("finished") is False
        # context_packet should be populated (router ran)
        assert result.get("context_packet") is not None
        assert result["context_packet"].section_id == SectionID.REQUIREMENTS

    @pytest.mark.asyncio
    async def test_supabase_called_on_every_turn(self):
        """Memory_updater should call Supabase on every turn, even for cold start."""
        mocks, patches = _e2e_mocks()
        state = _initial_state()

        for p in patches:
            p.start()

        try:
            await xbuddy_graph.ainvoke(state, {"configurable": {"thread_id": THREAD_ID, "user_id": USER_ID}})
        finally:
            for p in patches:
                p.stop()

        # save_conversation_message should have been called (new AI message)
        assert mocks["supabase_client"].save_conversation_message.call_count >= 1

    @pytest.mark.asyncio
    async def test_resume_path_works(self):
        """Graph can resume from a partially-completed state."""
        mocks, patches = _e2e_mocks()
        state = _initial_state()

        # Simulate a resume scenario: PROJECT_IDEA already DONE
        state["section_states"] = {
            "project_idea": SectionState(
                section_id=SectionID.PROJECT_IDEA,
                status=SectionStatus.DONE,
                content=SectionContent(content={"type": "doc"}, plain_text="Built a task app"),
            ),
        }
        state["current_section"] = SectionID.REQUIREMENTS
        state["messages"] = [HumanMessage(content="I want users to be able to create tasks and set deadlines")]

        for p in patches:
            p.start()

        try:
            result = await xbuddy_graph.ainvoke(state, {"configurable": {"thread_id": THREAD_ID, "user_id": USER_ID}})
        finally:
            for p in patches:
                p.stop()

        # Should be on REQUIREMENTS section
        assert result["current_section"] == SectionID.REQUIREMENTS

    @pytest.mark.asyncio
    async def test_agent_id_is_project_buddy(self):
        """Verify the agent_id 'project-buddy' is passed to Supabase."""
        mocks, patches = _e2e_mocks()
        state = _initial_state()

        for p in patches:
            p.start()

        try:
            await xbuddy_graph.ainvoke(state, {"configurable": {"thread_id": THREAD_ID, "user_id": USER_ID}})
        finally:
            for p in patches:
                p.stop()

        # Check that save_section_state received the right agent_id
        for call in mocks["supabase_client"].save_section_state.call_args_list:
            assert call.kwargs.get("agent_id") == "project-buddy"

        # Check that save_conversation_message received the right agent_id
        for call in mocks["supabase_client"].save_conversation_message.call_args_list:
            assert call.kwargs.get("agent_id") == "project-buddy"
