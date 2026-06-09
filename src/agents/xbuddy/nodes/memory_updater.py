"""Memory updater node — persists section state and manages completion.

Responsibilities
----------------
1. Iterate ``section_states`` and persist any that have content or are DONE.
2. Persist the latest conversation message to Supabase.
3. Return state unchanged (pure side-effect node — graph wiring already
   handles the loop-back via ``route_after_memory_updater``).
"""

import asyncio
import logging
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig

from ..enums import SectionStatus
from ..models import XBuddyState

logger = logging.getLogger(__name__)

_AGENT_ID = "project-buddy"


def _save_section_state(
    client: Any,
    section_id: str,
    section_state: Any,
    user_id: int,
    thread_id: str,
) -> None:
    """Sync helper — persists a single section state row to Supabase.

    The caller (``memory_updater_node``) is responsible for filtering out
    sections that don't need persisting. This function trusts the caller.
    """
    result = client.save_section_state(
        user_id=user_id,
        thread_id=thread_id,
        section_id=section_id,
        agent_id=_AGENT_ID,
        content=section_state.content.content if section_state.content else {},
        plain_text=section_state.content.plain_text if section_state.content else "",
        status=section_state.status.value,
        satisfaction_status=section_state.satisfaction_status,
    )
    if not result.get("success"):
        logger.warning("Failed to save section %s: %s", section_id, result.get("error"))


def _save_message(client: Any, user_id: int, thread_id: str, msg: Any) -> None:
    """Sync helper — persists a single message to Supabase."""
    role = getattr(msg, "type", "unknown")
    content = getattr(msg, "content", "")
    if not content:
        return

    result = client.save_conversation_message(
        user_id=user_id,
        thread_id=thread_id,
        role=role,
        content=str(content),
        agent_id=_AGENT_ID,
    )
    if not result.get("success"):
        logger.warning("Failed to save message: %s", result.get("error"))


async def memory_updater_node(state: XBuddyState, config: RunnableConfig) -> dict[str, Any]:
    """Update section state, persist data, check completion.

    Returns an **empty** dict — this node is a pure side-effect operation.
    The ``route_after_memory_updater`` conditional edge decides whether to
    loop back to ``router`` or go to ``implementation``.
    """
    from integrations.supabase.supabase_client import SupabaseClient

    user_id: int = state.get("user_id", 1)
    if user_id == 1:
        logger.warning("user_id defaulted to 1 — check that the caller is passing a real user ID")
    thread_id: str = state.get("thread_id", "unknown")
    section_states = state.get("section_states", {})
    messages = state.get("messages", [])

    # Single client instance for the entire turn
    client = SupabaseClient()

    # ── 1. Persist section states ────────────────────────────────────────────
    for section_id, section_state in section_states.items():
        if section_state.content is None and section_state.status != SectionStatus.DONE:
            continue
        try:
            await asyncio.to_thread(
                _save_section_state,
                client,
                section_id,
                section_state,
                user_id,
                thread_id,
            )
        except Exception as exc:
            logger.error("Error persisting section %s: %s", section_id, exc)

    # ── 2. Persist the latest assistant message ──────────────────────────────
    if messages and isinstance(messages[-1], AIMessage):
        try:
            await asyncio.to_thread(_save_message, client, user_id, thread_id, messages[-1])
        except Exception as exc:
            logger.error("Error persisting message: %s", exc)

    logger.info(
        "Memory updated — %d section(s), %d message(s)",
        len(section_states),
        len(messages),
    )

    return {}
