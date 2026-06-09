"""Tests for implementation_node (Project Blueprint generation).

Covers:
- generate_blueprint: LLM called, final_output set, finished=True
- save_to_supabase: blueprint saved via save_business_plan
- full_graph_termination: graph reaches END via implementation node
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agents.xbuddy.enums import SectionID, SectionStatus
from agents.xbuddy.models import (
    ProjectBuddyData,
    SectionContent,
    SectionState,
)
from agents.xbuddy.nodes.implementation import implementation_node


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _state_with_completed_sections():
    """Return a state dict where all 5 sections are DONE with content."""
    section_states = {}
    texts = {
        "project_idea": "A task management app for students",
        "requirements": "Users can create tasks, set deadlines",
        "architecture": "React frontend, FastAPI backend, PostgreSQL",
        "tech_stack": "React, FastAPI, PostgreSQL, Docker",
        "implementation": "Phase 1: Auth + task CRUD",
    }
    for sid, text in texts.items():
        section_states[sid] = SectionState(
            section_id=SectionID(sid),
            status=SectionStatus.DONE,
            content=SectionContent(content={"type": "doc"}, plain_text=text),
        )

    return {
        "messages": [
            HumanMessage(content="I want to build an app"),
            AIMessage(content="Let's start planning"),
            HumanMessage(content="I'm satisfied with all sections"),
        ],
        "user_id": 1,
        "thread_id": "test-blueprint",
        "current_section": SectionID.IMPLEMENTATION,
        "context_packet": None,
        "section_states": section_states,
        "router_directive": "next",
        "finished": False,
        "user_data": ProjectBuddyData(
            one_line_idea="A task management app",
            functional_requirements=["User can create tasks"],
        ),
        "short_memory": [],
        "agent_output": None,
        "awaiting_user_input": False,
        "awaiting_satisfaction_feedback": False,
        "error_count": 0,
        "last_error": None,
        "final_output": None,
        "should_generate_final_output": True,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Implementation node tests
# ─────────────────────────────────────────────────────────────────────────────

class TestImplementationNode:
    @pytest.mark.asyncio
    async def test_generates_blueprint(self):
        """LLM is called, final_output is set, finished=True."""
        state = _state_with_completed_sections()
        mock_response = AIMessage(content="# Project Blueprint\n\n## Executive Summary\nA task management app.")

        with patch("agents.xbuddy.nodes.implementation.get_model") as mock_get_model:
            mock_model = AsyncMock()
            mock_model.ainvoke = AsyncMock(return_value=mock_response)
            mock_get_model.return_value = mock_model

            # Also mock Supabase to avoid missing credentials error
            with patch("integrations.supabase.supabase_client.SupabaseClient") as mock_sb:
                mock_client = MagicMock()
                mock_client.save_business_plan.return_value = {"success": True}
                mock_sb.return_value = mock_client

                result = await implementation_node(state, None)

        assert result["final_output"] is not None
        assert "# Project Blueprint" in result["final_output"]
        assert result["finished"] is True

    @pytest.mark.asyncio
    async def test_saves_to_supabase(self):
        """Blueprint is saved via save_business_plan with correct thread_id."""
        state = _state_with_completed_sections()
        mock_response = AIMessage(content="# Project Blueprint\nContent here")

        with patch("agents.xbuddy.nodes.implementation.get_model") as mock_get_model:
            mock_model = AsyncMock()
            mock_model.ainvoke = AsyncMock(return_value=mock_response)
            mock_get_model.return_value = mock_model

            with patch("integrations.supabase.supabase_client.SupabaseClient") as mock_sb:
                mock_client = MagicMock()
                mock_client.save_business_plan.return_value = {"success": True}
                mock_sb.return_value = mock_client

                await implementation_node(state, None)

        mock_client.save_business_plan.assert_called_once()
        call_kwargs = mock_client.save_business_plan.call_args.kwargs
        assert call_kwargs["thread_id"] == "test-blueprint"
        assert call_kwargs["agent_id"] == "project-buddy"

    @pytest.mark.asyncio
    async def test_handles_supabase_error_gracefully(self):
        """Supabase error doesn't crash — blueprint still in final_output."""
        state = _state_with_completed_sections()
        mock_response = AIMessage(content="# Project Blueprint\nContent")

        with patch("agents.xbuddy.nodes.implementation.get_model") as mock_get_model:
            mock_model = AsyncMock()
            mock_model.ainvoke = AsyncMock(return_value=mock_response)
            mock_get_model.return_value = mock_model

            with patch("integrations.supabase.supabase_client.SupabaseClient") as mock_sb:
                mock_client = MagicMock()
                mock_client.save_business_plan.return_value = {"success": False, "error": "DB down"}
                mock_sb.return_value = mock_client

                result = await implementation_node(state, None)

        assert result["final_output"] is not None
        assert result["finished"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Full graph test
# ─────────────────────────────────────────────────────────────────────────────

class TestFullGraphWithImplementation:
    @pytest.mark.asyncio
    async def test_full_graph_terminates_via_implementation(self):
        """When should_generate_final_output=True, the graph reaches END via implementation.

        Uses the resume path (mocked Supabase rows) so initialize_node
        doesn't overwrite the completed section_states.
        """
        from agents.xbuddy.agent import graph as xbuddy_graph

        state = _state_with_completed_sections()

        # Mock Supabase to return completed section rows (resume path)
        supabase_rows = [
            {"section_id": "project_idea", "status": "done",
             "content": {"type": "doc"}, "plain_text": "A task app", "satisfaction_status": "satisfied"},
            {"section_id": "requirements", "status": "done",
             "content": {"type": "doc"}, "plain_text": "FRs listed", "satisfaction_status": "satisfied"},
            {"section_id": "architecture", "status": "done",
             "content": {"type": "doc"}, "plain_text": "Components designed", "satisfaction_status": "satisfied"},
            {"section_id": "tech_stack", "status": "done",
             "content": {"type": "doc"}, "plain_text": "Tech chosen", "satisfaction_status": "satisfied"},
            {"section_id": "implementation", "status": "in_progress",  # current section
             "content": {"type": "doc"}, "plain_text": "Phases planned", "satisfaction_status": None},
        ]

        # Mock LLM for generate_reply
        mock_reply_model = AsyncMock()
        mock_reply_model.ainvoke = AsyncMock(return_value=AIMessage(content="Great, let's generate your blueprint!"))

        # Mock LLM for generate_decision
        import json
        mock_decision_response = MagicMock()
        mock_decision_response.content = json.dumps({
            "router_directive": "next",
            "user_satisfaction_feedback": None,
            "is_satisfied": True,
            "should_save_content": True,
        })
        mock_decision_model = AsyncMock()
        mock_decision_model.ainvoke = AsyncMock(return_value=mock_decision_response)

        # Mock LLM for implementation_node
        mock_impl_response = AIMessage(content="# Project Blueprint\nComplete!")
        mock_impl_model = AsyncMock()
        mock_impl_model.ainvoke = AsyncMock(return_value=mock_impl_response)

        # Mock Supabase
        mock_supabase = MagicMock()
        mock_supabase.save_section_state.return_value = {"success": True}
        mock_supabase.save_conversation_message.return_value = {"success": True}
        mock_supabase.save_business_plan.return_value = {"success": True}
        mock_supabase.get_section_states.return_value = supabase_rows

        async def _async_shim(fn, *args, **kwargs):
            return fn(*args, **kwargs)

        patches = [
            patch("agents.xbuddy.nodes.initialize.asyncio.to_thread", new=_async_shim),
            patch("agents.xbuddy.nodes.generate_reply.get_model", return_value=mock_reply_model),
            patch("agents.xbuddy.nodes.generate_decision.get_model", return_value=mock_decision_model),
            patch("agents.xbuddy.nodes.memory_updater.asyncio.to_thread", new=_async_shim),
            patch("agents.xbuddy.nodes.implementation.get_model", return_value=mock_impl_model),
            patch("integrations.supabase.supabase_client.SupabaseClient", return_value=mock_supabase),
        ]

        for p in patches:
            p.start()

        try:
            result = await xbuddy_graph.ainvoke(state, {"configurable": {"thread_id": "test-impl-graph", "user_id": 1}})
        finally:
            for p in patches:
                p.stop()

        # Graph should have run through implementation_node
        assert result.get("finished") is True
        assert result.get("final_output") is not None
        assert "# Project Blueprint" in result["final_output"]
