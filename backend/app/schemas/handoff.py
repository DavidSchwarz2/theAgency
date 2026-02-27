"""Pydantic schema for structured handoff data between pipeline agents."""

from pydantic import BaseModel


class HandoffSchema(BaseModel):
    """Structured representation of what one agent passed to the next.

    All fields are optional because agents may produce partial structured output.
    Use `is_empty()` to check if extraction yielded anything meaningful.
    """

    what_was_done: str | None = None
    decisions_made: str | None = None
    open_questions: str | None = None
    next_agent_context: str | None = None

    def is_empty(self) -> bool:
        """Return True if all fields are None or empty strings."""
        return not any(
            v for v in (self.what_was_done, self.decisions_made, self.open_questions, self.next_agent_context)
        )

    def to_context_header(self, agent_name: str | None = None) -> str:
        """Render a compact Markdown context header for the next agent.

        Includes agent_name in the heading if provided.
        Omits fields that are None or empty.
        """
        heading = f"## Handoff from previous step ({agent_name})" if agent_name else "## Handoff from previous step"
        lines = [heading, ""]

        if self.what_was_done:
            lines.append(f"**What was done**: {self.what_was_done}")
            lines.append("")

        if self.decisions_made:
            lines.append("**Decisions made**:")
            lines.append(self.decisions_made)
            lines.append("")

        if self.open_questions:
            lines.append("**Open questions**:")
            lines.append(self.open_questions)
            lines.append("")

        if self.next_agent_context:
            lines.append(f"**Your task**: {self.next_agent_context}")
            lines.append("")

        return "\n".join(lines).rstrip()
