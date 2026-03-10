"""Persistent session state for vibegen projects.

Saves a JSON manifest inside the generated project so that a ``--resume`` run
can skip scaffold/generate and jump straight to the fix loop when the spec has
not changed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_SESSION_FILE = ".vibegen/session.json"


@dataclass
class Session:
    """Persistent state for a single vibegen generation run.

    Attributes:
        spec_hash: SHA-256 hex digest of the spec file contents.
        project_name: Human-readable project name from the spec.
        package_name: Python package name (snake_case).
        model_provider: LLM provider used (``"claude"`` or ``"ollama"``).
        model: Model identifier string.
        attempts: Number of test-fix cycles completed.
        last_status: Last known pipeline status.
        generated_files: Relative paths of all LLM-generated files.
        timestamp: ISO-8601 timestamp of the last save.
    """

    spec_hash: str
    project_name: str
    package_name: str
    model_provider: str
    model: str
    attempts: int = 0
    last_status: str = "scaffold"
    generated_files: list[str] = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


def hash_spec(spec_path: Path) -> str:
    """Return the SHA-256 hex digest of a spec file.

    Args:
        spec_path: Path to the spec ``.md`` file.

    Returns:
        Hex digest string.
    """
    content = spec_path.read_bytes()
    return hashlib.sha256(content).hexdigest()


def save_session(project_path: Path, session: Session) -> None:
    """Write *session* to ``<project_path>/.vibegen/session.json``.

    Args:
        project_path: Project root directory.
        session: Session data to persist.
    """
    session_dir = project_path / ".vibegen"
    session_dir.mkdir(exist_ok=True)
    session_file = project_path / _SESSION_FILE
    data = asdict(session)
    data["timestamp"] = datetime.now(timezone.utc).isoformat()
    session_file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_session(project_path: Path) -> Session | None:
    """Load the session manifest from *project_path* if it exists.

    Args:
        project_path: Project root directory.

    Returns:
        Loaded Session, or None if no session file is present or it is corrupt.
    """
    session_file = project_path / _SESSION_FILE
    if not session_file.exists():
        return None
    try:
        data = json.loads(session_file.read_text(encoding="utf-8"))
        return Session(**data)
    except Exception:  # noqa: BLE001
        return None


def spec_changed(project_path: Path, spec_path: Path) -> bool:
    """Return True if the spec has changed since the last saved session.

    Args:
        project_path: Project root directory.
        spec_path: Path to the current spec file.

    Returns:
        True when the spec hash differs from the saved session (or no session).
    """
    session = load_session(project_path)
    if session is None:
        return True
    return session.spec_hash != hash_spec(spec_path)
