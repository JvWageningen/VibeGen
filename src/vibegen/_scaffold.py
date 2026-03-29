"""Project scaffolding helpers: directory layout, config files, git init."""

from __future__ import annotations

import json
import os
import shutil
from importlib import resources
from pathlib import Path
from typing import Any

from ._io import _print_err, _print_ok, _print_step, _print_warn, _run_cmd, _write_file


def _ensure_directory(path: Path) -> None:
    """Create *path* and all parents; silently succeed if it already exists.

    Args:
        path: Directory to create.
    """
    path.mkdir(parents=True, exist_ok=True)


def _write_claude_md(project_path: Path, spec: dict[str, Any]) -> None:
    """Write CLAUDE.md with project conventions and code-style rules.

    Args:
        project_path: Project root directory.
        spec: Parsed spec dict (from ``_parse_spec``).
    """
    description = spec.get("description", "")
    if not description:
        for line in spec["raw"].splitlines():
            if line.startswith("## Description"):
                continue
            if line.startswith("## "):
                break
            if line.strip():
                description = line.strip()
                break

    pkg = spec["project_name"].lower().replace("-", "_")
    content = f"""# {spec["project_name"]}

## Project
{description}

## Tech Stack
- Python {spec["python_version"]}, managed by `uv`
- Ruff for linting and formatting
- pytest for testing
- mypy for type checking

## Directory Map
- `src/{pkg}/` - main package
- `tests/` - test suite (mirrors src structure)

## Commands
- `uv run pytest` - run tests
- `uv run ruff check . --fix` - lint and fix
- `uv run ruff format .` - format
- `uv run mypy src/` - type check
- `uv run bandit -r src/` - security check
- `uv run pip-audit` - dependency vulnerability check
- `uv run radon cc src/ -mi C` - complexity report
- `uv run vulture src/` - unused code detection

## Code Style Rules
- Always add type hints to function signatures
- Use Google-style docstrings on every public function and class
- Use loguru for logging, never print()
- Use Pydantic models for structured data
- Prefer early returns over deep nesting
- Keep functions under 30 lines; extract helpers if longer
- Use absolute imports: `from {pkg}.module import ...`
- snake_case for files, modules, functions, variables
- PascalCase for classes
- UPPER_SNAKE_CASE for constants

## Verification
After any code change, always:
1. Run: `uv run ruff check . --fix` and `uv run ruff format .`
2. Run: `uv run pytest -x`
3. Run: `uv run mypy src/`

## Things to Avoid
- Never use pip install directly; always `uv add`
- Never use bare `except:` - catch specific exceptions
- Never use mutable default arguments
- No `print()` statements - use loguru
"""
    _write_file(project_path / "CLAUDE.md", content)


def _write_claude_settings(project_path: Path) -> None:
    """Write ``.claude/settings.local.json`` with default permissions.

    Configures Claude Code with sensible allow/deny/ask rules so the
    generated project is immediately usable with Claude Code.

    Args:
        project_path: Project root directory.
    """
    claude_dir = project_path / ".claude"
    _ensure_directory(claude_dir)
    settings = {
        "permissions": {
            "allow": [
                "Bash(*)",
                "Bash(uv run python -c :*)",
                "WebSearch",
            ],
            "deny": [
                "Bash(rm -rf /)",
                "Bash(rm -rf /*)",
                "Bash(sudo *)",
                "Bash(shutdown *)",
                "Bash(reboot *)",
                "Bash(poweroff *)",
                "Bash(dd *)",
                "Bash(mkfs *)",
            ],
            "ask": [
                "Bash(rm *)",
                "Bash(rmdir *)",
                "Bash(mv *)",
                "Bash(cp -r *)",
                "Bash(git reset *)",
                "Bash(git clean *)",
                "Bash(git checkout *)",
                "Bash(git branch -D *)",
                "Bash(pip install *)",
                "Bash(uv pip install *)",
                "Bash(npm install *)",
                "Bash(docker *)",
            ],
        }
    }
    _write_file(
        claude_dir / "settings.local.json",
        json.dumps(settings, indent=2),
    )


