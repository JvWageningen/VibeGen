"""Persistent state management for the iterative improvement loop."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

_IMPROVE_DIR = ".vibegen/improve"
_STATE_FILE = f"{_IMPROVE_DIR}/state.json"
_CHANGELOG_FILE = f"{_IMPROVE_DIR}/CHANGELOG.md"
_LOGS_DIR = f"{_IMPROVE_DIR}/logs"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class IterationRecord:
    """Single iteration history entry.

    Attributes:
        iteration: Iteration number.
        verdict: Claude's evaluation (``improvement``, ``neutral``, ``regression``).
        verdict_reasoning: Claude's one-line explanation.
        changes_summary: What changed this iteration.
        commit_sha: Git commit hash (empty if not committed).
        reverted: Whether this iteration was later reverted.
        test_output: Raw pytest output (truncated for storage).
        lint_output: Raw ruff output (truncated).
        type_output: Raw mypy output (truncated).
        timestamp: ISO-8601 timestamp.
    """

    iteration: int = 0
    verdict: str = ""
    verdict_reasoning: str = ""
    changes_summary: str = ""
    commit_sha: str = ""
    reverted: bool = False
    test_output: str = ""
    lint_output: str = ""
    type_output: str = ""
    timestamp: str = ""


@dataclass
class ImproveState:
    """Full state of an improvement loop run.

    Attributes:
        iteration: Current iteration number.
        max_iterations: Maximum iterations (0 = unlimited, stall detection stops).
        status: Loop status (``idle``, ``running``, ``paused``, ``done``, ``error``).
        mode: Execution mode (``direct`` or ``polling``).
        task: User-provided improvement task description.
        branch_name: Git branch for improvements.
        base_branch: Original branch to merge back to.
        history: List of past iteration records.
        notes_for_claude: User-provided hints for next iteration.
        failed_changes: Changes that caused regressions (Claude should avoid).
        best_iteration: Iteration number with the best result so far.
        consecutive_regressions: Count of consecutive regression verdicts.
        consecutive_stalls: Count of consecutive neutral verdicts.
        claude_session_id: Persistent Claude session ID for context continuity.
        started_at: ISO-8601 timestamp of loop start.
        project_path: Absolute path to the project being improved.
        poll_flag_path: Flag file path for polling mode.
        poll_interval: Seconds between polls in polling mode.
    """

    iteration: int = 0
    max_iterations: int = 0
    status: str = "idle"
    mode: str = "direct"
    task: str = ""
    branch_name: str = ""
    base_branch: str = ""
    history: list[IterationRecord] = field(default_factory=list)
    notes_for_claude: list[str] = field(default_factory=list)
    failed_changes: list[dict[str, str]] = field(default_factory=list)
    best_iteration: int = 0
    consecutive_regressions: int = 0
    consecutive_stalls: int = 0
    claude_session_id: str = ""
    started_at: str = ""
    project_path: str = ""
    poll_flag_path: str = ""
    poll_interval: int = 60


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------


def _ensure_improve_dirs(project_path: Path) -> None:
    """Create the ``.vibegen/improve/logs/`` directory tree if absent.

    Args:
        project_path: Project root directory.
    """
    (project_path / _LOGS_DIR).mkdir(parents=True, exist_ok=True)


def _load_improve_state(project_path: Path) -> ImproveState:
    """Load improvement state from disk, returning defaults if absent.

    Args:
        project_path: Project root directory.

    Returns:
        Loaded or default ``ImproveState``.
    """
    state_path = project_path / _STATE_FILE
    if not state_path.exists():
        return ImproveState(project_path=str(project_path))

    raw = json.loads(state_path.read_text(encoding="utf-8"))

    # Reconstruct history records from dicts.
    history = [IterationRecord(**rec) for rec in raw.pop("history", [])]
    return ImproveState(**raw, history=history)


def _save_improve_state(project_path: Path, state: ImproveState) -> None:
    """Persist improvement state atomically (write-to-temp then rename).

    Args:
        project_path: Project root directory.
        state: State to persist.
    """
    _ensure_improve_dirs(project_path)
    state_path = project_path / _STATE_FILE
    data = asdict(state)
    payload = json.dumps(data, indent=2, ensure_ascii=False)

    # Atomic write: temp file in same dir, then rename.
    fd, tmp = tempfile.mkstemp(
        dir=str(state_path.parent), suffix=".tmp", prefix="state_"
    )
    try:
        os.write(fd, payload.encode("utf-8"))
        os.close(fd)
        os.replace(tmp, str(state_path))
    except BaseException:
        os.close(fd) if not os.get_inheritable(fd) else None  # noqa: BLE001
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ---------------------------------------------------------------------------
# Changelog & failed-change tracking
# ---------------------------------------------------------------------------


def _append_changelog(project_path: Path, iteration: int, entry: str) -> None:
    """Append an entry to the improvement CHANGELOG.

    Args:
        project_path: Project root directory.
        iteration: Iteration number.
        entry: Change description text.
    """
    _ensure_improve_dirs(project_path)
    changelog = project_path / _CHANGELOG_FILE
    ts = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M")
    line = f"- **Iter {iteration}** ({ts}): {entry}\n"

    if not changelog.exists():
        changelog.write_text("# Improvement Changelog\n\n" + line, encoding="utf-8")
    else:
        with changelog.open("a", encoding="utf-8") as fh:
            fh.write(line)


def _record_failed_change(
    project_path: Path,
    iteration: int,
    summary: str,
    reasoning: str,
) -> None:
    """Record a reverted change so Claude can avoid repeating it.

    Args:
        project_path: Project root directory.
        iteration: Iteration that was reverted.
        summary: What was changed.
        reasoning: Why it was considered a regression.
    """
    _ensure_improve_dirs(project_path)
    state = _load_improve_state(project_path)
    state.failed_changes.append(
        {
            "iteration": str(iteration),
            "change": summary,
            "reason": reasoning,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }
    )
    _save_improve_state(project_path, state)


def _save_iteration_log(project_path: Path, iteration: int, content: str) -> None:
    """Save per-iteration Claude log output.

    Args:
        project_path: Project root directory.
        iteration: Iteration number.
        content: Log content to write.
    """
    _ensure_improve_dirs(project_path)
    log_path = project_path / _LOGS_DIR / f"iter_{iteration}.txt"
    log_path.write_text(content, encoding="utf-8")


def _save_verdict(project_path: Path, iteration: int, verdict: dict[str, str]) -> None:
    """Save per-iteration verdict JSON.

    Args:
        project_path: Project root directory.
        iteration: Iteration number.
        verdict: Verdict dict with ``verdict`` and ``reasoning`` keys.
    """
    _ensure_improve_dirs(project_path)
    path = project_path / _LOGS_DIR / f"verdict_{iteration}.json"
    path.write_text(json.dumps(verdict, indent=2, ensure_ascii=False), encoding="utf-8")
