"""Project scaffolding helpers: directory layout, config files, git init."""

from __future__ import annotations

import datetime
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
- `cymbal index .` - (re)index codebase for cymbal

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

## Efficiency
- Read specific line ranges (offset/limit), not whole files. Use Grep before Read.
- Batch independent tool calls into single messages.
- Use /compact at logical breakpoints. Never let context exceed ~200K.

## Code Exploration Policy
Use `cymbal` CLI for code navigation — prefer it over Read, Grep, Glob, or Bash for code exploration.
- **New to a repo?**: `cymbal structure` — entry points, hotspots, central packages. Start here.
- **To understand a symbol**: `cymbal investigate <symbol>` — returns source, callers, impact, or members based on what the symbol is.
- **To understand multiple symbols**: `cymbal investigate Foo Bar Baz` — batch mode, one invocation.
- **To trace an execution path**: `cymbal trace <symbol>` — follows the call graph downward.
- **To assess change risk**: `cymbal impact <symbol>` — follows the call graph upward.
- Before reading a file: `cymbal outline <file>` or `cymbal show <file:L1-L2>`
- Before searching: `cymbal search <query>` (symbols) or `cymbal search <query> --text` (grep)
- Before exploring structure: `cymbal ls` (tree) or `cymbal ls --stats` (overview)
- To disambiguate: `cymbal show path/to/file.py:SymbolName` or `cymbal investigate file.py:Symbol`
- First run: `cymbal index .` to build the initial index (<1s). After that, queries auto-refresh.
- All commands support `--json` for structured output.

## Context Management
- When fixing test failures across multiple attempts, summarise completed steps
  rather than reprinting full file contents.
- Prefer concise failure descriptions: test name + error message + line number.
- If the fix loop exceeds 3 iterations, focus only on the specific failing
  assertion — do not re-explain earlier fixes.
- Use `cymbal` for code navigation instead of reading entire files — prefer
  `cymbal investigate <symbol>` or `cymbal outline <file>` before any Read.
- Run `cymbal index .` after significant code changes to refresh the index.

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


_CLAUDE_PERMISSIONS: dict[str, list[str]] = {
    "allow": [
        "Bash(*)",
        "Read",
        "Write(*)",
        "Edit",
        "Glob",
        "Grep",
        "WebSearch",
        "WebFetch(*)",
    ],
    "deny": [
        "Bash(shutdown *)",
        "Bash(reboot *)",
        "Bash(poweroff *)",
        "Bash(dd *)",
        "Bash(mkfs *)",
    ],
    "ask": [
        "Bash(rm -rf /)",
        "Bash(rm -rf /*)",
        "Bash(rm *)",
        "Bash(rmdir *)",
        "Bash(mv *)",
        "Bash(cp -r *)",
        "Bash(git reset *)",
        "Bash(git clean *)",
        "Bash(git checkout *)",
        "Bash(git branch -D *)",
    ],
}


def _write_claude_settings(project_path: Path) -> None:
    """Write ``.claude/settings.json`` and ``.claude/settings.local.json``.

    ``settings.json`` holds shared config (permissions, autocompact, hooks).
    ``settings.local.json`` holds personal token-saving defaults (model,
    thinking cap, subagent model) that users can override for their own setup.

    Args:
        project_path: Project root directory.
    """
    claude_dir = project_path / ".claude"
    _ensure_directory(claude_dir)

    shared: dict[str, object] = {
        "model": "opusplan",
        "permissions": _CLAUDE_PERMISSIONS,
        "env": {
            "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "50",
            "MAX_THINKING_TOKENS": "10000",
            "CLAUDE_CODE_SUBAGENT_MODEL": "claude-haiku-4-5-20251001",
        },
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Read",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 .claude/hooks/read_once.py",
                        }
                    ],
                }
            ],
            "PostToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                "output=$(cat /dev/stdin); "
                                'lines=$(echo "$output" | wc -l); '
                                "if echo \"$CLAUDE_TOOL_INPUT_COMMAND\" | grep -q 'pytest'; "
                                "then threshold=500; else threshold=200; fi; "
                                'if [ "$lines" -gt "$threshold" ]; then '
                                'echo "$output" | head -100; '
                                "echo ''; "
                                'echo "... ($lines total lines, middle truncated) ..."; '
                                "echo ''; "
                                'echo "$output" | tail -50; '
                                'else echo "$output"; fi'
                            ),
                        }
                    ],
                },
                {
                    "matcher": "Write|Edit",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "python3 .claude/hooks/auto_lint.py",
                        }
                    ],
                },
            ],
            "Stop": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "bash .claude/hooks/verify_on_stop.sh",
                        }
                    ]
                }
            ],
        },
    }
    _write_file(claude_dir / "settings.json", json.dumps(shared, indent=2))
    _write_file(claude_dir / "settings.local.json", "{}\n")


