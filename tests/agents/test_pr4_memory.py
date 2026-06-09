"""Tests for PR4: memory_updater_node + Supabase persistence.

Covers:
- Saves sections with content (skips PENDING/null-content sections)
- Passes correct agent_id="project-buddy" to save_section_state
- Saves the latest AIMessage via save_conversation_message
- Skips save when last message is not an AIMessage
- Handles Supabase errors gracefully (logs, doesn't crash)
- Returns empty dict (pure side-effect node)
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from agents.xbuddy.enums import SectionID, SectionStatus
from agents.xbuddy.models import (
    ProjectBuddyData,
    SectionContent,
    SectionState,
    XBuddyState,
)
from agents.xbuddy.nodes.memory_updater import memory_updater_node


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

THREAD_ID = "test-pr4-thread"
USER_ID = 1


def _make_state(
    section_states: dict[str, SectionState] | None = None,
    messages: list | None = None,
) -> XBuddyState:
    return {
        "messages": messages or [],
        "user_id": USER_ID,
        "thread_id": THREAD_ID,
        "current_section": SectionID.PROJECT_IDEA,
        "context_packet": None,
        "section_states": section_states or {},
        "router_directive": "stay",
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


def _section_with_content(
    section_id: SectionID,
    text: str = "some content",
    status: SectionStatus = SectionStatus.IN_PROGRESS,
) -> SectionState:
    return SectionState(
        section_id=section_id,
        status=status,
        content=SectionContent(content={"type": "doc"}, plain_text=text),
    )


def _pending_section(section_id: SectionID) -> SectionState:
    return SectionState(section_id=section_id, status=SectionStatus.PENDING)


# ─────────────────────────────────────────────────────────────────────────────
# memory_updater_node
# ─────────────────────────────────────────────────────────────────────────────

class TestMemoryUpdaterNode:
    def _mock_supabase(self, success: bool = True):
        """Patch SupabaseClient and make to_thread run synchronously."""
        mock_client = MagicMock()
        mock_client.save_section_state.return_value = {"success": success}
        mock_client.save_conversation_message.return_value = {"success": success}

        return (
            patch(
                "integrations.supabase.supabase_client.SupabaseClient",
                return_value=mock_client,
            ),
            patch(
                "agents.xbuddy.nodes.memory_updater.asyncio.to_thread",
                new=lambda fn, *a, **kw: fn(*a, **kw),
            ),
            mock_client,
        )

    @pytest.mark.asyncio
    async def test_saves_sections_with_content(self):
        """Sections that have content should be persisted via save_section_state."""
        states = {
            "project_idea": _section_with_content(SectionID.PROJECT_IDEA),
            "requirements": _section_with_content(
                SectionID.REQUIREMENTS, text="requirements text"
            ),
        }
        state = _make_state(
            section_states=states,
            messages=[AIMessage(content="Hello!")],
        )

        supabase_patch, to_thread_patch, mock_client = self._mock_supabase()
        with supabase_patch, to_thread_patch:
            result = await memory_updater_node(state, None)

        assert mock_client.save_section_state.call_count == 2
        # Check agent_id was passed correctly
        for call in mock_client.save_section_state.call_args_list:
            assert call.kwargs["agent_id"] == "project-buddy"

        assert result == {}

    @pytest.mark.asyncio
    async def test_skips_pending_null_content_sections(self):
        """PENDING sections with no content should NOT be saved."""
        states = {
            "project_idea": _pending_section(SectionID.PROJECT_IDEA),
            "requirements": _section_with_content(SectionID.REQUIREMENTS),
        }
        state = _make_state(
            section_states=states,
            messages=[AIMessage(content="Hi")],
        )

        supabase_patch, to_thread_patch, mock_client = self._mock_supabase()
        with supabase_patch, to_thread_patch:
            await memory_updater_node(state, None)

        # Only the requirements section (with content) should be saved
        assert mock_client.save_section_state.call_count == 1
        saved_section_id = mock_client.save_section_state.call_args.kwargs["section_id"]
        assert saved_section_id == "requirements"

    @pytest.mark.asyncio
    async def test_saves_done_sections_even_without_content(self):
        """DONE sections should be saved even if content is somehow None."""
        states = {
            "project_idea": SectionState(
                section_id=SectionID.PROJECT_IDEA,
                status=SectionStatus.DONE,
            ),
        }
        state = _make_state(
            section_states=states,
            messages=[AIMessage(content="All done")],
        )

        supabase_patch, to_thread_patch, mock_client = self._mock_supabase()
        with supabase_patch, to_thread_patch:
            await memory_updater_node(state, None)

        assert mock_client.save_section_state.call_count == 1

    @pytest.mark.asyncio
    async def test_saves_aimessage_via_conversation_messages(self):
        """The latest AIMessage should be saved via save_conversation_message."""
        state = _make_state(
            messages=[AIMessage(content="How can I help you?")],
        )

        supabase_patch, to_thread_patch, mock_client = self._mock_supabase()
        with supabase_patch, to_thread_patch:
            await memory_updater_node(state, None)

        mock_client.save_conversation_message.assert_called_once()
        call_kwargs = mock_client.save_conversation_message.call_args.kwargs
        assert call_kwargs["role"] == "ai"
        assert call_kwargs["content"] == "How can I help you?"

    @pytest.mark.asyncio
    async def test_skips_save_when_last_message_not_aimessage(self):
        """If the last message is a HumanMessage, don't save (only save AI replies)."""
        state = _make_state(
            messages=[HumanMessage(content="I want to build an app")],
        )

        supabase_patch, to_thread_patch, mock_client = self._mock_supabase()
        with supabase_patch, to_thread_patch:
            await memory_updater_node(state, None)

        mock_client.save_conversation_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_supabase_error_gracefully(self):
        """Supabase errors should be logged, not crash the graph."""
        states = {
            "project_idea": _section_with_content(SectionID.PROJECT_IDEA),
        }
        state = _make_state(
            section_states=states,
            messages=[AIMessage(content="Hello")],
        )

        supabase_patch, to_thread_patch, mock_client = self._mock_supabase(success=False)
        with supabase_patch, to_thread_patch:
            # Should not raise — errors are caught and logged
            result = await memory_updater_node(state, None)

        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_dict(self):
        """memory_updater_node is a pure side-effect node — returns {}."""
        state = _make_state()

        supabase_patch, to_thread_patch, mock_client = self._mock_supabase()
        with supabase_patch, to_thread_patch:
            result = await memory_updater_node(state, None)

        assert result == {}

    @pytest.mark.asyncio
    async def test_correct_agent_id_in_message_save(self):
        """save_conversation_message should receive agent_id='project-buddy'."""
        state = _make_state(
            messages=[AIMessage(content="Tell me about your project")],
        )

        supabase_patch, to_thread_patch, mock_client = self._mock_supabase()
        with supabase_patch, to_thread_patch:
            await memory_updater_node(state, None)

        call_kwargs = mock_client.save_conversation_message.call_args.kwargs
        assert call_kwargs["agent_id"] == "project-buddy"

    @pytest.mark.asyncio
    async def test_saves_content_mapping_correct(self):
        """Verify the field mapping: content.content, plain_text, status.value."""
        content = SectionContent(
            content={"type": "doc", "content": [{"text": "hello"}]},
            plain_text="hello world",
        )
        states = {
            "project_idea": SectionState(
                section_id=SectionID.PROJECT_IDEA,
                status=SectionStatus.IN_PROGRESS,
                content=content,
            ),
        }
        state = _make_state(
            section_states=states,
            messages=[AIMessage(content="OK")],
        )

        supabase_patch, to_thread_patch, mock_client = self._mock_supabase()
        with supabase_patch, to_thread_patch:
            await memory_updater_node(state, None)

        call_kwargs = mock_client.save_section_state.call_args.kwargs
        assert call_kwargs["content"] == content.content
        assert call_kwargs["plain_text"] == "hello world"
        assert call_kwargs["status"] == "in_progress"
