"""Project scaffolding helpers: directory layout, config files, git init."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ._io import _print_ok, _print_warn, _run_cmd, _write_file


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
    """Copy documentation files referenced in the spec to ``docs/``.

    Args:
        project_path: Project root directory.
        spec_path: Path to the spec file (used to resolve relative doc paths).
        doc_files: List of relative doc file paths from the spec.
    """
    if not doc_files:
        return

    spec_dir = spec_path.parent
    docs_dir = project_path / "docs"
    _ensure_directory(docs_dir)

    for doc_file in doc_files:
        full_path = spec_dir / doc_file
        if full_path.exists():
            dest = docs_dir / Path(doc_file).name
            _write_file(dest, full_path.read_text(encoding="utf-8"))
            _print_ok(f"Loaded: {doc_file}")
        else:
            _print_warn(f"Documentation file not found: {full_path}")


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