def _write_claude_hooks(project_path: Path) -> None:
    """Write ``.claude/hooks/`` scripts for read deduplication and auto-lint.

    - ``read_once.py``: blocks redundant Read calls to save context tokens.
    - ``auto_lint.py``: runs ruff on every ``.py`` file written or edited.
    - ``verify_on_stop.sh``: runs ruff+pytest+mypy before Claude finishes.

    Args:
        project_path: Project root directory.
    """
    hooks_dir = project_path / ".claude" / "hooks"
    _ensure_directory(hooks_dir)
    script = '''\
#!/usr/bin/env python3
"""PreToolUse hook: block redundant Read calls to the same file+range.

Tracks which file paths (with offset/limit) have been read in the current
session and blocks re-reads to avoid wasting context tokens. State is stored
in a temp file and auto-resets after 6 hours (new session heuristic).
"""
from __future__ import annotations

import json
import os
import sys
import time

STATE_FILE = "/tmp/.claude_read_once_state.json"
MAX_AGE_SECONDS = 6 * 3600


def _load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"seen": {}}
    try:
        age = time.time() - os.path.getmtime(STATE_FILE)
        if age > MAX_AGE_SECONDS:
            return {"seen": {}}
        with open(STATE_FILE) as f:
            state = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"seen": {}}

    # Invalidate entries for files modified since they were last read
    seen = state.get("seen", {})
    invalidated = []
    for key, read_ts in seen.items():
        file_path = key.rsplit(":", 2)[0]
        try:
            if os.path.getmtime(file_path) > read_ts:
                invalidated.append(key)
        except OSError:
            invalidated.append(key)
    for key in invalidated:
        del seen[key]
    state["seen"] = seen
    return state


def _save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def main() -> None:
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input", {})
    file_path = tool_input.get("file_path", "")
    offset = tool_input.get("offset", 0)
    limit = tool_input.get("limit", 0)

    # Include offset/limit in key so different ranges of the same file are allowed
    key = f"{file_path}:{offset}:{limit}"

    state = _load_state()
    seen: dict[str, int] = state.get("seen", {})

    if key in seen:
        json.dump(
            {
                "decision": "block",
                "reason": f"Already read: {file_path} (offset={offset}, limit={limit})",
            },
            sys.stdout,
        )
    else:
        seen[key] = time.time()
        state["seen"] = seen
        _save_state(state)
        json.dump({"decision": "approve"}, sys.stdout)


if __name__ == "__main__":
    main()
'''
    _write_file(hooks_dir / "read_once.py", script)

    auto_lint = '''\
#!/usr/bin/env python3
"""PostToolUse hook: auto-lint .py files after Write or Edit."""
from __future__ import annotations

import json
import os
import subprocess
import sys


def main() -> None:
    data = json.load(sys.stdin)
    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path.endswith(".py") or not os.path.isfile(file_path):
        return
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    for cmd in (
        ["uv", "run", "ruff", "check", "--fix", file_path],
        ["uv", "run", "ruff", "format", file_path],
    ):
        try:
            subprocess.run(cmd, cwd=project_root, capture_output=True, timeout=30)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass


if __name__ == "__main__":
    main()
'''
    _write_file(hooks_dir / "auto_lint.py", auto_lint)

    verify_on_stop = """\
#!/usr/bin/env bash
# Stop hook: verify ruff+pytest+mypy before Claude finishes its turn.
# Exits non-zero to force Claude to continue and fix any failures.
set -uo pipefail
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# Skip if no Python files changed (avoids running suite on analysis-only sessions)
changed=$(
    git diff --name-only HEAD 2>/dev/null
    git diff --name-only --cached 2>/dev/null
    git ls-files --others --exclude-standard \'*.py\' 2>/dev/null
)
if ! echo "$changed" | grep -q \'\\.py$\'; then
    exit 0
fi

errors=""
ruff_out=$(uv run ruff check . --output-format=concise 2>&1) || errors+="RUFF:\\n$ruff_out\\n\\n"
pytest_out=$(uv run pytest -x --tb=line -q 2>&1) || errors+="PYTEST:\\n$pytest_out\\n\\n"
mypy_out=$(uv run mypy src/ --no-error-summary 2>&1) || errors+="MYPY:\\n$mypy_out\\n\\n"

if [ -n "$errors" ]; then
    echo "=== VERIFICATION FAILED ==="
    printf "%b" "$errors"
    echo "Fix the above before finishing."
    exit 1
fi
exit 0
"""
    verify_path = hooks_dir / "verify_on_stop.sh"
    _write_file(verify_path, verify_on_stop)
    verify_path.chmod(0o755)


