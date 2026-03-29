"""Release script — bump version with SHA-256 manifests.

Usage:
    uv run python scripts/release.py major
    uv run python scripts/release.py minor
    uv run python scripts/release.py patch

Steps:
1. Read current version from pyproject.toml.
2. Bump the requested semantic version part (resets lower parts to 0).
3. Write new version to pyproject.toml, VERSION, and src/vibegen/__init__.py.
4. Compute SHA-256 checksums for all .py files in src/vibegen/.
5. Write manifest to versions/v<version>.json.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT: Path = Path(__file__).resolve().parents[1]
SRC: Path = ROOT / "src" / "vibegen"
VERSIONS_DIR: Path = ROOT / "versions"
VERSION_FILE: Path = ROOT / "VERSION"
PYPROJECT: Path = ROOT / "pyproject.toml"
INIT_FILE: Path = SRC / "__init__.py"

VALID_PARTS = {"major", "minor", "patch"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_git_commit() -> str:
    """Return the current HEAD commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _compute_checksums(src: Path) -> dict[str, str]:
    """Return a dict mapping relative path -> SHA-256 hex digest.

    Args:
        src: Root directory to scan for .py files.
    """
    checksums: dict[str, str] = {}
    for f in sorted(src.rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        rel = f.relative_to(src.parent)
        checksums[str(rel).replace("\\", "/")] = hashlib.sha256(
            f.read_bytes()
        ).hexdigest()
    return checksums


def _bump_version(current: str, part: str) -> str:
    """Increment one part of a semver string.

    Args:
        current: Current version string (e.g. ``"1.2.3"``).
        part: ``"major"``, ``"minor"``, or ``"patch"``.

    Returns:
        New version string with lower parts reset to 0.
    """
    major, minor, patch = (int(x) for x in current.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _read_current_version() -> str:
    """Read the current version from pyproject.toml.

    Returns:
        Version string from ``[project].version``.
    """
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]*)"', text, re.MULTILINE)
    if not match:
        msg = "No version found in pyproject.toml"
        raise ValueError(msg)
    return match.group(1)


def _update_pyproject(new_version: str) -> None:
    """Update the version in pyproject.toml.

    Args:
        new_version: New version string.
    """
    text = PYPROJECT.read_text(encoding="utf-8")
    text = re.sub(
        r'^version\s*=\s*"[^"]*"',
        f'version = "{new_version}"',
        text,
        flags=re.MULTILINE,
        count=1,
    )
    PYPROJECT.write_text(text, encoding="utf-8")


def _update_init(new_version: str) -> None:
    """Update __version__ in src/vibegen/__init__.py.

    Args:
        new_version: New version string.
    """
    text = INIT_FILE.read_text(encoding="utf-8")
    text = re.sub(
        r'__version__\s*=\s*"[^"]*"',
        f'__version__ = "{new_version}"',
        text,
    )
    INIT_FILE.write_text(text, encoding="utf-8")


def _write_manifest(
    version: str,
    checksums: dict[str, str],
) -> Path:
    """Write a versioned JSON manifest with checksums.

    Args:
        version: Version string for this release.
        checksums: File path to SHA-256 mapping.

    Returns:
        Path to the written manifest file.
    """
    VERSIONS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": version,
        "released_at": datetime.now(UTC).isoformat(),
        "git_commit": _get_git_commit(),
        "files": checksums,
    }
    out = VERSIONS_DIR / f"v{version}.json"
    out.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return out


# ---------------------------------------------------------------------------
# Bump
# ---------------------------------------------------------------------------


def bump(part: str) -> str:
    """Bump the version and generate a manifest.

    Args:
        part: ``"major"``, ``"minor"``, or ``"patch"``.

    Returns:
        The new version string.
    """
    current = _read_current_version()
    new_version = _bump_version(current, part)

    print(f"vibegen: {current} -> {new_version}")

    _update_pyproject(new_version)
    VERSION_FILE.write_text(new_version + "\n", encoding="utf-8")
    _update_init(new_version)

    checksums = _compute_checksums(SRC)
    manifest_path = _write_manifest(new_version, checksums)

    print(f"  Manifest : {manifest_path.relative_to(ROOT)}")
    print(f"  Files    : {len(checksums)}")
    return new_version


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point: parse args and bump version."""
    if len(sys.argv) != 2 or sys.argv[1] not in VALID_PARTS:
        print("Usage: python scripts/release.py [major|minor|patch]")
        sys.exit(1)

    part = sys.argv[1]
    new_version = bump(part)
    commit = _get_git_commit()
    print(f"Git commit : {commit[:12]}")
    print(f"Version    : {new_version}")


if __name__ == "__main__":
    main()
