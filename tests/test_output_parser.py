"""Tests for vibegen._output_parser module."""

from __future__ import annotations

from pathlib import Path

import pytest

from vibegen._output_parser import (
    _clean_file_content,
    _parse_generated_files,
    _write_generated_files,
)

# ---------------------------------------------------------------------------
# _clean_file_content
# ---------------------------------------------------------------------------


def test_clean_file_content_strips_code_fence() -> None:
    lines = ["```python", "x = 1", "```"]
    result = _clean_file_content(lines)
    assert result == "x = 1"


def test_clean_file_content_no_fence() -> None:
    # Without fences, non-code content is outside in_code_block → not captured
    lines = ["just some text"]
    result = _clean_file_content(lines)
    assert result == ""


def test_clean_file_content_narrative_stops_at_first_fence() -> None:
    # Narrative prose after the closing fence causes the loop to break,
    # so the second code block is never reached.
    lines = ["```python", "x = 1", "```", "some prose", "```python", "y = 2", "```"]
    result = _clean_file_content(lines)
    # First fence content is returned; second fence is unreachable after prose
    assert "x = 1" in result
    assert "y = 2" not in result


def test_clean_file_content_second_fence_resets_when_no_prose() -> None:
    # Without narrative prose, a second fence reopens and resets result.
    lines = ["```python", "x = 1", "```", "```python", "y = 2", "```"]
    result = _clean_file_content(lines)
    assert "y = 2" in result
    assert "x = 1" not in result


def test_clean_file_content_strips_trailing_newlines() -> None:
    lines = ["```", "code here", "```"]
    result = _clean_file_content(lines)
    assert not result.endswith("\n")


def test_clean_file_content_narrative_after_closing_fence_discarded() -> None:
    lines = ["```python", "x = 1", "```", "This is a narrative paragraph"]
    result = _clean_file_content(lines)
    assert "narrative" not in result


def test_clean_file_content_empty_lines_list() -> None:
    result = _clean_file_content([])
    assert result == ""


def test_clean_file_content_preserves_indentation() -> None:
    lines = ["```python", "def foo():", "    return 1", "```"]
    result = _clean_file_content(lines)
    assert "    return 1" in result


# ---------------------------------------------------------------------------
# _parse_generated_files
# ---------------------------------------------------------------------------


def test_parse_generated_files_basic() -> None:
    output = "--- file: src/mod.py ---\n```python\nx = 1\n```\n--- end ---"
    result = _parse_generated_files(output)
    assert "src/mod.py" in result
    assert "x = 1" in result["src/mod.py"]


def test_parse_generated_files_without_file_keyword() -> None:
    output = "--- src/mod.py ---\n```python\nx = 1\n```\n"
    result = _parse_generated_files(output)
    assert "src/mod.py" in result


def test_parse_generated_files_multiple_files() -> None:
    output = (
        "--- file: a.py ---\n```python\na = 1\n```\n"
        "--- file: b.py ---\n```python\nb = 2\n```\n"
    )
    result = _parse_generated_files(output)
    assert "a.py" in result
    assert "b.py" in result


def test_parse_generated_files_skips_end_marker() -> None:
    output = "--- file: a.py ---\n```python\na = 1\n```\n--- end ---\n"
    result = _parse_generated_files(output)
    assert "end" not in result
    assert "a.py" in result


def test_parse_generated_files_empty_output() -> None:
    result = _parse_generated_files("")
    assert result == {}


def test_parse_generated_files_no_valid_blocks() -> None:
    result = _parse_generated_files("just some text without markers")
    assert result == {}


def test_parse_generated_files_skips_empty_content() -> None:
    output = "--- file: empty.py ---\n```python\n   \n```\n"
    result = _parse_generated_files(output)
    # Content is only whitespace → should be skipped
    assert "empty.py" not in result


def test_parse_generated_files_end_marker_case_insensitive() -> None:
    output = "--- file: a.py ---\n```python\nx=1\n```\n--- END ---"
    result = _parse_generated_files(output)
    assert "a.py" in result


@pytest.mark.parametrize(
    "marker",
    [
        "--- file: tests/test_foo.py ---",
        "--- tests/test_foo.py ---",
    ],
)
def test_parse_generated_files_various_marker_styles(marker: str) -> None:
    output = f"{marker}\n```python\nimport pytest\n```\n"
    result = _parse_generated_files(output)
    assert "tests/test_foo.py" in result


# ---------------------------------------------------------------------------
# _write_generated_files
# ---------------------------------------------------------------------------


def test_write_generated_files_creates_files(tmp_path: Path) -> None:
    files = {"src/mod.py": "x = 1\n"}
    count = _write_generated_files(tmp_path, files)
    assert count == 1
    assert (tmp_path / "src" / "mod.py").read_text(encoding="utf-8") == "x = 1\n"


def test_write_generated_files_returns_count(tmp_path: Path) -> None:
    files = {"a.py": "a=1\n", "b.py": "b=2\n"}
    count = _write_generated_files(tmp_path, files)
    assert count == 2


def test_write_generated_files_creates_parent_dirs(tmp_path: Path) -> None:
    files = {"deep/nested/dir/module.py": "pass\n"}
    _write_generated_files(tmp_path, files)
    assert (tmp_path / "deep" / "nested" / "dir" / "module.py").exists()


def test_write_generated_files_empty_dict(tmp_path: Path) -> None:
    count = _write_generated_files(tmp_path, {})
    assert count == 0


def test_write_generated_files_prints_ok(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"out.py": "pass\n"}
    _write_generated_files(tmp_path, files)
    captured = capsys.readouterr()
    assert "out.py" in captured.out
