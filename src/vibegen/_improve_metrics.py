"""Verification runner for the iterative improvement loop.

Runs pytest, ruff, and mypy and captures raw output for Claude to evaluate.
Does NOT interpret pass/fail — that is Claude's job.
"""

from __future__ import annotations

from pathlib import Path

from ._io import _print_step, _print_warn, _run_cmd


def _run_pytest_raw(project_path: Path) -> str:
    """Run pytest and return the raw combined output.

    Args:
        project_path: Project root directory.

    Returns:
        Combined stdout + stderr from ``uv run pytest --tb=short -q``.
    """
    try:
        result = _run_cmd(
            ["uv", "run", "pytest", "--tb=short", "-q"],
            cwd=project_path,
            capture_output=True,
            check=False,
        )
        return (result.stdout or "") + (result.stderr or "")
    except Exception:  # noqa: BLE001
        return "(pytest not available or failed to run)"


def _run_ruff_raw(project_path: Path) -> str:
    """Run ruff check and return the raw output.

    Args:
        project_path: Project root directory.

    Returns:
        Combined stdout + stderr from ``uv run ruff check .``.
    """
    try:
        result = _run_cmd(
            ["uv", "run", "ruff", "check", "."],
            cwd=project_path,
            capture_output=True,
            check=False,
        )
        return (result.stdout or "") + (result.stderr or "")
    except Exception:  # noqa: BLE001
        return "(ruff not available or failed to run)"


def _run_mypy_raw(project_path: Path) -> str:
    """Run mypy and return the raw output.

    Args:
        project_path: Project root directory.

    Returns:
        Combined stdout + stderr from ``uv run mypy src/``, or a fallback
        message if mypy is not installed.
    """
    try:
        result = _run_cmd(
            ["uv", "run", "mypy", "src/"],
            cwd=project_path,
            capture_output=True,
            check=False,
        )
        return (result.stdout or "") + (result.stderr or "")
    except Exception:  # noqa: BLE001
        return "(mypy not available or failed to run)"


def _run_verification(project_path: Path) -> dict[str, str]:
    """Run the full verification suite and capture raw output.

    Runs pytest, ruff, and mypy sequentially.  Output is returned as-is
    for Claude to interpret — no pass/fail logic is applied here.

    Args:
        project_path: Project root directory.

    Returns:
        Dict with keys ``pytest``, ``ruff``, ``mypy`` mapping to raw output.
    """
    _print_step("Running verification suite (pytest, ruff, mypy)...")

    results: dict[str, str] = {}

    _print_step("  pytest...")
    results["pytest"] = _run_pytest_raw(project_path)

    _print_step("  ruff...")
    results["ruff"] = _run_ruff_raw(project_path)

    _print_step("  mypy...")
    results["mypy"] = _run_mypy_raw(project_path)

    # Log a summary line for console visibility.
    for tool, output in results.items():
        lines = output.strip().splitlines()
        last = lines[-1] if lines else "(no output)"
        if "error" in last.lower() or "failed" in last.lower():
            _print_warn(f"  {tool}: {last}")

    return results