def _copy_claude_commands(project_path: Path) -> None:
    """Copy bundled ``.claude/commands/`` templates into the project.

    The 43 command templates provide slash-command shortcuts for
    analysis, documentation, feature work, quality, and testing.

    Args:
        project_path: Project root directory.
    """
    dest_dir = project_path / ".claude" / "commands"

    # Locate bundled templates via importlib.resources (Python 3.11+)
    try:
        templates_root = resources.files("vibegen") / "templates" / "claude_commands"
    except (TypeError, FileNotFoundError):
        templates_root = None

    # Fallback: resolve relative to this file
    if templates_root is None or not _traversable_exists(templates_root):
        templates_root = Path(__file__).parent / "templates" / "claude_commands"

    if not _traversable_exists(templates_root):
        return

    _copy_traversable_tree(templates_root, dest_dir)


def _traversable_exists(path: Any) -> bool:
    """Check whether a Traversable or Path exists and is a directory.

    Args:
        path: A ``pathlib.Path`` or ``importlib.resources.abc.Traversable``.

    Returns:
        True if the path exists and is a directory.
    """
    try:
        return path.is_dir()
    except (AttributeError, FileNotFoundError, TypeError):
        return False


def _copy_traversable_tree(src: Any, dest: Path) -> None:
    """Recursively copy a Traversable (or Path) tree into *dest*.

    Args:
        src: Source directory (Traversable or Path).
        dest: Destination directory on the filesystem.
    """
    _ensure_directory(dest)
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            _copy_traversable_tree(item, target)
        elif item.is_file() and item.name.endswith(".md"):
            content = item.read_text(encoding="utf-8")
            _write_file(target, content)


def _create_vscode_settings(project_path: Path) -> None:
    """Write `.vscode/settings.json` with Ruff and Python configuration.

    Args:
        project_path: Project root directory.
    """
    vscode_dir = project_path / ".vscode"
    _ensure_directory(vscode_dir)
    interpreter = (
        "./.venv/Scripts/python.exe" if os.name == "nt" else "./.venv/bin/python"
    )
    settings = {
        "python.defaultInterpreterPath": interpreter,
        "python.analysis.typeCheckingMode": "strict",
        "[python]": {
            "editor.defaultFormatter": "charliermarsh.ruff",
            "editor.formatOnSave": True,
            "editor.codeActionsOnSave": {
                "source.fixAll.ruff": "explicit",
                "source.organizeImports.ruff": "explicit",
            },
        },
        "ruff.lint.args": ["--config=pyproject.toml"],
        "files.trimTrailingWhitespace": True,
        "files.insertFinalNewline": True,
        "files.eol": "\n",
    }
    _write_file(vscode_dir / "settings.json", json.dumps(settings, indent=2))


def _write_gitignore(project_path: Path) -> None:
    """Write a standard Python `.gitignore`.

    Args:
        project_path: Project root directory.
    """
    content = """__pycache__/
*.py[cod]
*$py.class
.venv/
dist/
build/
*.egg-info/
.mypy_cache/
.pytest_cache/
.ruff_cache/
*.log
.env
.env.*
.DS_Store
"""
    _write_file(project_path / ".gitignore", content)


def _write_gitattributes(project_path: Path) -> None:
    """Write `.gitattributes` enforcing LF line endings.

    Args:
        project_path: Project root directory.
    """
    _write_file(project_path / ".gitattributes", "* text=auto eol=lf\n")


def _write_pre_commit_config(project_path: Path) -> None:
    """Write `.pre-commit-config.yaml` with ruff, bandit, and vulture hooks.

    Args:
        project_path: Project root directory.
    """
    content = """repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: bandit
        name: bandit security check
        entry: uv run bandit
        args: ["-c", "pyproject.toml", "-r", "src/"]
        language: system
        types: [python]
        pass_filenames: false
      - id: vulture
        name: vulture dead code
        entry: uv run vulture
        args: ["src/", "--min-confidence", "80"]
        language: system
        types: [python]
        pass_filenames: false
"""
    _write_file(project_path / ".pre-commit-config.yaml", content)


