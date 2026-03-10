"""Docker sandbox for isolating generated-project commands."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_IMAGE = "ghcr.io/astral-sh/uv:python3.12-bookworm-slim"
_SANDBOX_READY: bool = False

# Commands that must always run on the host, never inside the container.
_HOST_ONLY_COMMANDS: frozenset[str] = frozenset({"claude", "docker", "git"})


@dataclass
class SandboxConfig:
    """Configuration for Docker-based sandbox execution.

    Args:
        project_path: Absolute path to the generated project directory.
        image: Docker image to use. Defaults to VIBEGEN_SANDBOX_IMAGE env var
            or the bundled uv image.
        enabled: Whether sandboxing is active.
    """

    project_path: Path
    image: str = field(
        default_factory=lambda: os.environ.get("VIBEGEN_SANDBOX_IMAGE", _DEFAULT_IMAGE)
    )
    enabled: bool = True

    def should_sandbox(self, args: list[str], cwd: Path | str | None) -> bool:
        """Return True when *args* should be executed inside the container.

        Args:
            args: Command-line arguments list (args[0] is the executable name).
            cwd: Working directory that would be used for the command.

        Returns:
            True if the command should be sandboxed, False otherwise.
        """
        if not self.enabled or not args:
            return False

        # Never sandbox host-only commands.
        executable = Path(args[0]).name.lower()
        if executable in _HOST_ONLY_COMMANDS:
            return False

        # Skip `uv init` — it runs in the parent directory before the project exists.
        if args[0] == "uv" and len(args) > 1 and args[1] == "init":
            return False

        # Only sandbox commands whose cwd is inside the project directory.
        if cwd is None:
            return False
        try:
            Path(cwd).resolve().relative_to(self.project_path.resolve())
            return True
        except ValueError:
            return False

    def build_docker_args(self, args: list[str]) -> list[str]:
        """Wrap *args* with `docker run` so they execute inside the sandbox.

        Args:
            args: Original command-line arguments.

        Returns:
            New argument list starting with `docker run ...`.
        """
        # Docker Desktop on Windows accepts forward-slash paths in -v.
        host_path = str(self.project_path.resolve()).replace("\\", "/")
        return [
            "docker",
            "run",
            "--rm",
            "--network",
            "bridge",
            "--add-host",
            "host.docker.internal:host-gateway",
            "-v",
            f"{host_path}:/workspace:rw",
            "-v",
            "uv-tools-cache:/root/.local/share/uv/tools",
            "-w",
            "/workspace",
            "-e",
            "HOME=/root",
            self.image,
            *args,
        ]


def ensure_image_ready(image: str) -> None:
    """Pull *image* if it is not already present locally.

    Args:
        image: Docker image reference to check/pull.

    Raises:
        SystemExit: If Docker is not running or the pull fails.
    """
    global _SANDBOX_READY  # noqa: PLW0603
    if _SANDBOX_READY:
        return

    try:
        result = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            print(f"[STEP]  Pulling sandbox image {image} (first run only)…")
            subprocess.run(["docker", "pull", image], check=True)
    except FileNotFoundError:
        raise SystemExit(
            "[ERR]   Docker is not installed or not on PATH. "
            "Install Docker Desktop and try again, or omit --sandbox."
        ) from None
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"[ERR]   Failed to pull Docker image '{image}': {exc}"
        ) from exc

    _SANDBOX_READY = True
