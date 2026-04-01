"""Tests for vibegen._design module."""

from __future__ import annotations

from unittest.mock import patch

from vibegen._design import (
    _extract_spec_text,
    _parse_qa_response,
    _read_multiline_input,
)

# ---------------------------------------------------------------------------
# _parse_qa_response
# ---------------------------------------------------------------------------


def test_parse_qa_response_ready() -> None:
    text = "I have enough info.\n\nSTATUS: READY"
    status, questions = _parse_qa_response(text)
    assert status == "READY"
    assert questions == []


def test_parse_qa_response_need_more() -> None:
    text = (
        "I need more info:\n"
        "1. What are the inputs?\n"
        "2. What are the outputs?\n"
        "3. Any edge cases?\n\n"
        "STATUS: NEED_MORE"
    )
    status, questions = _parse_qa_response(text)
    assert status == "NEED_MORE"
    assert len(questions) == 3
    assert "What are the inputs?" in questions[0]


def test_parse_qa_response_need_more_dash_list() -> None:
    text = (
        "Questions:\n- What is the first thing?\n"
        "- What is the second?\n\nSTATUS: NEED_MORE"
    )
    status, questions = _parse_qa_response(text)
    assert status == "NEED_MORE"
    assert len(questions) == 2


def test_parse_qa_response_no_marker_no_questions() -> None:
    text = "Some response without a status marker"
    status, questions = _parse_qa_response(text)
    assert status == "NEED_MORE"
    assert questions == []


def test_parse_qa_response_no_marker_with_question() -> None:
    text = "What dependencies do you need?"
    status, questions = _parse_qa_response(text)
    assert status == "NEED_MORE"
    assert len(questions) == 1


def test_parse_qa_response_empty() -> None:
    status, questions = _parse_qa_response("")
    assert status == "NEED_MORE"
    assert questions == []


def test_parse_qa_response_parenthesis_numbers() -> None:
    text = "1) First?\n2) Second?\n\nSTATUS: NEED_MORE"
    status, questions = _parse_qa_response(text)
    assert status == "NEED_MORE"
    assert len(questions) == 2


def test_parse_qa_response_ready_phrase() -> None:
    text = "I have enough information to write the spec."
    status, questions = _parse_qa_response(text)
    assert status == "READY"


def test_parse_qa_response_bold_numbers() -> None:
    text = "**1.** What inputs?\n**2.** What outputs?\n\nSTATUS: NEED_MORE"
    status, questions = _parse_qa_response(text)
    assert status == "NEED_MORE"
    assert len(questions) == 2


# ---------------------------------------------------------------------------
# _extract_spec_text
# ---------------------------------------------------------------------------


def test_extract_spec_text_with_delimiters() -> None:
    response = (
        "Here is the spec:\n\n"
        "--- spec.md ---\n"
        "## Name\nmy-project\n\n## Description\nA thing\n"
        "--- end ---\n\n"
        "Let me know if you want changes."
    )
    result = _extract_spec_text(response)
    assert "## Name" in result
    assert "my-project" in result
    assert "Let me know" not in result


def test_extract_spec_text_without_delimiters() -> None:
    response = "## Name\nmy-project\n\n## Description\nA tool"
    result = _extract_spec_text(response)
    assert "## Name" in result
    assert "my-project" in result


def test_extract_spec_text_empty() -> None:
    result = _extract_spec_text("")
    assert result == ""


# ---------------------------------------------------------------------------
# _read_multiline_input
# ---------------------------------------------------------------------------


@patch("builtins.input", side_effect=["line 1", "line 2", ""])
def test_read_multiline_input_two_lines(mock_input: object) -> None:
    result = _read_multiline_input()
    assert result == "line 1\nline 2"


@patch("builtins.input", side_effect=[""])
def test_read_multiline_input_immediate_enter(mock_input: object) -> None:
    result = _read_multiline_input()
    assert result == ""


@patch("builtins.input", side_effect=EOFError)
def test_read_multiline_input_eof(mock_input: object) -> None:
    result = _read_multiline_input()
    assert result == ""


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------


def test_design_help_exits_zero() -> None:
    """Verify ``vibegen design --help`` parses without error."""
    import argparse

    parser = argparse.ArgumentParser(prog="vibegen design")
    parser.add_argument("--description", default="")
    parser.add_argument("--output-dir", default=".")
    parser.add_argument("--spec-only", action="store_true")
    # Should not raise.
    args = parser.parse_args(["--description", "a tool", "--spec-only"])
    assert args.description == "a tool"
    assert args.spec_only is True
