"""Tests for HandoffExtractor and HandoffSchema."""

import pytest

from app.schemas.handoff import HandoffSchema
from app.services.handoff_extractor import HandoffExtractor


@pytest.fixture
def extractor() -> HandoffExtractor:
    return HandoffExtractor()


# ---------------------------------------------------------------------------
# Test 1: all four sections extracted
# ---------------------------------------------------------------------------


def test_extract_all_four_sections(extractor: HandoffExtractor) -> None:
    content = (
        "## What Was Done\n"
        "Implemented the login endpoint and wrote 5 tests.\n"
        "\n"
        "## Decisions Made\n"
        "- Used JWT over session cookies for statelessness.\n"
        "\n"
        "## Open Questions\n"
        "- Should we rate-limit the endpoint?\n"
        "\n"
        "## Next Agent Context\n"
        "The endpoint is at POST /auth/login. Next: add refresh token support.\n"
    )
    result = extractor.extract(content)
    assert result is not None
    assert result.what_was_done == "Implemented the login endpoint and wrote 5 tests."
    assert "JWT" in (result.decisions_made or "")
    assert "rate-limit" in (result.open_questions or "")
    assert "POST /auth/login" in (result.next_agent_context or "")


# ---------------------------------------------------------------------------
# Test 2: partial sections
# ---------------------------------------------------------------------------


def test_extract_partial_sections(extractor: HandoffExtractor) -> None:
    content = (
        "## What Was Done\nRefactored the auth module.\n\n## Next Agent Context\nContinue with adding rate limiting.\n"
    )
    result = extractor.extract(content)
    assert result is not None
    assert result.what_was_done == "Refactored the auth module."
    assert result.next_agent_context == "Continue with adding rate limiting."
    assert result.decisions_made is None
    assert result.open_questions is None


# ---------------------------------------------------------------------------
# Test 3: no recognized sections → None
# ---------------------------------------------------------------------------


def test_extract_returns_none_when_no_sections(extractor: HandoffExtractor) -> None:
    content = "Just a plain paragraph of text.\n\nNo headings here at all."
    assert extractor.extract(content) is None


# ---------------------------------------------------------------------------
# Test 4: empty / whitespace-only input → None
# ---------------------------------------------------------------------------


def test_extract_returns_none_for_empty_input(extractor: HandoffExtractor) -> None:
    assert extractor.extract("") is None
    assert extractor.extract("   \n\n\t  ") is None


# ---------------------------------------------------------------------------
# Test 5: case-insensitive heading matching
# ---------------------------------------------------------------------------


def test_extract_case_insensitive_headings(extractor: HandoffExtractor) -> None:
    content = (
        "## WHAT WAS DONE\n"
        "Done in caps.\n"
        "\n"
        "## Decisions Made\n"
        "Mixed case decision.\n"
        "\n"
        "## OPEN QUESTIONS\n"
        "Any?\n"
        "\n"
        "## Next Agent Context\n"
        "lowercase context.\n"
    )
    result = extractor.extract(content)
    assert result is not None
    assert result.what_was_done == "Done in caps."
    assert result.decisions_made == "Mixed case decision."
    assert result.open_questions == "Any?"
    assert result.next_agent_context == "lowercase context."


# ---------------------------------------------------------------------------
# Test 6: strips whitespace from field content
# ---------------------------------------------------------------------------


def test_extract_strips_whitespace(extractor: HandoffExtractor) -> None:
    content = "## What Was Done\n\n\n   Implemented something.   \n\n## Next Agent Context\n   Do more things.   \n"
    result = extractor.extract(content)
    assert result is not None
    assert result.what_was_done == "Implemented something."
    assert result.next_agent_context == "Do more things."


# ---------------------------------------------------------------------------
# Test 7: content before first heading is ignored (preamble)
# ---------------------------------------------------------------------------


def test_extract_ignores_preamble(extractor: HandoffExtractor) -> None:
    content = (
        "Here is my summary report for the sprint.\n"
        "\n"
        "This preamble should be ignored completely.\n"
        "\n"
        "## What Was Done\n"
        "Fixed the bug.\n"
    )
    result = extractor.extract(content)
    assert result is not None
    assert result.what_was_done == "Fixed the bug."
    # preamble must not appear in any field
    assert "preamble" not in (result.what_was_done or "")


# ---------------------------------------------------------------------------
# Test 8: duplicate headings — first occurrence wins
# ---------------------------------------------------------------------------


def test_extract_duplicate_heading_first_wins(extractor: HandoffExtractor) -> None:
    content = (
        "## What Was Done\n"
        "First occurrence content.\n"
        "\n"
        "## What Was Done\n"
        "Second occurrence content — should be ignored.\n"
    )
    result = extractor.extract(content)
    assert result is not None
    assert result.what_was_done == "First occurrence content."


# ---------------------------------------------------------------------------
# Test 9: to_context_header with all fields and agent_name
# ---------------------------------------------------------------------------


def test_to_context_header_all_fields() -> None:
    schema = HandoffSchema(
        what_was_done="Did the thing.",
        decisions_made="Chose A over B.",
        open_questions="Is C needed?",
        next_agent_context="Continue with D.",
    )
    header = schema.to_context_header(agent_name="developer")
    assert header.startswith("## Handoff from previous step (developer)")
    assert "**What was done**: Did the thing." in header
    assert "**Decisions made**:" in header
    assert "Chose A over B." in header
    assert "**Open questions**:" in header
    assert "Is C needed?" in header
    assert "**Your task**: Continue with D." in header


# ---------------------------------------------------------------------------
# Test 10: to_context_header omits empty/None fields
# ---------------------------------------------------------------------------


def test_to_context_header_omits_empty_fields() -> None:
    schema = HandoffSchema(
        what_was_done="Did the thing.",
        decisions_made=None,
        open_questions=None,
        next_agent_context="Continue with D.",
    )
    header = schema.to_context_header()
    assert "**Decisions made**:" not in header
    assert "**Open questions**:" not in header
    assert "**What was done**: Did the thing." in header
    assert "**Your task**: Continue with D." in header


# ---------------------------------------------------------------------------
# Test 11: to_context_header without agent_name
# ---------------------------------------------------------------------------


def test_to_context_header_without_agent_name() -> None:
    schema = HandoffSchema(what_was_done="Done.")
    header = schema.to_context_header()
    assert header.startswith("## Handoff from previous step")
    assert "(" not in header.splitlines()[0]


# ---------------------------------------------------------------------------
# Test 12: is_empty returns True when all None
# ---------------------------------------------------------------------------


def test_is_empty_true_when_all_none() -> None:
    schema = HandoffSchema()
    assert schema.is_empty() is True


# ---------------------------------------------------------------------------
# Test 13: is_empty returns False when any field set
# ---------------------------------------------------------------------------


def test_is_empty_false_when_any_field_set() -> None:
    schema = HandoffSchema(what_was_done="Something happened.")
    assert schema.is_empty() is False
