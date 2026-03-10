"""Low-level I/O utilities shared across all vibegen modules."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from .sandbox import SandboxConfig


def _write_file(path: Path, content: str) -> None:
    """Write a text file with LF line endings (avoids CRLF warnings on Windows).

    Args:
        path: Destination file path.
        content: Text content to write.
    """
    path.write_text(content, encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# Console helpers
# ---------------------------------------------------------------------------


def _print_step(message: str) -> None:
    """Print a [STEP] progress message."""
    print(f"[STEP]  {message}")


def _print_ok(message: str) -> None:
    """Print an [OK] success message."""
    print(f"[OK]    {message}")


def _print_warn(message: str) -> None:
    """Print a [WARN] warning message."""
    print(f"[WARN]  {message}")


def _print_err(message: str) -> None:
    """Print an [ERR] error message to stderr."""
    print(f"[ERR]   {message}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------


def _run_cmd(
    args: list[str],
    cwd: Path | None = None,
    capture_output: bool = False,
    check: bool = True,
    env: dict[str, str] | None = None,
    sandbox: SandboxConfig | None = None,
) -> subprocess.CompletedProcess[Any]:
    """Run a subprocess, optionally wrapping it in the Docker sandbox.

    Args:
        args: Command and arguments to run.
        cwd: Working directory for the subprocess.
        capture_output: Whether to capture stdout/stderr.
        check: Raise on non-zero exit code when True.
        env: Optional environment variable overrides.
        sandbox: When provided, sandboxable commands are wrapped with Docker.

    Returns:
        The completed process result.
    """
    actual_args = args
    actual_cwd = cwd
    if sandbox is not None and sandbox.should_sandbox(args, cwd):
        actual_args = sandbox.build_docker_args(args)
        actual_cwd = None  # Docker handles cwd via -w /workspace
    return subprocess.run(
        actual_args,
        cwd=actual_cwd,
        capture_output=capture_output,
        text=True,
        env=env,
        check=check,
    )
