"""Tests for vibegen.sandbox module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from vibegen.sandbox import SandboxConfig, ensure_image_ready

# ---------------------------------------------------------------------------
# SandboxConfig.should_sandbox
# ---------------------------------------------------------------------------


@pytest.fixture()
def sandbox(tmp_path: Path) -> SandboxConfig:
    return SandboxConfig(project_path=tmp_path, enabled=True)


@pytest.fixture()
def disabled_sandbox(tmp_path: Path) -> SandboxConfig:
    return SandboxConfig(project_path=tmp_path, enabled=False)


def test_should_sandbox_disabled_returns_false(
    disabled_sandbox: SandboxConfig, tmp_path: Path
) -> None:
    subdir = tmp_path / "sub"
    subdir.mkdir()
    assert disabled_sandbox.should_sandbox(["uv", "run", "pytest"], subdir) is False


def test_should_sandbox_empty_args_returns_false(
    sandbox: SandboxConfig, tmp_path: Path
) -> None:
    assert sandbox.should_sandbox([], tmp_path) is False


def test_should_sandbox_host_only_claude(
    sandbox: SandboxConfig, tmp_path: Path
) -> None:
    assert sandbox.should_sandbox(["claude", "--version"], tmp_path) is False


def test_should_sandbox_host_only_docker(
    sandbox: SandboxConfig, tmp_path: Path
) -> None:
    assert sandbox.should_sandbox(["docker", "ps"], tmp_path) is False


def test_should_sandbox_host_only_git(sandbox: SandboxConfig, tmp_path: Path) -> None:
    assert sandbox.should_sandbox(["git", "status"], tmp_path) is False


def test_should_sandbox_uv_init_skipped(sandbox: SandboxConfig, tmp_path: Path) -> None:
    assert sandbox.should_sandbox(["uv", "init", "myproject"], tmp_path) is False


def test_should_sandbox_cwd_none_returns_false(sandbox: SandboxConfig) -> None:
    assert sandbox.should_sandbox(["uv", "run", "pytest"], None) is False


def test_should_sandbox_cwd_outside_project(
    sandbox: SandboxConfig, tmp_path: Path
) -> None:
    outside = tmp_path.parent
    assert sandbox.should_sandbox(["uv", "run", "pytest"], outside) is False


def test_should_sandbox_cwd_inside_project(
    sandbox: SandboxConfig, tmp_path: Path
) -> None:
    subdir = tmp_path / "src"
    subdir.mkdir()
    assert sandbox.should_sandbox(["uv", "run", "pytest"], subdir) is True


def test_should_sandbox_cwd_is_project_root(
    sandbox: SandboxConfig, tmp_path: Path
) -> None:
    assert sandbox.should_sandbox(["uv", "run", "pytest"], tmp_path) is True


def test_should_sandbox_case_insensitive_executable(
    sandbox: SandboxConfig, tmp_path: Path
) -> None:
    subdir = tmp_path / "x"
    subdir.mkdir()
    # CLAUDE in upper-case should still be treated as host-only
    assert sandbox.should_sandbox(["CLAUDE", "--version"], subdir) is False


# ---------------------------------------------------------------------------
# SandboxConfig.build_docker_args
# ---------------------------------------------------------------------------


def test_build_docker_args_starts_with_docker_run(
    sandbox: SandboxConfig, tmp_path: Path
) -> None:
    result = sandbox.build_docker_args(["uv", "run", "pytest"])
    assert result[0] == "docker"
    assert result[1] == "run"


def test_build_docker_args_contains_rm_flag(sandbox: SandboxConfig) -> None:
    result = sandbox.build_docker_args(["uv", "run", "pytest"])
    assert "--rm" in result


def test_build_docker_args_mounts_workspace(
    sandbox: SandboxConfig, tmp_path: Path
) -> None:
    result = sandbox.build_docker_args(["uv", "run", "pytest"])
    combined = " ".join(result)
    assert "/workspace" in combined


def test_build_docker_args_ends_with_original_command(
    sandbox: SandboxConfig,
) -> None:
    original = ["uv", "run", "pytest", "-x"]
    result = sandbox.build_docker_args(original)
    assert result[-4:] == original


def test_build_docker_args_includes_image(
    sandbox: SandboxConfig,
) -> None:
    result = sandbox.build_docker_args(["uv"])
    assert sandbox.image in result


def test_build_docker_args_network_bridge(sandbox: SandboxConfig) -> None:
    result = sandbox.build_docker_args(["uv"])
    assert "bridge" in result


def test_sandbox_default_image_from_env(tmp_path: Path) -> None:
    with patch.dict("os.environ", {"VIBEGEN_SANDBOX_IMAGE": "custom/image:tag"}):
        cfg = SandboxConfig(project_path=tmp_path)
    assert cfg.image == "custom/image:tag"


def test_sandbox_custom_image(tmp_path: Path) -> None:
    cfg = SandboxConfig(project_path=tmp_path, image="my/image:latest")
    assert cfg.image == "my/image:latest"


# ---------------------------------------------------------------------------
# ensure_image_ready
# ---------------------------------------------------------------------------


def test_ensure_image_ready_image_already_present() -> None:
    import vibegen.sandbox as _sandbox_mod

    _sandbox_mod._SANDBOX_READY = False
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        ensure_image_ready("some/image:tag")
        # Should only call inspect, not pull
        assert mock_run.call_count == 1
    _sandbox_mod._SANDBOX_READY = False


def test_ensure_image_ready_pulls_when_missing() -> None:
    import vibegen.sandbox as _sandbox_mod

    _sandbox_mod._SANDBOX_READY = False
    inspect_result = MagicMock(returncode=1)
    pull_result = MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=[inspect_result, pull_result]) as mock_run:
        ensure_image_ready("some/image:tag")
        assert mock_run.call_count == 2
    _sandbox_mod._SANDBOX_READY = False


def test_ensure_image_ready_skips_when_already_ready() -> None:
    import vibegen.sandbox as _sandbox_mod

    _sandbox_mod._SANDBOX_READY = True
    with patch("subprocess.run") as mock_run:
        ensure_image_ready("any/image")
        mock_run.assert_not_called()
    _sandbox_mod._SANDBOX_READY = False


def test_ensure_image_ready_raises_system_exit_no_docker() -> None:
    import vibegen.sandbox as _sandbox_mod

    _sandbox_mod._SANDBOX_READY = False
    with (
        patch("subprocess.run", side_effect=FileNotFoundError),
        pytest.raises(SystemExit),
    ):
        ensure_image_ready("some/image:tag")
    _sandbox_mod._SANDBOX_READY = False


def test_ensure_image_ready_raises_system_exit_on_pull_failure() -> None:
    import subprocess

    import vibegen.sandbox as _sandbox_mod

    _sandbox_mod._SANDBOX_READY = False
    inspect_result = MagicMock(returncode=1)

    with (
        patch(
            "subprocess.run",
            side_effect=[
                inspect_result,
                subprocess.CalledProcessError(1, "docker pull"),
            ],
        ),
        pytest.raises(SystemExit),
    ):
        ensure_image_ready("bad/image:tag")
    _sandbox_mod._SANDBOX_READY = False
