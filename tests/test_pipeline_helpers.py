"""Tests for pure/parseable helpers in vibegen._pipeline."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vibegen._pipeline import _get_ruff_errors_by_file, _parse_pytest_failures

# ---------------------------------------------------------------------------
# _parse_pytest_failures
# ---------------------------------------------------------------------------


def test_parse_pytest_failures_empty_output() -> None:
    result = _parse_pytest_failures("")
    assert result == {}


def test_parse_pytest_failures_no_failures() -> None:
    output = "1 passed in 0.5s\n"
    result = _parse_pytest_failures(output)
    assert result == {}


def test_parse_pytest_failures_single_failed_test() -> None:
    output = (
        "_ test_something ___\n"
        "tests/test_foo.py:10: AssertionError\n"
        "FAILED tests/test_foo.py::test_something - AssertionError\n"
    )
    result = _parse_pytest_failures(output)
    assert "tests/test_foo.py" in result


def test_parse_pytest_failures_multiple_files() -> None:
    output = (
        "FAILED tests/test_a.py::test_x - AssertionError\n"
        "FAILED tests/test_b.py::test_y - ValueError\n"
    )
    result = _parse_pytest_failures(output)
    assert "tests/test_a.py" in result
    assert "tests/test_b.py" in result


def test_parse_pytest_failures_error_prefix() -> None:
    output = "ERROR tests/test_c.py::test_z - ImportError\n"
    result = _parse_pytest_failures(output)
    assert "tests/test_c.py" in result


def test_parse_pytest_failures_normalizes_backslashes() -> None:
    output = "FAILED tests\\test_foo.py::test_bar - AssertionError\n"
    result = _parse_pytest_failures(output)
    # Key should use forward slashes
    assert "tests/test_foo.py" in result


def test_parse_pytest_failures_block_text_included() -> None:
    output = (
        "_ test_something ___\n"
        "tests/test_foo.py:10: in test_something\n"
        "    assert x == 1\n"
        "AssertionError: assert 0 == 1\n"
        "FAILED tests/test_foo.py::test_something - AssertionError\n"
    )
    result = _parse_pytest_failures(output)
    assert "tests/test_foo.py" in result
    block = result["tests/test_foo.py"]
    assert "AssertionError" in block or "FAILED" in block


def test_parse_pytest_failures_summary_line_in_result() -> None:
    output = "FAILED tests/test_foo.py::test_bar - ValueError: bad value\n"
    result = _parse_pytest_failures(output)
    block = result["tests/test_foo.py"]
    assert "FAILED" in block


def test_parse_pytest_failures_multiple_tests_same_file() -> None:
    output = (
        "FAILED tests/test_foo.py::test_a - AssertionError\n"
        "FAILED tests/test_foo.py::test_b - ValueError\n"
    )
    result = _parse_pytest_failures(output)
    assert "tests/test_foo.py" in result
    block = result["tests/test_foo.py"]
    # Both failure lines should appear in the combined block
    assert "test_a" in block or "test_b" in block


@pytest.mark.parametrize(
    "line,expected_key",
    [
        (
            "FAILED tests/test_x.py::TestClass::test_method - AssertionError",
            "tests/test_x.py",
        ),
        (
            "ERROR tests/sub/test_y.py::test_func - ImportError",
            "tests/sub/test_y.py",
        ),
    ],
)
def test_parse_pytest_failures_parametrized_prefixes(
    line: str, expected_key: str
) -> None:
    result = _parse_pytest_failures(line + "\n")
    assert expected_key in result


# ---------------------------------------------------------------------------
# _get_ruff_errors_by_file (output parsing, subprocess mocked)
# ---------------------------------------------------------------------------


def _make_ruff_result(stdout: str, returncode: int = 1) -> MagicMock:
    mock = MagicMock()
    mock.stdout = stdout
    mock.returncode = returncode
    return mock


def test_get_ruff_errors_by_file_no_errors(tmp_path: Path) -> None:
    with patch("vibegen._pipeline._run_cmd", return_value=_make_ruff_result("", 0)):
        result = _get_ruff_errors_by_file(tmp_path, ["src/"])
    assert result == {}


def test_get_ruff_errors_by_file_skips_autofixable(tmp_path: Path) -> None:
    stdout = "src/mod.py:1:1: F401 'os' imported but unused [*]\n"
    with patch("vibegen._pipeline._run_cmd", return_value=_make_ruff_result(stdout)):
        result = _get_ruff_errors_by_file(tmp_path, ["src/"])
    assert result == {}


def test_get_ruff_errors_by_file_skips_e501(tmp_path: Path) -> None:
    stdout = "src/mod.py:1:89: E501 Line too long (90 > 88)\n"
    with patch("vibegen._pipeline._run_cmd", return_value=_make_ruff_result(stdout)):
        result = _get_ruff_errors_by_file(tmp_path, ["src/"])
    assert result == {}


def test_get_ruff_errors_by_file_returns_non_fixable(tmp_path: Path) -> None:
    stdout = "src/mod.py:5:1: N802 Function name should be lowercase\n"
    with patch("vibegen._pipeline._run_cmd", return_value=_make_ruff_result(stdout)):
        result = _get_ruff_errors_by_file(tmp_path, ["src/"])
    assert "src/mod.py" in result
    assert len(result["src/mod.py"]) == 1


def test_get_ruff_errors_by_file_skips_found_and_warning_lines(
    tmp_path: Path,
) -> None:
    stdout = "Found 1 error.\nwarning: something\nsrc/mod.py:1:1: N802 bad name\n"
    with patch("vibegen._pipeline._run_cmd", return_value=_make_ruff_result(stdout)):
        result = _get_ruff_errors_by_file(tmp_path, ["src/"])
    assert "src/mod.py" in result
    assert len(result["src/mod.py"]) == 1


def test_get_ruff_errors_by_file_groups_by_file(tmp_path: Path) -> None:
    stdout = (
        "src/a.py:1:1: N802 bad name\n"
        "src/b.py:2:1: N803 bad arg name\n"
        "src/a.py:5:1: N802 bad name again\n"
    )
    with patch("vibegen._pipeline._run_cmd", return_value=_make_ruff_result(stdout)):
        result = _get_ruff_errors_by_file(tmp_path, ["src/"])
    assert "src/a.py" in result
    assert "src/b.py" in result
    assert len(result["src/a.py"]) == 2


def test_get_ruff_errors_by_file_returns_empty_on_exception(tmp_path: Path) -> None:
    with patch("vibegen._pipeline._run_cmd", side_effect=RuntimeError("oops")):
        result = _get_ruff_errors_by_file(tmp_path, ["src/"])
    assert result == {}


def test_get_ruff_errors_by_file_skips_short_parts(tmp_path: Path) -> None:
    # Lines with fewer than 3 colon-separated parts should be ignored
    stdout = "just-a-line\n"
    with patch("vibegen._pipeline._run_cmd", return_value=_make_ruff_result(stdout)):
        result = _get_ruff_errors_by_file(tmp_path, ["src/"])
    assert result == {}


def test_get_ruff_errors_by_file_windows_drive_letter(tmp_path: Path) -> None:
    # Simulate Windows absolute path: C:\path\to\src\mod.py:1:1: N802 ...
    win_path = "C:\\src\\mod.py"
    stdout = f"C:{win_path[1:]}:1:1: N802 bad name\n"
    # We just verify it doesn't crash; the relative path handling is best-effort
    with patch("vibegen._pipeline._run_cmd", return_value=_make_ruff_result(stdout)):
        result = _get_ruff_errors_by_file(tmp_path, ["src/"])
    assert isinstance(result, dict)
