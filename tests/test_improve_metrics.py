"""Tests for vibegen._improve_metrics module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from vibegen._improve_metrics import (
    _run_mypy_raw,
    _run_pytest_raw,
    _run_ruff_raw,
    _run_verification,
)


def _mock_run_cmd(stdout: str = "", returncode: int = 0) -> MagicMock:
    """Create a mock CompletedProcess."""
    result = MagicMock()
    result.stdout = stdout
    result.stderr = ""
    result.returncode = returncode
    return result


# ---------------------------------------------------------------------------
# Individual tool runners
# ---------------------------------------------------------------------------


@patch("vibegen._improve_metrics._run_cmd")
def test_run_pytest_raw(mock_cmd: MagicMock) -> None:
    mock_cmd.return_value = _mock_run_cmd("5 passed in 0.3s")
    output = _run_pytest_raw(Path("/fake"))
    assert "5 passed" in output
    mock_cmd.assert_called_once()


@patch("vibegen._improve_metrics._run_cmd")
def test_run_pytest_raw_failure(mock_cmd: MagicMock) -> None:
    mock_cmd.side_effect = Exception("not found")
    output = _run_pytest_raw(Path("/fake"))
    assert "not available" in output


@patch("vibegen._improve_metrics._run_cmd")
def test_run_ruff_raw(mock_cmd: MagicMock) -> None:
    mock_cmd.return_value = _mock_run_cmd("All checks passed!")
    output = _run_ruff_raw(Path("/fake"))
    assert "All checks passed" in output


@patch("vibegen._improve_metrics._run_cmd")
def test_run_mypy_raw(mock_cmd: MagicMock) -> None:
    mock_cmd.return_value = _mock_run_cmd("Success: no issues found")
    output = _run_mypy_raw(Path("/fake"))
    assert "Success" in output


@patch("vibegen._improve_metrics._run_cmd")
def test_run_mypy_raw_not_installed(mock_cmd: MagicMock) -> None:
    mock_cmd.side_effect = Exception("not found")
    output = _run_mypy_raw(Path("/fake"))
    assert "not available" in output


# ---------------------------------------------------------------------------
# Full verification suite
# ---------------------------------------------------------------------------


@patch("vibegen._improve_metrics._run_cmd")
def test_run_verification_returns_all_keys(mock_cmd: MagicMock) -> None:
    mock_cmd.return_value = _mock_run_cmd("ok")
    result = _run_verification(Path("/fake"))
    assert "pytest" in result
    assert "ruff" in result
    assert "mypy" in result