def _write_claudeignore(project_path: Path) -> None:
    """Write ``.claudeignore`` to exclude generated/cache directories.

    Claude Code does not read ``.gitignore``, so this file explicitly
    prevents it from indexing cache dirs, lock files, and build artifacts.

    Args:
        project_path: Project root directory.
    """
    content = """\
# Cache directories
__pycache__/
.mypy_cache/
.ruff_cache/
.pytest_cache/

# Build artifacts
build/
dist/
*.egg-info/

# Virtual environment
.venv/

# Lock file (machine-generated)
uv.lock

# Compiled Python
*.pyc
*.pyo

# FUSE artifacts
.fuse_hidden*
"""
    _write_file(project_path / ".claudeignore", content)


def _write_mcp_config(project_path: Path) -> None:
    """Write ``.mcp.json`` with code-intelligence MCP servers.

    Provides tree-sitter (semantic search) and ast-grep (structural pattern
    matching) for projects with complex codebases. Requires Node.js/npx;
    Claude Code falls back to built-in tools if unavailable.

    Args:
        project_path: Project root directory.
    """
    config = {
        "tree-sitter-mcp": {
            "command": "npx",
            "args": ["@nendo/tree-sitter-mcp", "--mcp"],
        },
        "ast-grep": {
            "command": "npx",
            "args": ["@notprolands/ast-grep-mcp"],
        },
    }
    _write_file(project_path / ".mcp.json", json.dumps(config, indent=2))


