"""HandoffExtractor — parses structured handoff data from raw Markdown agent output."""

import re

from app.schemas.handoff import HandoffSchema

# Maps normalized heading text to HandoffSchema field names.
_FIELD_KEYS = {
    "whatwasdone": "what_was_done",
    "decisionsmade": "decisions_made",
    "openquestions": "open_questions",
    "nextagentcontext": "next_agent_context",
}


def _normalize(text: str) -> str:
    """Lower-case and strip all non-alphanumeric characters."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


class HandoffExtractor:
    """Extracts a structured HandoffSchema from raw Markdown agent output.

    Uses heading-based parsing. Does not log — returns None on failure,
    and the caller handles logging and audit events.
    """

    def extract(self, content_md: str) -> HandoffSchema | None:
        """Parse Markdown headings to populate HandoffSchema fields.

        Returns None if extraction fails (no recognized sections found,
        or input is empty/whitespace-only). If a heading appears multiple
        times, the first occurrence wins.
        """
        if not content_md or not content_md.strip():
            return None

        fields: dict[str, str] = {}
        current_field: str | None = None
        current_lines: list[str] = []

        for line in content_md.splitlines():
            if line.startswith("#"):
                # Flush previous section
                if current_field and current_field not in fields:
                    fields[current_field] = "\n".join(current_lines).strip()
                current_field = None
                current_lines = []

                heading_text = line.lstrip("#").strip()
                normalized = _normalize(heading_text)
                if normalized in _FIELD_KEYS:
                    field_name = _FIELD_KEYS[normalized]
                    # First occurrence wins — only set current_field if not seen yet
                    if field_name not in fields:
                        current_field = field_name
            elif current_field is not None:
                current_lines.append(line)

        # Flush last section
        if current_field and current_field not in fields:
            fields[current_field] = "\n".join(current_lines).strip()

        if not fields:
            return None

        schema = HandoffSchema(**fields)
        if schema.is_empty():
            return None
        return schema
