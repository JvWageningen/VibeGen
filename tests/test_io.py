"""Tests for vibegen._io module."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vibegen._io import (
    _print_err,
    _print_ok,
    _print_step,
    _print_warn,
    _run_cmd,
    _write_file,
)
from vibegen.sandbox import SandboxConfig

# ---------------------------------------------------------------------------
# _write_file
# ---------------------------------------------------------------------------


def test_write_file_creates_file(tmp_path: Path) -> None:
    dest = tmp_path / "out.txt"
    _write_file(dest, "hello world")
    assert dest.exists()
    assert dest.read_text(encoding="utf-8") == "hello world"


def test_write_file_lf_line_endings(tmp_path: Path) -> None:
    dest = tmp_path / "out.txt"
    _write_file(dest, "line1\nline2")
    raw = dest.read_bytes()
    assert b"\r\n" not in raw


def test_write_file_overwrites_existing(tmp_path: Path) -> None:
    dest = tmp_path / "out.txt"
    dest.write_text("old content", encoding="utf-8")
    _write_file(dest, "new content")
    assert dest.read_text(encoding="utf-8") == "new content"


def test_write_file_nested_directory(tmp_path: Path) -> None:
    dest = tmp_path / "sub" / "dir" / "file.py"
    dest.parent.mkdir(parents=True)
    _write_file(dest, "# code")
    assert dest.read_text(encoding="utf-8") == "# code"


# ---------------------------------------------------------------------------
# Console helpers
# ---------------------------------------------------------------------------


def test_print_step_format(capsys: pytest.CaptureFixture[str]) -> None:
    _print_step("doing something")
    captured = capsys.readouterr()
    assert "[STEP]" in captured.out
    assert "doing something" in captured.out


def test_print_ok_format(capsys: pytest.CaptureFixture[str]) -> None:
    _print_ok("done")
    captured = capsys.readouterr()
    assert "[OK]" in captured.out
    assert "done" in captured.out


def test_print_warn_format(capsys: pytest.CaptureFixture[str]) -> None:
    _print_warn("careful")
    captured = capsys.readouterr()
    assert "[WARN]" in captured.out
    assert "careful" in captured.out


def test_print_err_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    _print_err("something went wrong")
    captured = capsys.readouterr()
    assert "[ERR]" in captured.err
    assert "something went wrong" in captured.err


# ---------------------------------------------------------------------------
# _run_cmd
# ---------------------------------------------------------------------------


def test_run_cmd_basic(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        _run_cmd(["echo", "hello"], cwd=tmp_path)
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["echo", "hello"]


def test_run_cmd_capture_output(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="output", stderr="")
        _run_cmd(["echo", "hi"], cwd=tmp_path, capture_output=True)
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["capture_output"] is True


def test_run_cmd_text_mode(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        _run_cmd(["cmd"], cwd=tmp_path)
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["text"] is True


def test_run_cmd_passes_env(tmp_path: Path) -> None:
    env = {"MY_VAR": "value"}
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        _run_cmd(["cmd"], cwd=tmp_path, env=env)
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs["env"] == env


def test_run_cmd_with_sandbox_wraps_command(tmp_path: Path) -> None:
    sandbox = SandboxConfig(project_path=tmp_path, enabled=True)
    subdir = tmp_path / "sub"
    subdir.mkdir()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        _run_cmd(["uv", "run", "pytest"], cwd=subdir, sandbox=sandbox)
        actual_args = mock_run.call_args[0][0]
        assert actual_args[0] == "docker"
        assert "run" in actual_args


def test_run_cmd_with_sandbox_skips_host_only(tmp_path: Path) -> None:
    sandbox = SandboxConfig(project_path=tmp_path, enabled=True)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        _run_cmd(["git", "status"], cwd=tmp_path, sandbox=sandbox)
        actual_args = mock_run.call_args[0][0]
        # Should NOT be wrapped in docker
        assert actual_args[0] == "git"


def test_run_cmd_without_sandbox(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        _run_cmd(["uv", "run", "pytest"], cwd=tmp_path, sandbox=None)
        actual_args = mock_run.call_args[0][0]
        assert actual_args[0] == "uv"


def test_run_cmd_check_true_raises_on_nonzero(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "cmd")
        with pytest.raises(subprocess.CalledProcessError):
            _run_cmd(["bad-cmd"], cwd=tmp_path, check=True)
