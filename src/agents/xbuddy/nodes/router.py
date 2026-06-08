"""Router node — handles section navigation and context loading.

Runs after initialize_node on every graph cycle.

Responsibilities
----------------
1. Read ``current_section`` and ``router_directive`` from state.
2. Handle NEXT → advance to next section in SECTION_ORDER.
3. Handle MODIFY → parse ``"modify:<section_id>"``, jump back.
4. Handle STAY → keep current section as-is.
5. Check ``finished`` flag — if True and no pending user message, return
   early (graph conditional edge routes to END).
6. Build a ``ContextPacket`` with the current section's system prompt and
   any previously saved draft content.
7. Reset ``router_directive`` to STAY after processing.
"""

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from ..enums import RouterDirective, SectionID, SectionStatus
from ..models import ContextPacket, XBuddyState
from ..prompts import SECTION_ORDER, build_system_prompt

logger = logging.getLogger(__name__)


async def router_node(state: XBuddyState, config: RunnableConfig) -> dict[str, Any]:
    """Route to the correct section and load context.

    Returns a partial state dict. LangGraph merges it into the full state.
    """
    # ── 1. Read current state ───────────────────────────────────────────────
    current_section: SectionID = state.get("current_section", SectionID.PROJECT_IDEA)
    directive: str = state.get("router_directive", RouterDirective.STAY)
    section_states = state.get("section_states", {})
    finished: bool = state.get("finished", False)

    logger.info(
        "Router — directive=%s current_section=%s finished=%s",
        directive,
        current_section,
        finished,
    )

    # ── 2. Process the directive ─────────────────────────────────────────────
    if finished:
        # Layout completed — keep section as-is. The route_decision
        # conditional edge will route to END if no pending input.
        pass

    elif directive == RouterDirective.NEXT:
        next_section = _advance_section(current_section)
        if next_section is not None:
            logger.info("Advancing: %s → %s", current_section, next_section)
            current_section = next_section
        else:
            logger.info("Already at last section, staying on %s", current_section)

    elif directive.startswith("modify:"):
        target = _parse_modify_directive(directive)
        if target is not None and target in set(SectionID):
            logger.info("Modify directive: jumping from %s → %s", current_section, target)
            current_section = target
        else:
            logger.warning(
                "Invalid modify directive: %s — staying on %s",
                directive,
                current_section,
            )

    elif directive == RouterDirective.STAY:
        pass  # Keep current section

    else:
        logger.warning("Unknown directive: %s — staying on %s", directive, current_section)

    # ── 3. Build ContextPacket ───────────────────────────────────────────────
    system_prompt = build_system_prompt(current_section)
    section_state = section_states.get(current_section.value)

    context_packet = ContextPacket(
        section_id=current_section,
        status=section_state.status if section_state else SectionStatus.PENDING,
        system_prompt=system_prompt,
        draft=section_state.content if section_state else None,
    )

    # ── 4. Return partial state ──────────────────────────────────────────────
    return {
        "current_section": current_section,
        "context_packet": context_packet,
        "router_directive": RouterDirective.STAY,  # Reset after processing
    }


# ── Private helpers ─────────────────────────────────────────────────────

def _advance_section(current: SectionID) -> SectionID | None:
    """Return the next section in SECTION_ORDER, or None if at the end."""
    idx = SECTION_ORDER.index(current)
    if idx + 1 < len(SECTION_ORDER):
        return SECTION_ORDER[idx + 1]
    return None


def _parse_modify_directive(directive: str) -> SectionID | None:
    """Parse ``"modify:<section_id>"`` into a SectionID.

    Returns None if the section_id is not a valid SectionID value.
    """
    try:
        _, raw = directive.split(":", 1)
        return SectionID(raw.strip())
    except (ValueError, KeyError):
        return None

