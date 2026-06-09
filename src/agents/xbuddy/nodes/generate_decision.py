"""Generate decision node — analyzes the conversation and decides next action.

This node:
  1. Reads the current section goal and latest user message from state
  2. Calls the LLM with a structured decision prompt
  3. Produces a ``ChatAgentDecision`` with ``router_directive``,
     ``is_satisfied``, and ``should_save_content``
  4. Checks if all sections are now DONE → sets ``finished`` /
     ``should_generate_final_output``
"""

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from core import get_model

from ..enums import SectionID, SectionStatus
from ..models import (
    ChatAgentDecision,
    ContextPacket,
    SectionState,
    XBuddyState,
)
from ..prompts import SECTION_ORDER, get_next_unfinished_section

logger = logging.getLogger(__name__)

DECISION_SYSTEM_PROMPT = """You are evaluating a project-planning conversation.

Your job is to read the current section's goal and the conversation so far,
then decide what the agent should do next. Respond ONLY with valid JSON in
exactly this format — no markdown, no code fences, no extra text:

{
  "router_directive": "next",
  "user_satisfaction_feedback": null,
  "is_satisfied": false,
  "should_save_content": false
}

Rules for router_directive:
- "next" — user has given enough info and seems satisfied; advance.
- "stay" — needs more info or user has questions; continue current section.
- "modify:<section_id>" — user wants to go back to a previous section
  (section_id: project_idea, requirements, architecture, tech_stack, or
  implementation).

Other rules:
- Set is_satisfied to true only if the user has explicitly confirmed
  satisfaction.
- Set should_save_content to true if the conversation produced substantive
  new content worth persisting.
- Set user_satisfaction_feedback to null unless there's a specific concern.
"""


async def generate_decision_node(state: XBuddyState, config: RunnableConfig) -> dict[str, Any]:
    """Analyze conversation and produce a structured decision.

    Returns a partial state dict with router_directive, section_states
    updates, and potentially finished/should_generate_final_output.
    """
    context_packet: ContextPacket | None = state.get("context_packet")
    messages = state.get("messages", [])
    section_states: dict[str, SectionState] = dict(state.get("section_states", {}))
    current_section: SectionID = state.get("current_section", SectionID.PROJECT_IDEA)
    user_data = state.get("user_data")

    if not messages:
        logger.warning("No messages to evaluate — staying on current section")
        return {"router_directive": "stay"}

    # ── 1. Build decision prompt ─────────────────────────────────────────────
    section_goal = (
        context_packet.system_prompt[:500] if context_packet else "General conversation"
    )

    decision_messages = [
        SystemMessage(content=DECISION_SYSTEM_PROMPT),
        HumanMessage(
            content=f"Current section: {current_section.value}\n\n"
            f"Section goal/prompt (first 500 chars):\n{section_goal}\n\n"
            f"Conversation history ({len(messages)} messages):\n"
            + _format_messages(messages[-6:])  # last 6 messages for context
            + "\n\nDecide the next action."
        ),
    ]

    # ── 2. Call LLM and parse JSON response manually ─────────────────────────
    # NOTE: we avoid with_structured_output() because some providers (DeepSeek)
    # do not support the "response_format" parameter. Instead we ask for JSON
    # in the prompt and parse the response string ourselves.
    model = get_model()
    raw_response = await model.ainvoke(decision_messages)
    decision = _parse_decision(raw_response.content)

    if decision is None:
        logger.warning("Failed to parse LLM decision response — defaulting to stay")
        return {"router_directive": "stay"}

    logger.info(
        "Decision: directive=%s satisfied=%s save=%s",
        decision.router_directive,
        decision.is_satisfied,
        decision.should_save_content,
    )

    # ── 3. Update section state if content should be saved ───────────────────
    result: dict[str, Any] = {
        "router_directive": decision.router_directive,
        "agent_output": decision,
    }

    if decision.should_save_content:
        current_state = section_states.get(current_section.value)
        if current_state:
            current_state.status = SectionStatus.IN_PROGRESS
            section_states[current_section.value] = current_state
        else:
            section_states[current_section.value] = SectionState(
                section_id=current_section,
                status=SectionStatus.IN_PROGRESS,
            )
        result["section_states"] = section_states

    # ── 4. Handle NEXT → mark section as DONE, check if all done ────────────
    if decision.router_directive == "next":
        # Mark current section as DONE
        current_state = section_states.get(current_section.value)
        if current_state:
            current_state.status = SectionStatus.DONE
            current_state.satisfaction_status = (
                "satisfied" if decision.is_satisfied else "needs_improvement"
            )
        else:
            section_states[current_section.value] = SectionState(
                section_id=current_section,
                status=SectionStatus.DONE,
            )
        result["section_states"] = section_states

        # Check if all sections are done
        unfinished = get_next_unfinished_section(section_states)
        if unfinished is None:
            # All sections complete — prepare for final blueprint
            result["finished"] = True
            result["should_generate_final_output"] = True
            logger.info("All sections complete — ready for final blueprint")

    return result


def _parse_decision(text: str) -> ChatAgentDecision | None:
    """Parse a ChatAgentDecision from LLM JSON response.

    Tries JSON parsing first, then falls back to regex extraction if the
    LLM wrapped the JSON in markdown or added extra text.
    """
    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove opening ```json or ``` and closing ```
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    # Try direct JSON parse
    try:
        data = json.loads(cleaned)
        return ChatAgentDecision(**data)
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Fallback: try to find a JSON object by bracket-balancing (handles
    # nested JSON, unlike a flat regex).
    for i, ch in enumerate(cleaned):
        if ch == "{":
            depth = 0
            for j in range(i, len(cleaned)):
                if cleaned[j] == "{":
                    depth += 1
                elif cleaned[j] == "}":
                    depth -= 1
                if depth == 0:
                    candidate = cleaned[i : j + 1]
                    try:
                        data = json.loads(candidate)
                        return ChatAgentDecision(**data)
                    except (json.JSONDecodeError, ValueError, TypeError):
                        pass
                    break  # mismatched braces — move on

    logger.warning("Could not parse decision from LLM response: %.100s", text)
    return None


def _format_messages(msgs: list) -> str:
    """Format a list of messages into a readable string for the decision prompt."""
    parts = []
    for m in msgs:
        role = getattr(m, "type", "unknown")
        content = getattr(m, "content", "")
        # Truncate long content
        if isinstance(content, str) and len(content) > 300:
            content = content[:300] + "..."
        parts.append(f"[{role}]: {content}")
    return "\n".join(parts)

