"""Enumerations for your XBuddy Agent."""

from enum import Enum


class SectionStatus(str, Enum):
    """Status of an agent section."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class RouterDirective(str, Enum):
    """Router directive for navigation control."""
    STAY = "stay"
    NEXT = "next"
    MODIFY = "modify"  # Format: "modify:section_id"


class SectionID(str, Enum):
    """ProjectBuddy section identifiers — ordered by dependency chain.

    The order is non-negotiable:
      PROJECT_IDEA → REQUIREMENTS → ARCHITECTURE → TECH_STACK → IMPLEMENTATION
    Each section is a required input to the next.
    """
    PROJECT_IDEA = "project_idea"
    REQUIREMENTS = "requirements"
    ARCHITECTURE = "architecture"
    TECH_STACK = "tech_stack"
    IMPLEMENTATION = "implementation"
