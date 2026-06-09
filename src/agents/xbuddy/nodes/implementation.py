"""Implementation node — generates the final Project Blueprint when all sections are complete.

This node:
  1. Gathers all section data from section_states and user_data
  2. Calls the LLM to synthesise the Project Blueprint Markdown
  3. Saves the output to Supabase
  4. Returns updated state with final_output
"""

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from core import get_model

from ..models import XBuddyState
from ..prompts import BLUEPRINT_SYNTHESIS_PROMPT, SECTION_ORDER

logger = logging.getLogger(__name__)


async def implementation_node(state: XBuddyState, config: RunnableConfig) -> dict[str, Any]:
    """Generate the final Project Blueprint artifact.

    Returns a partial state dict with ``final_output`` set to the generated
    Markdown and ``finished`` set to True.
    """
    section_states = state.get("section_states", {})
    user_data = state.get("user_data")
    thread_id: str = state.get("thread_id", "unknown")
    user_id: int = state.get("user_id", 1)

    # ── 1. Gather section content ────────────────────────────────────────────
    sections_text = _gather_sections(section_states, user_data)

    # ── 2. Call LLM to synthesise blueprint ──────────────────────────────────
    messages = [
        SystemMessage(content=BLUEPRINT_SYNTHESIS_PROMPT),
        HumanMessage(content=f"Here is all the collected information from the planning session:\n\n{sections_text}\n\nPlease generate the complete Project Blueprint Markdown document."),
    ]

    model = get_model()
    response = await model.ainvoke(messages)
    blueprint_markdown = str(response.content)

    logger.info(
        "Blueprint generated — %d characters for thread %s",
        len(blueprint_markdown),
        thread_id,
    )

    # ── 3. Save to Supabase (best-effort) ────────────────────────────────────
    try:
        from integrations.supabase.supabase_client import SupabaseClient
        client = SupabaseClient()
        result = client.save_business_plan(
            user_id=user_id,
            thread_id=thread_id,
            content='{"type":"doc","content":[]}',  # Tiptap JSON (frontend expects JSON, not Markdown)
            markdown_content=blueprint_markdown,
            agent_id="project-buddy",
        )
        if not result.get("success"):
            logger.warning("Failed to save blueprint to Supabase: %s", result.get("error"))
    except Exception as exc:
        logger.warning("Supabase not available — blueprint saved only in state: %s", exc)

    # ── 4. Return updated state ──────────────────────────────────────────────
    return {
        "final_output": blueprint_markdown,
        "finished": True,
    }


def _gather_sections(section_states: dict[str, Any], user_data: Any) -> str:
    """Build a single text blob from all section data for the LLM prompt."""
    parts = []

    for sid in SECTION_ORDER:
        state = section_states.get(sid.value)
        label = sid.value.replace("_", " ").title()
        if state and state.content and state.content.plain_text:
            parts.append(f"=== {label} ===\n{state.content.plain_text}\n")
        elif state and state.content:
            parts.append(f"=== {label} ===\n{state.content.content}\n")
        else:
            parts.append(f"=== {label} ===\n(No content provided)\n")

    # Append structured data if available
    if user_data:
        dumped = user_data.model_dump(exclude_none=True)
        if dumped:
            parts.append(f"=== Structured Data ===\n{dumped}\n")

    return "\n".join(parts)
