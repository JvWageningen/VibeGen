"""Tests for vibegen._improve_webui module."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

from vibegen._improve_state import ImproveState, IterationRecord, _save_improve_state
from vibegen._improve_webui import _start_webui, _stop_webui


@pytest.fixture()
def webui_server(tmp_path: Path) -> any:
    """Start a webui server with test state and yield it."""
    state = ImproveState(
        iteration=2,
        status="running",
        task="improve tests",
        branch_name="vibegen/improve-test",
        base_branch="main",
        project_path=str(tmp_path),
        history=[
            IterationRecord(
                iteration=1,
                verdict="improvement",
                verdict_reasoning="tests pass",
                changes_summary="fixed import",
                commit_sha="abc1234",
                timestamp="2026-03-29T10:00:00",
            ),
            IterationRecord(
                iteration=2,
                verdict="neutral",
                verdict_reasoning="no change in metrics",
                changes_summary="refactored helper",
                commit_sha="def5678",
                timestamp="2026-03-29T10:30:00",
            ),
        ],
    )
    _save_improve_state(tmp_path, state)
    server = _start_webui(tmp_path, 0)  # Port 0 = OS picks available port
    port = server.server_address[1]
    yield {"server": server, "port": port, "path": tmp_path}
    _stop_webui(server)


def _get(port: int, path: str) -> dict:
    url = f"http://localhost:{port}{path}"
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read())


def _post(port: int, path: str, data: dict) -> dict:
    url = f"http://localhost:{port}{path}"
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# GET endpoints
# ---------------------------------------------------------------------------


def test_root_returns_html(webui_server: dict) -> None:
    port = webui_server["port"]
    url = f"http://localhost:{port}/"
    with urllib.request.urlopen(url, timeout=5) as resp:
        body = resp.read().decode("utf-8")
    assert "<title>VibeGen Improve Dashboard</title>" in body


def test_api_status(webui_server: dict) -> None:
    data = _get(webui_server["port"], "/api/status")
    assert data["iteration"] == 2
    assert data["status"] == "running"
    assert data["task"] == "improve tests"
    assert data["branch_name"] == "vibegen/improve-test"


def test_api_history(webui_server: dict) -> None:
    data = _get(webui_server["port"], "/api/history")
    assert len(data["history"]) == 2
    assert data["history"][0]["verdict"] == "improvement"
    assert data["history"][1]["verdict"] == "neutral"


def test_api_logs_changelog(webui_server: dict) -> None:
    # No changelog file exists yet — should return empty content.
    data = _get(webui_server["port"], "/api/logs?iter=changelog")
    assert "content" in data


# ---------------------------------------------------------------------------
# POST endpoints
# ---------------------------------------------------------------------------


def test_api_note(webui_server: dict) -> None:
    port = webui_server["port"]
    result = _post(port, "/api/note", {"text": "focus on edge cases"})
    assert result.get("ok") is True

    _get(port, "/api/status")
    # Note doesn't show in status, but state file should have it.
    from vibegen._improve_state import _load_improve_state

    loaded = _load_improve_state(webui_server["path"])
    assert "focus on edge cases" in loaded.notes_for_claude


def test_api_action_pause(webui_server: dict) -> None:
    port = webui_server["port"]
    result = _post(port, "/api/action", {"action": "pause"})
    assert result.get("status") == "paused"

    from vibegen._improve_state import _load_improve_state

    loaded = _load_improve_state(webui_server["path"])
    assert loaded.status == "paused"


def test_api_task_update(webui_server: dict) -> None:
    port = webui_server["port"]
    result = _post(port, "/api/task", {"task": "new task"})
    assert result.get("ok") is True

    from vibegen._improve_state import _load_improve_state

    loaded = _load_improve_state(webui_server["path"])
    assert loaded.task == "new task"


def test_api_note_empty_rejected(webui_server: dict) -> None:
    port = webui_server["port"]
    try:
        _post(port, "/api/note", {"text": ""})
    except urllib.error.HTTPError as e:
        assert e.code == 400