def _copy_claude_commands(project_path: Path) -> None:
    """Copy bundled ``.claude/commands/`` templates into the project.

    The 53 command templates provide slash-command shortcuts for
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
    """Ensure a `.gitignore` contains all standard Python entries.

    Merges required entries into an existing file rather than overwriting.

    Args:
        project_path: Project root directory.
    """
    required = [
        "__pycache__/",
        "*.py[cod]",
        "*$py.class",
        ".venv/",
        "dist/",
        "build/",
        "*.egg-info/",
        ".mypy_cache/",
        ".pytest_cache/",
        ".ruff_cache/",
        "*.log",
        ".env",
        ".env.*",
        ".DS_Store",
        ".claude/.fuse_hidden*",
    ]
    gitignore = project_path / ".gitignore"
    existing: set[str] = set()
    if gitignore.exists():
        existing = {
            line.strip()
            for line in gitignore.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        }
    missing = [entry for entry in required if entry not in existing]
    if not missing and gitignore.exists():
        return
    if gitignore.exists():
        text = gitignore.read_text(encoding="utf-8").rstrip("\n")
        text += "\n\n# Added by vibegen\n" + "\n".join(missing) + "\n"
    else:
        text = "\n".join(required) + "\n"
    _write_file(gitignore, text)


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
    """Ensure ruff / pytest / mypy / bandit / vulture tool config is present.

    Only appends sections that are missing, preserving existing config.

    Args:
        project_path: Project root directory.
    """
    pyproject_path = project_path / "pyproject.toml"
    if not pyproject_path.exists():
        return

    text = pyproject_path.read_text(encoding="utf-8")
    additions: list[str] = []

    tool_sections: list[tuple[str, str]] = [
        (
            "[tool.ruff]",
            "[tool.ruff]\n"
            "line-length = 88\n"
            'target-version = "py312"\n'
            'extend-exclude = [".claude"]\n'
            "\n"
            "[tool.ruff.lint]\n"
            'select = ["E", "F", "I", "UP", "B", "SIM", "N"]\n'
            "\n"
            "[tool.ruff.format]\n"
            "docstring-code-format = true\n",
        ),
        (
            "[tool.pytest",
            "[tool.pytest.ini_options]\n"
            'testpaths = ["tests"]\n'
            'addopts = "-ra -q --strict-markers --tb=short"\n',
        ),
        (
            "[tool.mypy]",
            "[tool.mypy]\n"
            "strict = true\n"
            "warn_return_any = true\n"
            "disallow_untyped_defs = true\n",
        ),
        (
            "[tool.bandit]",
            '[tool.bandit]\nexclude_dirs = ["tests", ".venv"]\nskips = ["B101"]\n',
        ),
        (
            "[tool.vulture]",
            '[tool.vulture]\nmin_confidence = 80\npaths = ["src/"]\n',
        ),
    ]

    for marker, section in tool_sections:
        if marker not in text:
            additions.append(section)

    if additions:
        _write_file(pyproject_path, text.rstrip() + "\n\n" + "\n".join(additions))


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
    """Write a comprehensive README.md for a newly generated project.

    For new projects this writes a full template. For existing projects
    with a README already present, use :func:`_update_readme_with_claude`
    instead to intelligently merge changes.

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


def _update_readme_with_claude(
    project_path: Path,
    project_name: str,
    package_name: str,
    model: str = "claude-sonnet-4-6",
    show_output: bool = False,
) -> bool:
    """Use Claude to intelligently update an existing README.md.

    Asks Claude to read the current project structure, source code,
    and existing README, then update it to accurately reflect the
    project while preserving user-written content.

    If no README exists, Claude generates one from scratch based on
    the project contents.

    Args:
        project_path: Project root directory.
        project_name: Human-readable project name.
        package_name: Python package name (snake_case).
        model: Claude model identifier.
        show_output: Show full Claude output.

    Returns:
        True on success, False on failure.
    """
    from ._llm import _run_claude_session

    readme_path = project_path / "README.md"
    existing = ""
    if readme_path.exists():
        existing = readme_path.read_text(encoding="utf-8")

    action = "Update" if existing else "Generate"
    prompt = (
        f"{action} the README.md for this project.\n\n"
        f"Project name: {project_name}\n"
        f"Package: {package_name}\n\n"
    )
    if existing:
        prompt += (
            "The current README.md is below. Preserve any user-written "
            "content, links, badges, and custom sections. Update the "
            "installation, usage, project structure, and development "
            "sections to accurately reflect the current codebase. "
            "Add a Development section with uv run commands for pytest, "
            "ruff, mypy if missing.\n\n"
            f"Current README.md:\n```\n{existing[:3000]}\n```\n"
        )
    else:
        prompt += (
            "There is no README.md yet. Read the project source code "
            "and generate a comprehensive README with: project "
            "description, installation (uv sync), usage examples, "
            "development commands (pytest, ruff, mypy), and project "
            "structure."
        )

    try:
        _run_claude_session(
            prompt=prompt,
            model=model,
            cwd=project_path,
            permission_mode="acceptEdits",
            show_output=show_output,
        )
        return True
    except Exception:  # noqa: BLE001
        _print_warn("Claude README update failed — writing template")
        return False


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


