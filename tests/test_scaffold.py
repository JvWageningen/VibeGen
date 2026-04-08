"""Tests for vibegen._scaffold module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from vibegen._scaffold import (
    _copy_claude_commands,
    _copy_docs,
    _create_vscode_settings,
    _ensure_directory,
    _ensure_package_dir,
    _generate_readme,
    _init_git,
    _update_pyproject_tools,
    _write_ci_workflow,
    _write_claude_hooks,
    _write_claude_md,
    _write_claude_settings,
    _write_claudeignore,
    _write_conftest,
    _write_gitattributes,
    _write_gitignore,
    _write_mcp_config,
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


def test_write_gitignore_excludes_fuse_hidden(tmp_path: Path) -> None:
    _write_gitignore(tmp_path)
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".claude/.fuse_hidden*" in content


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


# ---------------------------------------------------------------------------
# _write_claude_settings
# ---------------------------------------------------------------------------


def test_write_claude_settings_creates_file(tmp_path: Path) -> None:
    _write_claude_settings(tmp_path)
    settings_file = tmp_path / ".claude" / "settings.local.json"
    assert settings_file.exists()


def test_write_claude_settings_valid_json(tmp_path: Path) -> None:
    _write_claude_settings(tmp_path)
    settings_file = tmp_path / ".claude" / "settings.json"
    data = json.loads(settings_file.read_text(encoding="utf-8"))
    assert "permissions" in data


def test_write_claude_settings_has_deny_rules(tmp_path: Path) -> None:
    _write_claude_settings(tmp_path)
    settings_file = tmp_path / ".claude" / "settings.json"
    data = json.loads(settings_file.read_text(encoding="utf-8"))
    deny = data["permissions"]["deny"]
    assert "Bash(shutdown *)" in deny
    assert "Bash(mkfs *)" in deny


def test_write_claude_settings_has_ask_rules(tmp_path: Path) -> None:
    _write_claude_settings(tmp_path)
    settings_file = tmp_path / ".claude" / "settings.json"
    data = json.loads(settings_file.read_text(encoding="utf-8"))
    ask = data["permissions"]["ask"]
    assert "Bash(rm -rf /)" in ask
    assert "Bash(rm *)" in ask
    assert "Bash(git reset *)" in ask


def test_write_claude_settings_creates_shared_settings_json(tmp_path: Path) -> None:
    _write_claude_settings(tmp_path)
    assert (tmp_path / ".claude" / "settings.json").exists()


def test_write_claude_settings_shared_has_autocompact_env(tmp_path: Path) -> None:
    _write_claude_settings(tmp_path)
    data = json.loads(
        (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert data["env"]["CLAUDE_AUTOCOMPACT_PCT_OVERRIDE"] == "50"


def test_write_claude_settings_shared_has_pretooluse_hook(tmp_path: Path) -> None:
    _write_claude_settings(tmp_path)
    data = json.loads(
        (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    pre = data["hooks"]["PreToolUse"]
    matchers = [h["matcher"] for h in pre]
    assert "Read" in matchers


def test_write_claude_settings_shared_has_posttooluse_hook(tmp_path: Path) -> None:
    _write_claude_settings(tmp_path)
    data = json.loads(
        (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    post = data["hooks"]["PostToolUse"]
    matchers = [h["matcher"] for h in post]
    assert "Bash" in matchers


def test_write_claude_settings_shared_has_model(tmp_path: Path) -> None:
    _write_claude_settings(tmp_path)
    data = json.loads(
        (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert "model" in data


def test_write_claude_settings_default_effort_has_sonnet_subagent(
    tmp_path: Path,
) -> None:
    _write_claude_settings(tmp_path)
    data = json.loads(
        (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert data["env"]["MAX_THINKING_TOKENS"] == "128000"
    assert data["env"]["CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING"] == "1"
    assert data["env"]["CLAUDE_CODE_SUBAGENT_MODEL"] == "claude-sonnet-4-6"
    assert data["model"] == "opusplan"


def test_write_claude_settings_max_effort_no_subagent(tmp_path: Path) -> None:
    _write_claude_settings(tmp_path, effort="max")
    data = json.loads(
        (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert "CLAUDE_CODE_SUBAGENT_MODEL" not in data["env"]
    assert data["env"]["MAX_THINKING_TOKENS"] == "128000"
    assert data["model"] == "opusplan"


def test_write_claude_settings_min_effort_has_haiku_subagent(tmp_path: Path) -> None:
    _write_claude_settings(tmp_path, effort="min")
    data = json.loads(
        (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert data["env"]["CLAUDE_CODE_SUBAGENT_MODEL"] == "claude-haiku-4-5-20251001"
    assert data["model"] == "sonnet"


# ---------------------------------------------------------------------------
# _write_claude_hooks
# ---------------------------------------------------------------------------


def test_write_claude_hooks_creates_file(tmp_path: Path) -> None:
    _write_claude_hooks(tmp_path)
    assert (tmp_path / ".claude" / "hooks" / "read_once.py").exists()


def test_write_claude_hooks_is_valid_python(tmp_path: Path) -> None:
    _write_claude_hooks(tmp_path)
    content = (tmp_path / ".claude" / "hooks" / "read_once.py").read_text(
        encoding="utf-8"
    )
    compile(content, "read_once.py", "exec")  # raises SyntaxError if invalid


def test_write_claude_hooks_blocks_redundant_reads(tmp_path: Path) -> None:
    _write_claude_hooks(tmp_path)
    content = (tmp_path / ".claude" / "hooks" / "read_once.py").read_text(
        encoding="utf-8"
    )
    assert "decision" in content
    assert "block" in content
    assert "approve" in content


def test_write_claude_hooks_tracks_offset_and_limit(tmp_path: Path) -> None:
    _write_claude_hooks(tmp_path)
    content = (tmp_path / ".claude" / "hooks" / "read_once.py").read_text(
        encoding="utf-8"
    )
    assert "offset" in content
    assert "limit" in content


def test_write_claude_hooks_creates_auto_lint(tmp_path: Path) -> None:
    _write_claude_hooks(tmp_path)
    assert (tmp_path / ".claude" / "hooks" / "auto_lint.py").exists()


def test_write_claude_hooks_auto_lint_is_valid_python(tmp_path: Path) -> None:
    _write_claude_hooks(tmp_path)
    content = (tmp_path / ".claude" / "hooks" / "auto_lint.py").read_text(
        encoding="utf-8"
    )
    compile(content, "auto_lint.py", "exec")  # raises SyntaxError if invalid


def test_write_claude_hooks_auto_lint_runs_ruff(tmp_path: Path) -> None:
    _write_claude_hooks(tmp_path)
    content = (tmp_path / ".claude" / "hooks" / "auto_lint.py").read_text(
        encoding="utf-8"
    )
    assert "ruff" in content
    assert "file_path" in content


def test_write_claude_hooks_creates_verify_on_stop(tmp_path: Path) -> None:
    _write_claude_hooks(tmp_path)
    assert (tmp_path / ".claude" / "hooks" / "verify_on_stop.sh").exists()


def test_write_claude_hooks_verify_on_stop_is_executable(tmp_path: Path) -> None:
    _write_claude_hooks(tmp_path)
    hook = tmp_path / ".claude" / "hooks" / "verify_on_stop.sh"
    assert hook.stat().st_mode & 0o111  # at least one execute bit set


def test_write_claude_hooks_verify_on_stop_runs_suite(tmp_path: Path) -> None:
    _write_claude_hooks(tmp_path)
    content = (tmp_path / ".claude" / "hooks" / "verify_on_stop.sh").read_text(
        encoding="utf-8"
    )
    assert "pytest" in content
    assert "mypy" in content
    assert "ruff" in content


def test_write_claude_settings_has_write_edit_posttooluse_hook(tmp_path: Path) -> None:
    _write_claude_settings(tmp_path)
    data = json.loads(
        (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    post = data["hooks"]["PostToolUse"]
    matchers = [h["matcher"] for h in post]
    assert "Write|Edit" in matchers


def test_write_claude_settings_has_stop_hook(tmp_path: Path) -> None:
    _write_claude_settings(tmp_path)
    data = json.loads(
        (tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    assert "Stop" in data["hooks"]
    stop = data["hooks"]["Stop"]
    assert len(stop) >= 1
    commands = [h["command"] for entry in stop for h in entry.get("hooks", [])]
    assert any("verify_on_stop" in cmd for cmd in commands)


# ---------------------------------------------------------------------------
# _write_claudeignore
# ---------------------------------------------------------------------------


def test_write_claudeignore_creates_file(tmp_path: Path) -> None:
    _write_claudeignore(tmp_path)
    assert (tmp_path / ".claudeignore").exists()


def test_write_claudeignore_excludes_pycache(tmp_path: Path) -> None:
    _write_claudeignore(tmp_path)
    content = (tmp_path / ".claudeignore").read_text(encoding="utf-8")
    assert "__pycache__/" in content


def test_write_claudeignore_excludes_venv(tmp_path: Path) -> None:
    _write_claudeignore(tmp_path)
    content = (tmp_path / ".claudeignore").read_text(encoding="utf-8")
    assert ".venv/" in content


def test_write_claudeignore_excludes_lock_file(tmp_path: Path) -> None:
    _write_claudeignore(tmp_path)
    content = (tmp_path / ".claudeignore").read_text(encoding="utf-8")
    assert "uv.lock" in content


def test_write_claudeignore_excludes_build_artifacts(tmp_path: Path) -> None:
    _write_claudeignore(tmp_path)
    content = (tmp_path / ".claudeignore").read_text(encoding="utf-8")
    assert "build/" in content
    assert "dist/" in content


# ---------------------------------------------------------------------------
# _write_mcp_config
# ---------------------------------------------------------------------------


def test_write_mcp_config_creates_file(tmp_path: Path) -> None:
    _write_mcp_config(tmp_path)
    assert (tmp_path / ".mcp.json").exists()


def test_write_mcp_config_valid_json(tmp_path: Path) -> None:
    _write_mcp_config(tmp_path)
    data = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_write_mcp_config_has_tree_sitter(tmp_path: Path) -> None:
    _write_mcp_config(tmp_path)
    data = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert "tree-sitter-mcp" in data
    assert data["tree-sitter-mcp"]["command"] == "npx"


def test_write_mcp_config_has_ast_grep(tmp_path: Path) -> None:
    _write_mcp_config(tmp_path)
    data = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert "ast-grep" in data
    assert data["ast-grep"]["command"] == "npx"


# ---------------------------------------------------------------------------
# _copy_claude_commands
# ---------------------------------------------------------------------------


def test_copy_claude_commands_creates_directories(
    tmp_path: Path,
) -> None:
    _copy_claude_commands(tmp_path)
    cmds_dir = tmp_path / ".claude" / "commands"
    assert cmds_dir.exists()
    subdirs = {d.name for d in cmds_dir.iterdir() if d.is_dir()}
    expected = {"analysis", "docs", "feature", "quality", "test"}
    assert expected <= subdirs


def test_copy_claude_commands_copies_files(tmp_path: Path) -> None:
    _copy_claude_commands(tmp_path)
    cmds_dir = tmp_path / ".claude" / "commands"
    md_files = list(cmds_dir.rglob("*.md"))
    assert len(md_files) >= 50  # at least 50 of 53


def test_copy_claude_commands_preserves_content(
    tmp_path: Path,
) -> None:
    _copy_claude_commands(tmp_path)
    explain = tmp_path / ".claude" / "commands" / "analysis" / "explain.md"
    assert explain.exists()
    content = explain.read_text(encoding="utf-8")
    assert len(content) > 10


def test_copy_claude_commands_includes_new_git_commands(tmp_path: Path) -> None:
    _copy_claude_commands(tmp_path)
    cmds_dir = tmp_path / ".claude" / "commands"
    assert (cmds_dir / "git" / "rebase.md").exists()
    assert (cmds_dir / "git" / "tag.md").exists()


def test_copy_claude_commands_includes_new_analysis_commands(tmp_path: Path) -> None:
    _copy_claude_commands(tmp_path)
    assert (tmp_path / ".claude" / "commands" / "analysis" / "todo.md").exists()


def test_copy_claude_commands_includes_integration_test_command(
    tmp_path: Path,
) -> None:
    _copy_claude_commands(tmp_path)
    assert (tmp_path / ".claude" / "commands" / "test" / "integration.md").exists()


# ---------------------------------------------------------------------------
# _write_conftest
# ---------------------------------------------------------------------------


def test_write_conftest_creates_file(tmp_path: Path) -> None:
    _write_conftest(tmp_path, "mytool")
    assert (tmp_path / "tests" / "conftest.py").exists()


def test_write_conftest_contains_fixture(tmp_path: Path) -> None:
    _write_conftest(tmp_path, "mytool")
    content = (tmp_path / "tests" / "conftest.py").read_text(
        encoding="utf-8",
    )
    assert "data_dir" in content
    assert "mytool" in content


def test_write_conftest_does_not_overwrite(tmp_path: Path) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    conftest = tests_dir / "conftest.py"
    conftest.write_text("# custom", encoding="utf-8")
    _write_conftest(tmp_path, "mytool")
    assert conftest.read_text(encoding="utf-8") == "# custom"


# ---------------------------------------------------------------------------
# _write_ci_workflow
# ---------------------------------------------------------------------------


def test_write_ci_workflow_creates_file(tmp_path: Path) -> None:
    _write_ci_workflow(tmp_path, "3.12")
    ci = tmp_path / ".github" / "workflows" / "ci.yml"
    assert ci.exists()


def test_write_ci_workflow_contains_python_version(
    tmp_path: Path,
) -> None:
    _write_ci_workflow(tmp_path, "3.11")
    content = (tmp_path / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "3.11" in content


def test_write_ci_workflow_runs_checks(tmp_path: Path) -> None:
    _write_ci_workflow(tmp_path, "3.12")
    content = (tmp_path / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "ruff check" in content
    assert "pytest" in content
    assert "mypy src/" in content
