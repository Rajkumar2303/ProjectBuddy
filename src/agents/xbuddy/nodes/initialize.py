"""Initialize node — validates and sets up conversation state.

Runs once at the start of every graph invocation (before router).

Responsibilities
----------------
1. Extract ``thread_id`` / ``user_id`` from LangGraph config or existing state.
2. Query Supabase for persisted section rows.
3. RESUME  → rebuild ``section_states``, resolve ``current_section``.
   COLD START → set all defaults, create empty ``ProjectBuddyData``.
4. Return a partial state dict — does NOT touch messages, LLM output, or routing.
"""

import asyncio
import logging
import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig

from ..enums import SectionID, SectionStatus
from ..models import ProjectBuddyData, SectionContent, SectionState, XBuddyState

logger = logging.getLogger(__name__)

# Canonical section ordering — order here IS the dependency chain.
SECTION_ORDER: list[SectionID] = [
    SectionID.PROJECT_IDEA,
    SectionID.REQUIREMENTS,
    SectionID.ARCHITECTURE,
    SectionID.TECH_STACK,
    SectionID.IMPLEMENTATION,
]


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _build_section_state(row: dict[str, Any]) -> SectionState:
    """Reconstruct a ``SectionState`` from a raw Supabase row.

    Raises ``ValueError`` if the row contains an unrecognised ``section_id``
    or ``status`` — caller should catch and skip corrupted rows.
    """
    raw_content = row.get("content")
    content: SectionContent | None = None
    if raw_content:
        content = SectionContent(
            content=raw_content if isinstance(raw_content, dict) else {},
            plain_text=row.get("plain_text"),
        )

    return SectionState(
        section_id=SectionID(row["section_id"]),           # raises ValueError on bad value
        content=content,
        satisfaction_status=row.get("satisfaction_status"),
        status=SectionStatus(row.get("status", SectionStatus.PENDING)),
    )


def _first_incomplete_section(section_states: dict[str, SectionState]) -> SectionID:
    """Return the first section in ``SECTION_ORDER`` whose status is not DONE.

    Falls back to the last section if everything is somehow marked DONE
    (implementation_node will set ``should_generate_final_output`` in that case).
    """
    for sid in SECTION_ORDER:
        state = section_states.get(sid.value)
        if state is None or state.status != SectionStatus.DONE:
            return sid
    return SECTION_ORDER[-1]


def _all_sections_done(section_states: dict[str, SectionState]) -> bool:
    """Return True only when every section in SECTION_ORDER is DONE."""
    return all(
        section_states.get(sid.value, SectionState(section_id=sid)).status == SectionStatus.DONE
        for sid in SECTION_ORDER
    )


def _fetch_section_states(user_id: int, thread_id: str) -> list[dict[str, Any]]:
    """Synchronous Supabase fetch — run inside ``asyncio.to_thread``."""
    from integrations.supabase.supabase_client import SupabaseClient  # lazy import
    return SupabaseClient().get_section_states(user_id, thread_id)


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

async def initialize_node(state: XBuddyState, config: RunnableConfig) -> dict[str, Any]:
    """Initialize or resume conversation state.

    Cold start
    ----------
    - Sets ``current_section`` to PROJECT_IDEA.
    - Initialises all ``section_states`` as PENDING.
    - Creates an empty ``ProjectBuddyData``.

    Resume
    ------
    - Restores ``section_states`` from Supabase.
    - Resolves ``current_section`` to the first non-DONE section.
    - Marks ``finished = True`` when all sections are DONE.

    Returns a *partial* state dict — LangGraph merges it into the full state.
    Does NOT set ``messages``, ``agent_output``, ``context_packet``, or any
    routing fields — those are the responsibility of downstream nodes.
    """
    # ── 1. Resolve identity ─────────────────────────────────────────────────
    configurable: dict[str, Any] = config.get("configurable", {}) if config else {}

    thread_id: str = (
        configurable.get("thread_id")
        or state.get("thread_id")
        or str(uuid.uuid4())
    )
    user_id: int = int(
        configurable.get("user_id")
        or state.get("user_id")
        or 1
    )

    # ── 2. Attempt Supabase lookup ───────────────────────────────────────────
    raw_rows: list[dict[str, Any]] = []
    try:
        raw_rows = await asyncio.to_thread(_fetch_section_states, user_id, thread_id)
    except Exception as exc:
        logger.warning(
            "Supabase unavailable during initialize (cold start fallback): %s",
            exc,
        )
        raw_rows = []

    # ── 3a. RESUME ───────────────────────────────────────────────────────────
    if raw_rows:
        logger.info(
            "Resuming session — user_id=%s thread_id=%s (%d persisted sections)",
            user_id,
            thread_id,
            len(raw_rows),
        )

        section_states: dict[str, SectionState] = {}
        for row in raw_rows:
            try:
                s = _build_section_state(row)
                section_states[s.section_id.value] = s
            except (ValueError, KeyError) as exc:
                logger.warning(
                    "Skipping corrupted section row (section_id=%r): %s",
                    row.get("section_id"),
                    exc,
                )

        # Safety: if all rows were corrupted, fall through to cold start
        if not section_states:
            logger.warning(
                "All Supabase rows were corrupted for thread_id=%s — performing cold start",
                thread_id,
            )
        else:
            current_section = _first_incomplete_section(section_states)
            finished = _all_sections_done(section_states)

            return {
                "user_id": user_id,
                "thread_id": thread_id,
                "section_states": section_states,
                "current_section": current_section,
                "finished": finished,
                "should_generate_final_output": False,  # implementation_node sets this
                "error_count": 0,
                "last_error": None,
            }

    # ── 3b. COLD START ───────────────────────────────────────────────────────
    logger.info(
        "Cold start — user_id=%s thread_id=%s",
        user_id,
        thread_id,
    )

    initial_section_states: dict[str, SectionState] = {
        sid.value: SectionState(section_id=sid, status=SectionStatus.PENDING)
        for sid in SECTION_ORDER
    }

    return {
        "user_id": user_id,
        "thread_id": thread_id,
        "section_states": initial_section_states,
        "current_section": SectionID.PROJECT_IDEA,
        "user_data": ProjectBuddyData(),
        "finished": False,
        "should_generate_final_output": False,
        "error_count": 0,
        "last_error": None,
    }

