"""Generate reply node — creates conversational responses.

This node:
  1. Reads the ``context_packet`` (system prompt + optional draft) from state
  2. Builds the full messages list for the LLM call
  3. Calls the LLM via ``get_model()``
  4. Appends the AI response as an ``AIMessage`` to ``state["messages"]``
  5. Updates ``short_memory`` (rolling window)
"""

import logging
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from core import get_model

from ..models import XBuddyState

logger = logging.getLogger(__name__)


async def generate_reply_node(state: XBuddyState, config: RunnableConfig) -> dict[str, Any]:
    """Generate a conversational reply for the current section.

    Returns a partial state dict with updated ``messages`` and
    ``short_memory``.
    """
    context_packet = state.get("context_packet")
    if not context_packet:
        logger.warning("No context_packet in state — using generic prompt")
        system_prompt = "You are a helpful assistant."
    else:
        system_prompt = context_packet.system_prompt

    # ── 1. Build messages ────────────────────────────────────────────────────
    messages = [SystemMessage(content=system_prompt)]

    # Optionally prepend draft content as system context (not a user
    # utterance, so the LLM treats it as reference material).
    draft = context_packet.draft if context_packet else None
    if draft and draft.plain_text:
        messages.append(
            SystemMessage(
                content=f"[Draft content for this section:\n{draft.plain_text}\n]"
            )
        )

    # Append conversation history
    existing_messages = state.get("messages", [])
    messages.extend(existing_messages)

    logger.debug(
        "Calling LLM with %d messages (system + %d history)",
        len(messages),
        len(existing_messages),
    )

    # ── 2. Call the LLM ──────────────────────────────────────────────────────
    model = get_model()
    response = await model.ainvoke(messages)

    # ── 3. Append AI message ─────────────────────────────────────────────────
    updated_messages = list(existing_messages) + [response]

    # ── 4. Update short_memory (rolling window of last 10 messages) ──────────
    short_memory = list(state.get("short_memory", []))
    short_memory.append(response)
    if len(short_memory) > 10:
        short_memory = short_memory[-10:]

    return {
        "messages": updated_messages,
        "short_memory": short_memory,
        "awaiting_user_input": True,
    }

