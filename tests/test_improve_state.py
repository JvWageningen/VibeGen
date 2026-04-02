"""Tests for vibegen._improve_state module."""

from __future__ import annotations

from pathlib import Path

from vibegen._improve_state import (
    ImproveState,
    IterationRecord,
    _append_changelog,
    _ensure_improve_dirs,
    _load_improve_state,
    _record_failed_change,
    _save_improve_state,
    _save_iteration_log,
    _save_verdict,
)

# ---------------------------------------------------------------------------
# ImproveState persistence
# ---------------------------------------------------------------------------


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    state = ImproveState(
        iteration=3,
        status="running",
        task="fix tests",
        project_path=str(tmp_path),
    )
    state.history.append(
        IterationRecord(
            iteration=1,
            verdict="improvement",
            verdict_reasoning="tests pass now",
            changes_summary="fixed import",
        )
    )
    _save_improve_state(tmp_path, state)
    loaded = _load_improve_state(tmp_path)
    assert loaded.iteration == 3
    assert loaded.status == "running"
    assert loaded.task == "fix tests"
    assert len(loaded.history) == 1
    assert loaded.history[0].verdict == "improvement"


def test_load_missing_returns_default(tmp_path: Path) -> None:
    state = _load_improve_state(tmp_path)
    assert state.iteration == 0
    assert state.status == "idle"


def test_save_creates_directories(tmp_path: Path) -> None:
    state = ImproveState(project_path=str(tmp_path))
    _save_improve_state(tmp_path, state)
    assert (tmp_path / ".vibegen" / "improve" / "state.json").exists()


# ---------------------------------------------------------------------------
# Changelog
# ---------------------------------------------------------------------------


def test_append_changelog_creates_file(tmp_path: Path) -> None:
    _append_changelog(tmp_path, 1, "fixed import order")
    changelog = tmp_path / ".vibegen" / "improve" / "CHANGELOG.md"
    assert changelog.exists()
    content = changelog.read_text(encoding="utf-8")
    assert "Iter 1" in content
    assert "fixed import order" in content


def test_append_changelog_appends(tmp_path: Path) -> None:
    _append_changelog(tmp_path, 1, "first change")
    _append_changelog(tmp_path, 2, "second change")
    content = (tmp_path / ".vibegen/improve/CHANGELOG.md").read_text(encoding="utf-8")
    assert "Iter 1" in content
    assert "Iter 2" in content


# ---------------------------------------------------------------------------
# Failed changes
# ---------------------------------------------------------------------------


def test_record_failed_change(tmp_path: Path) -> None:
    # Need initial state file for _record_failed_change to load.
    _save_improve_state(tmp_path, ImproveState(project_path=str(tmp_path)))
    _record_failed_change(tmp_path, 5, "removed caching", "caused 3 test failures")
    state = _load_improve_state(tmp_path)
    assert len(state.failed_changes) == 1
    assert state.failed_changes[0]["change"] == "removed caching"
    assert state.failed_changes[0]["reason"] == "caused 3 test failures"


# ---------------------------------------------------------------------------
# Iteration logs and verdicts
# ---------------------------------------------------------------------------


def test_save_iteration_log(tmp_path: Path) -> None:
    _ensure_improve_dirs(tmp_path)
    _save_iteration_log(tmp_path, 7, "Claude did some work here")
    log = tmp_path / ".vibegen/improve/logs/iter_7.txt"
    assert log.exists()
    assert "Claude did some work" in log.read_text(encoding="utf-8")


def test_save_verdict(tmp_path: Path) -> None:
    _ensure_improve_dirs(tmp_path)
    _save_verdict(tmp_path, 3, {"verdict": "improvement", "reasoning": "tests pass"})
    path = tmp_path / ".vibegen/improve/logs/verdict_3.json"
    assert path.exists()
    import json

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["verdict"] == "improvement"


# ---------------------------------------------------------------------------
# IterationRecord defaults
# ---------------------------------------------------------------------------


def test_iteration_record_defaults() -> None:
    rec = IterationRecord()
    assert rec.iteration == 0
    assert rec.verdict == ""
    assert rec.reverted is False
