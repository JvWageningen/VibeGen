"""Tests for .claude/hooks/read_once.py — mtime-based cache invalidation."""

from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path
from types import ModuleType
from unittest.mock import patch


def _load_hook() -> ModuleType:
    """Import read_once.py as a module without executing __main__."""
    hook_path = Path(__file__).parents[1] / ".claude" / "hooks" / "read_once.py"
    spec = importlib.util.spec_from_file_location("read_once", hook_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _call_hook(
    mod: ModuleType, file_path: str, offset: int = 0, limit: int = 0
) -> dict:
    """Invoke hook main() with a fake stdin and capture stdout."""
    import io

    payload = json.dumps(
        {"tool_input": {"file_path": file_path, "offset": offset, "limit": limit}}
    )
    with (
        patch("sys.stdin", io.StringIO(payload)),
        patch("sys.stdout", new_io := io.StringIO()),
    ):
        mod.main()
    return json.loads(new_io.getvalue())


def test_first_read_approved(tmp_path: Path) -> None:
    target = tmp_path / "hello.py"
    target.write_text("x = 1")
    state_file = str(tmp_path / "state.json")

    mod = _load_hook()
    with patch.object(mod, "STATE_FILE", state_file):
        result = _call_hook(mod, str(target))

    assert result["decision"] == "approve"


def test_second_read_blocked(tmp_path: Path) -> None:
    target = tmp_path / "hello.py"
    target.write_text("x = 1")
    state_file = str(tmp_path / "state.json")

    mod = _load_hook()
    with patch.object(mod, "STATE_FILE", state_file):
        _call_hook(mod, str(target))
        result = _call_hook(mod, str(target))

    assert result["decision"] == "block"


def test_mtime_invalidation_allows_reread(tmp_path: Path) -> None:
    target = tmp_path / "hello.py"
    target.write_text("x = 1")
    state_file = str(tmp_path / "state.json")

    mod = _load_hook()
    with patch.object(mod, "STATE_FILE", state_file):
        _call_hook(mod, str(target))

        # Ensure mtime is strictly newer than the stored timestamp
        time.sleep(0.05)
        target.write_text("x = 2")

        result = _call_hook(mod, str(target))

    assert result["decision"] == "approve"


def test_different_offsets_are_independent(tmp_path: Path) -> None:
    target = tmp_path / "hello.py"
    target.write_text("x = 1\ny = 2\n")
    state_file = str(tmp_path / "state.json")

    mod = _load_hook()
    with patch.object(mod, "STATE_FILE", state_file):
        r1 = _call_hook(mod, str(target), offset=0, limit=10)
        r2 = _call_hook(mod, str(target), offset=10, limit=10)
        r3 = _call_hook(mod, str(target), offset=0, limit=10)

    assert r1["decision"] == "approve"
    assert r2["decision"] == "approve"
    assert r3["decision"] == "block"


def test_deleted_file_is_invalidated(tmp_path: Path) -> None:
    target = tmp_path / "gone.py"
    target.write_text("x = 1")
    state_file = str(tmp_path / "state.json")

    mod = _load_hook()
    with patch.object(mod, "STATE_FILE", state_file):
        _call_hook(mod, str(target))
        target.unlink()
        result = _call_hook(mod, str(target))

    # Deleted file clears the cache entry; hook approves (file missing is OSError)
    assert result["decision"] == "approve"