def _ensure_package_dir(project_path: Path, package_name: str) -> Path:
    """Create ``src/<package_name>/`` with an ``__init__.py`` if absent.

    Args:
        project_path: Project root directory.
        package_name: Python package name (snake_case).

    Returns:
        Path to the package directory.
    """
    src = project_path / "src"
    pkg = src / package_name
    _ensure_directory(pkg)
    init_py = pkg / "__init__.py"
    if not init_py.exists():
        _write_file(init_py, f'"""{package_name} package"""\n')
    return pkg


def _update_pyproject_tools(project_path: Path) -> None:
    """Append ruff / pytest / mypy / bandit / vulture tool config if absent.

    Args:
        project_path: Project root directory.
    """
    pyproject_path = project_path / "pyproject.toml"
    if not pyproject_path.exists():
        return

    text = pyproject_path.read_text(encoding="utf-8")
    if "[tool.ruff]" in text:
        return

    tool_config = """
[tool.ruff]
line-length = 88
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "N"]

[tool.ruff.format]
docstring-code-format = true

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra -q --strict-markers --tb=short"

[tool.mypy]
strict = true
warn_return_any = true
disallow_untyped_defs = true

[tool.bandit]
exclude_dirs = ["tests", ".venv"]
skips = ["B101"]

[tool.vulture]
min_confidence = 80
paths = ["src/"]
"""
    _write_file(pyproject_path, text + tool_config)


def _write_conftest(project_path: Path, package_name: str) -> None:
    """Write a minimal ``tests/conftest.py`` with shared fixtures.

    Does nothing if the file already exists to avoid overwriting
    LLM-generated fixtures.

    Args:
        project_path: Project root directory.
        package_name: Python package name (for the docstring).
    """
    tests_dir = project_path / "tests"
    _ensure_directory(tests_dir)
    conftest = tests_dir / "conftest.py"
    if conftest.exists():
        return

    content = f'''\
"""Shared pytest fixtures for {package_name} tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def data_dir() -> Path:
    """Return the path to the test data directory."""
    d = Path(__file__).parent / "data"
    d.mkdir(exist_ok=True)
    return d
'''
    _write_file(conftest, content)


def _write_ci_workflow(
    project_path: Path,
    python_version: str,
) -> None:
    """Write ``.github/workflows/ci.yml`` for automated CI.

    Generates a GitHub Actions workflow that runs ruff, pytest,
    and mypy on push and pull requests to main.

    Args:
        project_path: Project root directory.
        python_version: Python version string (e.g. ``"3.12"``).
    """
    workflows_dir = project_path / ".github" / "workflows"
    _ensure_directory(workflows_dir)

    content = f"""\
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "{python_version}"
      - uses: astral-sh/setup-uv@v4
      - run: uv sync
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run pytest -x --tb=short
      - run: uv run mypy src/
"""
    _write_file(workflows_dir / "ci.yml", content)


def _init_git(project_path: Path) -> None:
    """Initialize a git repository with a minimal initial commit.

    Args:
        project_path: Project root directory.
    """
    try:
        _run_cmd(["git", "init"], cwd=project_path, check=False)
        _run_cmd(
            ["git", "config", "user.email", "vibegen@example.com"],
            cwd=project_path,
            check=False,
        )
        _run_cmd(
            ["git", "config", "user.name", "VibeGen"],
            cwd=project_path,
            check=False,
        )
        _run_cmd(["git", "add", "-A"], cwd=project_path, check=False)
        _run_cmd(
            ["git", "commit", "-q", "-m", "chore: initial scaffold from vibegen"],
            cwd=project_path,
            check=False,
        )
        _print_ok("Git initialized")
    except Exception as e:  # noqa: BLE001
        _print_warn(f"Could not initialize git: {e}")


