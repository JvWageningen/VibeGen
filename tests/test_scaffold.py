"""Tests for vibegen._scaffold module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from vibegen._scaffold import (
    _copy_docs,
    _create_vscode_settings,
    _ensure_directory,
    _ensure_package_dir,
    _generate_readme,
    _init_git,
    _update_pyproject_tools,
    _write_claude_md,
    _write_gitattributes,
    _write_gitignore,
    _write_pre_commit_config,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def minimal_spec() -> dict:
    return {
        "project_name": "MyTool",
        "python_version": "3.12",
        "dependencies": ["requests"],
        "description": "A handy CLI tool.",
        "usage": "Run `mytool --help`",
        "raw": "## Name\nMyTool\n## Description\nA handy CLI tool.\n",
        "doc_files": [],
    }


# ---------------------------------------------------------------------------
# _ensure_directory
# ---------------------------------------------------------------------------


def test_ensure_directory_creates_directory(tmp_path: Path) -> None:
    new_dir = tmp_path / "sub" / "dir"
    _ensure_directory(new_dir)
    assert new_dir.is_dir()


def test_ensure_directory_no_error_if_exists(tmp_path: Path) -> None:
    existing = tmp_path / "existing"
    existing.mkdir()
    _ensure_directory(existing)  # Should not raise
    assert existing.is_dir()


def test_ensure_directory_nested(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b" / "c"
    _ensure_directory(deep)
    assert deep.is_dir()


# ---------------------------------------------------------------------------
# _write_claude_md
# ---------------------------------------------------------------------------


def test_write_claude_md_creates_file(tmp_path: Path, minimal_spec: dict) -> None:
    _write_claude_md(tmp_path, minimal_spec)
    assert (tmp_path / "CLAUDE.md").exists()


def test_write_claude_md_contains_project_name(
    tmp_path: Path, minimal_spec: dict
) -> None:
    _write_claude_md(tmp_path, minimal_spec)
    content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "MyTool" in content


def test_write_claude_md_contains_python_version(
    tmp_path: Path, minimal_spec: dict
) -> None:
    _write_claude_md(tmp_path, minimal_spec)
    content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "3.12" in content


def test_write_claude_md_uses_description(tmp_path: Path, minimal_spec: dict) -> None:
    _write_claude_md(tmp_path, minimal_spec)
    content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "handy CLI tool" in content


def test_write_claude_md_fallback_description_from_raw(tmp_path: Path) -> None:
    spec = {
        "project_name": "FallbackTool",
        "python_version": "3.11",
        "dependencies": [],
        "description": "",
        "usage": "",
        "raw": "## Description\nFallback description here.\n",
        "doc_files": [],
    }
    _write_claude_md(tmp_path, spec)
    content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Fallback description here" in content


def test_write_claude_md_snake_case_package_name(
    tmp_path: Path, minimal_spec: dict
) -> None:
    minimal_spec["project_name"] = "My-Cool-Tool"
    _write_claude_md(tmp_path, minimal_spec)
    content = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "my_cool_tool" in content


# ---------------------------------------------------------------------------
# _create_vscode_settings
# ---------------------------------------------------------------------------


def test_create_vscode_settings_creates_file(tmp_path: Path) -> None:
    _create_vscode_settings(tmp_path)
    assert (tmp_path / ".vscode" / "settings.json").exists()


def test_create_vscode_settings_valid_json(tmp_path: Path) -> None:
    _create_vscode_settings(tmp_path)
    content = (tmp_path / ".vscode" / "settings.json").read_text(encoding="utf-8")
    parsed = json.loads(content)
    assert isinstance(parsed, dict)


def test_create_vscode_settings_has_ruff_formatter(tmp_path: Path) -> None:
    _create_vscode_settings(tmp_path)
    content = (tmp_path / ".vscode" / "settings.json").read_text(encoding="utf-8")
    assert "ruff" in content.lower()


# ---------------------------------------------------------------------------
# _write_gitignore
# ---------------------------------------------------------------------------


def test_write_gitignore_creates_file(tmp_path: Path) -> None:
    _write_gitignore(tmp_path)
    assert (tmp_path / ".gitignore").exists()


def test_write_gitignore_contains_venv(tmp_path: Path) -> None:
    _write_gitignore(tmp_path)
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".venv/" in content


def test_write_gitignore_contains_pycache(tmp_path: Path) -> None:
    _write_gitignore(tmp_path)
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "__pycache__" in content


# ---------------------------------------------------------------------------
# _write_gitattributes
# ---------------------------------------------------------------------------


def test_write_gitattributes_creates_file(tmp_path: Path) -> None:
    _write_gitattributes(tmp_path)
    assert (tmp_path / ".gitattributes").exists()


def test_write_gitattributes_enforces_lf(tmp_path: Path) -> None:
    _write_gitattributes(tmp_path)
    content = (tmp_path / ".gitattributes").read_text(encoding="utf-8")
    assert "eol=lf" in content


# ---------------------------------------------------------------------------
# _write_pre_commit_config
# ---------------------------------------------------------------------------


def test_write_pre_commit_config_creates_file(tmp_path: Path) -> None:
    _write_pre_commit_config(tmp_path)
    assert (tmp_path / ".pre-commit-config.yaml").exists()


def test_write_pre_commit_config_contains_ruff(tmp_path: Path) -> None:
    _write_pre_commit_config(tmp_path)
    content = (tmp_path / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "ruff" in content


def test_write_pre_commit_config_contains_bandit(tmp_path: Path) -> None:
    _write_pre_commit_config(tmp_path)
    content = (tmp_path / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    assert "bandit" in content


# ---------------------------------------------------------------------------
# _ensure_package_dir
# ---------------------------------------------------------------------------


def test_ensure_package_dir_creates_src_pkg(tmp_path: Path) -> None:
    result = _ensure_package_dir(tmp_path, "mypkg")
    assert result.is_dir()
    assert result == tmp_path / "src" / "mypkg"


def test_ensure_package_dir_creates_init_py(tmp_path: Path) -> None:
    _ensure_package_dir(tmp_path, "mypkg")
    assert (tmp_path / "src" / "mypkg" / "__init__.py").exists()


def test_ensure_package_dir_does_not_overwrite_existing_init(tmp_path: Path) -> None:
    pkg = tmp_path / "src" / "mypkg"
    pkg.mkdir(parents=True)
    init = pkg / "__init__.py"
    init.write_text("# existing", encoding="utf-8")
    _ensure_package_dir(tmp_path, "mypkg")
    # Should not overwrite
    assert init.read_text(encoding="utf-8") == "# existing"


# ---------------------------------------------------------------------------
# _update_pyproject_tools
# ---------------------------------------------------------------------------


def test_update_pyproject_tools_no_file_is_noop(tmp_path: Path) -> None:
    _update_pyproject_tools(tmp_path)  # Should not raise


def test_update_pyproject_tools_appends_ruff_config(tmp_path: Path) -> None:
    toml = tmp_path / "pyproject.toml"
    toml.write_text("[project]\nname = 'foo'\n", encoding="utf-8")
    _update_pyproject_tools(tmp_path)
    content = toml.read_text(encoding="utf-8")
    assert "[tool.ruff]" in content


def test_update_pyproject_tools_skips_if_already_configured(
    tmp_path: Path,
) -> None:
    toml = tmp_path / "pyproject.toml"
    original = "[project]\nname = 'foo'\n[tool.ruff]\nline-length = 100\n"
    toml.write_text(original, encoding="utf-8")
    _update_pyproject_tools(tmp_path)
    content = toml.read_text(encoding="utf-8")
    # Should not duplicate [tool.ruff]
    assert content.count("[tool.ruff]") == 1


def test_update_pyproject_tools_adds_pytest_config(tmp_path: Path) -> None:
    toml = tmp_path / "pyproject.toml"
    toml.write_text("[project]\nname = 'foo'\n", encoding="utf-8")
    _update_pyproject_tools(tmp_path)
    content = toml.read_text(encoding="utf-8")
    assert "[tool.pytest.ini_options]" in content


# ---------------------------------------------------------------------------
# _init_git
# ---------------------------------------------------------------------------


def test_init_git_calls_git_init(tmp_path: Path) -> None:
    with patch("vibegen._scaffold._run_cmd") as mock_run:
        _init_git(tmp_path)
    calls = [c[0][0] for c in mock_run.call_args_list]
    assert any("git" in cmd and "init" in cmd for cmd in calls)


def test_init_git_calls_git_commit(tmp_path: Path) -> None:
    with patch("vibegen._scaffold._run_cmd") as mock_run:
        _init_git(tmp_path)
    calls = [c[0][0] for c in mock_run.call_args_list]
    assert any("commit" in cmd for cmd in calls)


def test_init_git_does_not_raise_on_exception(tmp_path: Path) -> None:
    with patch("vibegen._scaffold._run_cmd", side_effect=RuntimeError("git not found")):
        # Should silently handle the exception
        _init_git(tmp_path)


# ---------------------------------------------------------------------------
# _copy_docs
# ---------------------------------------------------------------------------


def test_copy_docs_empty_list_is_noop(tmp_path: Path) -> None:
    spec_path = tmp_path / "spec.md"
    spec_path.write_text("", encoding="utf-8")
    _copy_docs(tmp_path, spec_path, [])
    assert not (tmp_path / "docs").exists()


def test_copy_docs_copies_existing_file(tmp_path: Path) -> None:
    spec_dir = tmp_path / "specs"
    spec_dir.mkdir()
    spec_path = spec_dir / "spec.md"
    spec_path.write_text("", encoding="utf-8")
    docs_src = spec_dir / "docs"
    docs_src.mkdir()
    doc_file = docs_src / "api.md"
    doc_file.write_text("# API Docs", encoding="utf-8")

    _copy_docs(tmp_path, spec_path, ["docs/api.md"])
    assert (tmp_path / "docs" / "api.md").exists()
    assert "API Docs" in (tmp_path / "docs" / "api.md").read_text(encoding="utf-8")


def test_copy_docs_warns_missing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    spec_path = tmp_path / "spec.md"
    spec_path.write_text("", encoding="utf-8")
    _copy_docs(tmp_path, spec_path, ["docs/missing.md"])
    captured = capsys.readouterr()
    assert "not found" in captured.out or "WARN" in captured.out


# ---------------------------------------------------------------------------
# _generate_readme
# ---------------------------------------------------------------------------


def test_generate_readme_creates_file(tmp_path: Path, minimal_spec: dict) -> None:
    _generate_readme(tmp_path, minimal_spec, "mytool")
    assert (tmp_path / "README.md").exists()


def test_generate_readme_contains_project_name(
    tmp_path: Path, minimal_spec: dict
) -> None:
    _generate_readme(tmp_path, minimal_spec, "mytool")
    content = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "MyTool" in content


def test_generate_readme_contains_description(
    tmp_path: Path, minimal_spec: dict
) -> None:
    _generate_readme(tmp_path, minimal_spec, "mytool")
    content = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "handy CLI tool" in content


def test_generate_readme_contains_usage(tmp_path: Path, minimal_spec: dict) -> None:
    _generate_readme(tmp_path, minimal_spec, "mytool")
    content = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "mytool" in content


def test_generate_readme_lists_py_files(tmp_path: Path, minimal_spec: dict) -> None:
    src = tmp_path / "src" / "mytool"
    src.mkdir(parents=True)
    (src / "core.py").write_text("", encoding="utf-8")
    _generate_readme(tmp_path, minimal_spec, "mytool")
    content = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "core.py" in content


def test_generate_readme_no_src_dir(tmp_path: Path, minimal_spec: dict) -> None:
    _generate_readme(tmp_path, minimal_spec, "mytool")
    content = (tmp_path / "README.md").read_text(encoding="utf-8")
    # Falls back to placeholder
    assert "generated source files" in content