def _write_docs_reference(project_path: Path, spec: dict[str, Any]) -> None:
    """Write initial docs/reference/ with ARCHITECTURE.md and CHANGELOG.md.

    Args:
        project_path: Project root directory.
        spec: Parsed spec dict (from ``_parse_spec``).
    """
    ref_dir = project_path / "docs" / "reference"
    _ensure_directory(ref_dir)

    pkg = spec["project_name"].lower().replace("-", "_")
    today = datetime.date.today().isoformat()
    description = spec.get("description", "<!-- TODO: Describe the system -->")

    arch_content = f"""# {spec["project_name"]} Architecture

## Overview
{description}

## Module Map
| Module | Description |
|--------|-------------|
| `src/{pkg}/` | Main package |

## Key Design Decisions
<!-- Document important architectural choices and their rationale -->

---
*Run `/docs:doc-repo` to auto-generate detailed documentation.*
*Run `cymbal structure` to see entry points, hotspots, and central packages.*
"""

    changelog_content = f"""# Changelog
All notable changes to this project will be documented in this file.
Format: [Keep a Changelog](https://keepachangelog.com)

## [0.1.0] - {today}

### Added
- Initial project scaffold via VibeGen
"""

    _write_file(ref_dir / "ARCHITECTURE.md", arch_content)
    _write_file(ref_dir / "CHANGELOG.md", changelog_content)


def _run_cymbal_index(project_path: Path) -> None:
    """Run ``cymbal index .`` in *project_path* if cymbal is installed.

    Non-fatal: silently skips if cymbal is not on PATH.

    Args:
        project_path: Project root directory to index.
    """
    if not shutil.which("cymbal"):
        return
    try:
        _run_cmd(["cymbal", "index", "."], cwd=project_path, check=False)
        _print_ok("cymbal: codebase indexed")
    except Exception:  # noqa: BLE001
        _print_warn("cymbal index failed; skipping")


def _repair_project(
    project_path: Path,
    model: str = "claude-sonnet-4-6",
    show_output: bool = False,
) -> tuple[int, dict[str, Any], str]:
    """Re-apply scaffold files to an existing project.

    Reads the current project structure, then writes/overwrites all scaffold
    files so the project matches a freshly generated vibegen project.
    Uses Claude to intelligently update the README when one already exists.

    Additive operations (gitignore, pyproject.toml tool sections) merge into
    existing files rather than overwriting.

    Args:
        project_path: Path to the existing project root directory.
        model: Claude model identifier for README generation.
        show_output: Show full Claude output.

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
    _print_ok("Written: .claude/settings.json & .claude/settings.local.json")

    _write_claude_hooks(project_path)
    _print_ok("Written: .claude/hooks/read_once.py")

    _copy_claude_commands(project_path)
    _print_ok("Written: .claude/commands/")

    _write_docs_reference(project_path, spec)
    _print_ok("Written: docs/reference/ARCHITECTURE.md & CHANGELOG.md")

    _write_claudeignore(project_path)
    _print_ok("Written: .claudeignore")

    _write_mcp_config(project_path)
    _print_ok("Written: .mcp.json")

    _create_vscode_settings(project_path)
    _print_ok("Written: .vscode/settings.json")

    _write_gitignore(project_path)
    _print_ok("Updated: .gitignore")

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

    # Use Claude to update README if one already exists; fall back to template.
    readme_exists = (project_path / "README.md").exists()
    if readme_exists:
        _print_step("Updating README.md with Claude...")
        ok = _update_readme_with_claude(
            project_path,
            project_name,
            package_name,
            model=model,
            show_output=show_output,
        )
        if ok:
            _print_ok("Updated: README.md (via Claude)")
        else:
            _generate_readme(project_path, spec, package_name)
            _print_ok("Written: README.md (template fallback)")
    else:
        _print_step("Generating README.md with Claude...")
        ok = _update_readme_with_claude(
            project_path,
            project_name,
            package_name,
            model=model,
            show_output=show_output,
        )
        if ok:
            _print_ok("Generated: README.md (via Claude)")
        else:
            _generate_readme(project_path, spec, package_name)
            _print_ok("Written: README.md (template fallback)")

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

    _run_cymbal_index(project_path)
    return 0, spec, package_name