def _copy_docs(project_path: Path, spec_path: Path, doc_files: list[str]) -> None:
    """Copy documentation files and directories referenced in the spec to ``docs/``.

    Args:
        project_path: Project root directory.
        spec_path: Path to the spec file (used to resolve relative doc paths).
        doc_files: List of relative doc file/directory paths from the spec.
    """
    if not doc_files:
        return

    spec_dir = spec_path.parent
    docs_dir = project_path / "docs"
    _ensure_directory(docs_dir)

    for entry in doc_files:
        full_path = spec_dir / entry
        if not full_path.exists():
            _print_warn(f"Documentation path not found: {full_path}")
            continue

        if full_path.is_dir():
            for child in sorted(full_path.rglob("*")):
                if not child.is_file():
                    continue
                rel = child.relative_to(full_path)
                dest = docs_dir / entry / rel
                _ensure_directory(dest.parent)
                try:
                    _write_file(dest, child.read_text(encoding="utf-8"))
                except UnicodeDecodeError:
                    shutil.copy2(child, dest)
                _print_ok(f"Copied doc: {entry}/{rel}")
        else:
            dest = docs_dir / Path(entry).name
            try:
                _write_file(dest, full_path.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                shutil.copy2(full_path, dest)
            _print_ok(f"Copied doc: {entry}")


def _generate_readme(
    project_path: Path, spec: dict[str, Any], package_name: str
) -> None:
    """Write a comprehensive README.md.

    Args:
        project_path: Project root directory.
        spec: Parsed spec dict.
        package_name: Python package name (snake_case).
    """
    description = spec.get("description", "")
    usage = spec.get("usage", "See the documentation for usage details.")
    repo_slug = spec["project_name"].lower().replace(" ", "-").replace("_", "-")

    src_dir = project_path / "src" / package_name
    py_files = []
    if src_dir.exists():
        for py_file in sorted(src_dir.rglob("*.py")):
            if py_file.name != "__init__.py":
                rel_path = py_file.relative_to(project_path / "src")
                py_files.append(f"  - `{rel_path}`")

    py_files_section = (
        "\n".join(py_files) if py_files else "  - (generated source files)"
    )

    content = f"""# {spec["project_name"]}

{description}

## Installation

```bash
git clone https://github.com/<user>/{repo_slug}
cd {repo_slug}
uv sync
```

## Usage

{usage}

## Development

```bash
uv run pytest              # run tests
uv run ruff check . --fix  # lint and auto-fix
uv run ruff format .       # format code
uv run mypy src/           # type check
```

## Project Structure

```
src/{package_name}/
{py_files_section}
tests/
```

## License

MIT
"""
    _write_file(project_path / "README.md", content)


# ---------------------------------------------------------------------------
# Repair helpers
# ---------------------------------------------------------------------------


def _read_pyproject_info(project_path: Path) -> dict[str, str]:
    """Extract project metadata from pyproject.toml.

    Args:
        project_path: Project root directory.

    Returns:
        Dict with keys ``project_name``, ``python_version``, and ``description``.
    """
    pyproject = project_path / "pyproject.toml"
    if not pyproject.exists():
        return {
            "project_name": project_path.name,
            "python_version": "3.12",
            "description": "",
        }

    try:
        import tomllib

        with open(pyproject, "rb") as f:
            data = tomllib.load(f)

        project = data.get("project", {})
        raw_requires = project.get("requires-python", ">=3.12")
        python_version = raw_requires.lstrip("><=~!")
        return {
            "project_name": project.get("name", project_path.name),
            "python_version": python_version or "3.12",
            "description": project.get("description", ""),
        }
    except Exception:  # noqa: BLE001
        pass

    # Fallback: parse raw text
    text = pyproject.read_text(encoding="utf-8")
    name = project_path.name
    python_version = "3.12"
    description = ""
    for line in text.splitlines():
        if line.startswith("name = "):
            name = line.split("=", 1)[1].strip().strip('"').strip("'")
        elif line.startswith("requires-python = "):
            raw = line.split("=", 1)[1].strip().strip('"').strip("'")
            python_version = raw.lstrip("><=~!") or "3.12"
        elif line.startswith("description = "):
            description = line.split("=", 1)[1].strip().strip('"').strip("'")
    return {
        "project_name": name,
        "python_version": python_version,
        "description": description,
    }


def _detect_package_name(project_path: Path) -> str | None:
    """Detect the Python package name from the ``src/`` directory structure.

    Args:
        project_path: Project root directory.

    Returns:
        Package name (first non-egg-info subdirectory under ``src/``), or ``None``.
    """
    src = project_path / "src"
    if not src.exists():
        return None
    for subdir in sorted(src.iterdir()):
        if (
            subdir.is_dir()
            and not subdir.name.startswith(".")
            and not subdir.name.endswith(".egg-info")
        ):
            return subdir.name
    return None


def _repair_project(
    project_path: Path,
) -> tuple[int, dict[str, Any], str]:
    """Re-apply scaffold files to an existing project.

    Reads the current project structure, then writes/overwrites all scaffold
    files so the project matches a freshly generated vibegen project.

    Args:
        project_path: Path to the existing project root directory.

    Returns:
        Tuple of (exit_code, spec_dict, package_name).
        On error the spec dict is empty and package_name is ``""``.
    """
    if not project_path.exists():
        _print_err(f"Repo path not found: {project_path}")
        return 1, {}, ""

    if not (project_path / "pyproject.toml").exists():
        _print_err(
            f"No pyproject.toml found at {project_path}. Is this a Python project?"
        )
        return 1, {}, ""

    info = _read_pyproject_info(project_path)
    project_name = info["project_name"]
    python_version = info["python_version"]
    description = info["description"]

    package_name = _detect_package_name(project_path)
    if not package_name:
        package_name = project_name.lower().replace("-", "_").replace(" ", "_")
        _print_warn(
            f"Could not detect package name from src/; assuming '{package_name}'"
        )

    _print_step(f"Repairing '{project_name}' (package: {package_name})")

    spec: dict[str, Any] = {
        "project_name": project_name,
        "python_version": python_version,
        "description": description,
        "dependencies": [],
        "doc_files": [],
        "usage": "See the documentation for usage details.",
        "raw": f"## Name\n{project_name}\n\n## Description\n{description}\n",
    }

    _write_claude_md(project_path, spec)
    _print_ok("Written: CLAUDE.md")

    _write_claude_settings(project_path)
    _print_ok("Written: .claude/settings.local.json")

    _copy_claude_commands(project_path)
    _print_ok("Written: .claude/commands/")

    _create_vscode_settings(project_path)
    _print_ok("Written: .vscode/settings.json")

    _write_gitignore(project_path)
    _print_ok("Written: .gitignore")

    _write_gitattributes(project_path)
    _print_ok("Written: .gitattributes")

    _write_pre_commit_config(project_path)
    _print_ok("Written: .pre-commit-config.yaml")

    _ensure_package_dir(project_path, package_name)
    _print_ok(f"Ensured: src/{package_name}/__init__.py")

    tests_dir = project_path / "tests"
    _ensure_directory(tests_dir)
    _print_ok("Ensured: tests/")

    _update_pyproject_tools(project_path)
    _print_ok("Updated: pyproject.toml (tool config)")

    _write_conftest(project_path, package_name)
    _print_ok("Written: tests/conftest.py")

    _write_ci_workflow(project_path, python_version)
    _print_ok("Written: .github/workflows/ci.yml")

    _generate_readme(project_path, spec, package_name)
    _print_ok("Written: README.md")

    try:
        _run_cmd(["git", "add", "-A"], cwd=project_path, check=False)
        _run_cmd(
            ["git", "commit", "-q", "-m", "chore: repair scaffold with vibegen"],
            cwd=project_path,
            check=False,
        )
        _print_ok("Git commit: chore: repair scaffold with vibegen")
    except Exception:  # noqa: BLE001
        _print_warn("Could not create git commit.")

    return 0, spec, package_name
