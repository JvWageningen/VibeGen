"""Command-line interface for vibegen."""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .ollama_client import OllamaClient

# Standard-library module names (Python 3.10+); used to identify external deps.
_STDLIB: frozenset[str] = sys.stdlib_module_names


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------


def _write_file(path: Path, content: str) -> None:
    """Write a text file with LF line endings (avoids CRLF warnings on Windows)."""
    path.write_text(content, encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# Console helpers
# ---------------------------------------------------------------------------


def _print_step(message: str) -> None:
    print(f"[STEP]  {message}")


def _print_ok(message: str) -> None:
    print(f"[OK]    {message}")


def _print_warn(message: str) -> None:
    print(f"[WARN]  {message}")


def _print_err(message: str) -> None:
    print(f"[ERR]   {message}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------


def _run_cmd(
    args: list[str],
    cwd: Path | None = None,
    capture_output: bool = False,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=capture_output,
        text=True,
        env=env,
        check=check,
    )


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


def _render_template(text: str, values: dict[str, str]) -> str:
    """Replace {{key}} placeholders in *text* with values from *values*."""
    out = text
    for k, v in values.items():
        out = out.replace(f"{{{{{k}}}}}", v)
    return out


# ---------------------------------------------------------------------------
# Spec parsing
# ---------------------------------------------------------------------------


def _parse_spec(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    def _extract_section(header: str, default: str = "") -> str:
        in_section = False
        collected: list[str] = []
        for line in lines:
            if in_section:
                if line.startswith("## ") and not line.startswith(header):
                    break
                if line.strip():
                    collected.append(line)
            elif line.startswith(header):
                in_section = True
        return "\n".join(collected).strip() or default

    project_name = _extract_section("## Name")
    python_version = _extract_section("## Python Version", "3.12").strip()
    dependencies = _extract_section("## Dependencies", "").strip()
    description = _extract_section("## Description", "").strip()

    # Extract doc file references <!-- docs/... -->
    doc_files: list[str] = []
    for line in lines:
        if "<!--" in line and "docs/" in line and "-->" in line:
            start = line.find("<!--")
            end = line.find("-->", start)
            if start >= 0 and end >= 0:
                comment = line[start + 4 : end].strip()
                if comment.startswith("docs/"):
                    doc_files.append(comment)

    usage = _extract_section("## Usage")
    if not usage:
        usage = _extract_section("## Examples")
    if not usage:
        usage = _extract_section("## CLI")
    if not usage:
        usage = _extract_section("## Interface")
    if not usage:
        usage = _extract_section("## API")

    return {
        "project_name": project_name,
        "python_version": python_version,
        "dependencies": [d.strip() for d in dependencies.split(",") if d.strip()],
        "doc_files": doc_files,
        "usage": usage,
        "description": description,
        "raw": text,
    }


# ---------------------------------------------------------------------------
# Dependency graph & source-code analysis
# ---------------------------------------------------------------------------


def _build_dependency_graph(src_dir: Path, package_name: str) -> str:
    """Build an AST-based dependency and public-API graph for all source files."""
    graph: dict[str, dict[str, list[str]]] = {}

    for py_file in sorted(src_dir.rglob("*.py")):
        module = py_file.stem
        internal: list[str] = []
        external: list[str] = []
        public_api: list[str] = []

        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top == package_name:
                        internal.append(alias.name)
                    elif top not in _STDLIB:
                        external.append(top)
            elif isinstance(node, ast.ImportFrom):
                mod_name = node.module or ""
                top = mod_name.split(".")[0]
                if top == package_name or node.level > 0:
                    internal.append(mod_name or f"(relative level={node.level})")
                elif top and top not in _STDLIB:
                    external.append(top)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    public_api.append(f"def {node.name}()")
            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                public_api.append(f"class {node.name}")

        graph[module] = {
            "internal": sorted(set(internal)),
            "external": sorted(set(external)),
            "api": sorted(set(public_api)),
        }

    lines: list[str] = ["=== Dependency Graph ==="]
    for mod, info in sorted(graph.items()):
        lines.append(f"\n{mod}:")
        if info["internal"]:
            lines.append(f"  internal imports : {', '.join(info['internal'])}")
        if info["external"]:
            lines.append(f"  external packages: {', '.join(info['external'])}")
        if info["api"]:
            lines.append(f"  public API       : {', '.join(info['api'])}")

    return "\n".join(lines)


def _read_source_files(src_dir: Path, project_path: Path) -> str:
    """Return the content of every source Python file as a single formatted block."""
    parts: list[str] = []
    for py_file in sorted(src_dir.rglob("*.py")):
        rel = py_file.relative_to(project_path)
        content = py_file.read_text(encoding="utf-8")
        parts.append(f"=== {rel} ===\n{content}")
    return "\n\n".join(parts)


def _get_pyproject_deps(project_path: Path) -> str:
    """Return project dependencies from pyproject.toml as a bullet list."""
    pyproject = project_path / "pyproject.toml"
    if not pyproject.exists():
        return "(no pyproject.toml found)"

    try:
        import tomllib

        with open(pyproject, "rb") as f:
            data = tomllib.load(f)

        all_deps: list[str] = list(data.get("project", {}).get("dependencies", []))

        # Include optional-dependencies (e.g. [project.optional-dependencies.dev])
        for group_deps in (
            data.get("project", {}).get("optional-dependencies", {}).values()
        ):
            all_deps.extend(group_deps)

        # Include dependency-groups (e.g. [dependency-groups] dev = [...])
        for group_deps in data.get("dependency-groups", {}).values():
            for item in group_deps:
                # Items may be plain strings or dicts like {include-group = "..."}
                if isinstance(item, str):
                    all_deps.append(item)

        return "\n".join(f"- {d}" for d in all_deps) or "(no dependencies listed)"
    except Exception:
        pass

    # Fallback: parse raw text
    text = pyproject.read_text(encoding="utf-8")
    in_deps = False
    result: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "dependencies = [":
            in_deps = True
            continue
        if in_deps:
            if stripped == "]":
                break
            dep = stripped.strip('",')
            if dep:
                result.append(f"- {dep}")
    return "\n".join(result) or "(could not parse dependencies)"


# ---------------------------------------------------------------------------
# Ruff error detection & LLM-based fixing
# ---------------------------------------------------------------------------


def _get_ruff_errors_by_file(
    project_path: Path, check_paths: list[str]
) -> dict[str, list[str]]:
    """Run ruff and return non-auto-fixable errors grouped by relative file path."""
    try:
        result = _run_cmd(
            ["uv", "run", "ruff", "check", "--output-format=concise"] + check_paths,
            cwd=project_path,
            capture_output=True,
            check=False,
        )
    except Exception:
        return {}

    errors: dict[str, list[str]] = {}
    for line in result.stdout.splitlines():
        if not line or line.startswith("Found") or line.startswith("warning"):
            continue
        if "[*]" in line:
            continue  # auto-fixable, skip
        if " E501 " in line:
            continue  # handled by ruff format, not the LLM

        # Parse "path:line:col: CODE message"
        # On Windows paths start with a drive letter: C:\...
        parts = line.split(":")
        if len(parts) < 3:
            continue

        if len(parts[0]) == 1 and parts[0].isalpha():
            # Windows absolute path — rejoin drive letter
            abs_path = f"{parts[0]}:{parts[1]}"
            try:
                rel_path = str(Path(abs_path).relative_to(project_path))
            except ValueError:
                rel_path = abs_path
        else:
            rel_path = parts[0]

        errors.setdefault(rel_path, []).append(line.strip())

    return errors


def _get_installed_package_names(installed_deps_str: str) -> set[str]:
    """Parse a dep-list string into a set of normalized package names."""
    names: set[str] = set()
    for line in installed_deps_str.splitlines():
        dep = (
            line.lstrip("- ")
            .split(">=")[0]
            .split("==")[0]
            .split("!=")[0]
            .split("<")[0]
            .split("[")[0]
            .strip()
        )
        if dep:
            names.add(dep.lower().replace("-", "_"))
    return names


def _install_missing_deps(
    project_path: Path,
    search_dir: Path,
    package_name: str,
    installed_deps: str,
) -> str:
    """Use pipreqs to detect and install packages missing from pyproject.toml.

    pipreqs resolves the import-name → PyPI-package-name mapping correctly
    (e.g. ``PIL`` → ``Pillow``) and ignores internal project modules.
    Returns an updated installed-deps string after any ``uv add`` calls.
    """
    installed = _get_installed_package_names(installed_deps)

    try:
        result = _run_cmd(
            ["uvx", "pipreqs", "--print", str(search_dir)],
            cwd=project_path,
            capture_output=True,
            check=False,
        )
    except Exception:
        return installed_deps

    missing: list[str] = []
    for raw in result.stdout.splitlines():
        line = raw.strip()
        # Skip blank lines, comments, and pipreqs log-level prefixes
        if not line or line.startswith(("#", "INFO", "WARNING", "ERROR")):
            continue
        # Extract the bare package name before any version specifier
        pkg_name = (
            line.split("==")[0]
            .split(">=")[0]
            .split("<=")[0]
            .split("!=")[0]
            .split(">")[0]
            .split("<")[0]
            .strip()
        )
        if not pkg_name or not pkg_name[0].isalpha():
            continue
        normalized = pkg_name.lower().replace("-", "_")
        if normalized != package_name.lower() and normalized not in installed:
            missing.append(pkg_name)

    if not missing:
        return installed_deps

    for pkg in sorted(set(missing)):
        _print_step(f"Installing missing package: {pkg}...")
        try:
            _run_cmd(["uv", "add", pkg], cwd=project_path)
            _print_ok(f"Installed: {pkg}")
        except subprocess.CalledProcessError:
            _print_warn(f"Could not install '{pkg}' — skipping.")

    return _get_pyproject_deps(project_path)


def _fix_code_errors_with_llm(
    project_path: Path,
    check_paths: list[str],
    installed_deps: str,
    model_provider: str,
    model: str,
    show_output: bool = False,
) -> None:
    """Use the LLM to fix non-auto-fixable ruff errors in the given paths."""
    fix_template = _load_prompt_template("fix_errors")
    if not fix_template:
        _print_warn("fix_errors template not found — skipping LLM error fixing.")
        return

    errors_by_file = _get_ruff_errors_by_file(project_path, check_paths)
    if not errors_by_file:
        return

    total = sum(len(v) for v in errors_by_file.values())
    _print_step(f"Fixing {total} non-auto-fixable error(s) with LLM...")

    for rel_path, file_errors in errors_by_file.items():
        full_path = project_path / rel_path
        if not full_path.exists():
            continue

        prompt = _render_template(
            fix_template,
            {
                "file_path": rel_path,
                "file_content": full_path.read_text(encoding="utf-8"),
                "errors": "\n".join(file_errors),
                "installed_deps": installed_deps,
            },
        )

        _print_step(f"Fixing {rel_path}...")
        fixed = _run_llm(prompt, model_provider, model, show_output=show_output)
        if not fixed.strip():
            _print_warn(f"LLM returned empty output for {rel_path}. Skipping.")
            continue

        # Strip potential markdown fences the LLM may add
        fixed_lines = fixed.splitlines()
        if fixed_lines and fixed_lines[0].startswith("```"):
            fixed_lines = fixed_lines[1:]
        if fixed_lines and fixed_lines[-1].strip() == "```":
            fixed_lines = fixed_lines[:-1]

        _write_file(full_path, "\n".join(fixed_lines))
        _print_ok(f"Fixed: {rel_path}")


# ---------------------------------------------------------------------------
# Scaffold helpers
# ---------------------------------------------------------------------------


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_claude_md(project_path: Path, spec: dict[str, Any]) -> None:
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
    _write_file(project_path / ".gitattributes", "* text=auto eol=lf\n")


def _write_pre_commit_config(project_path: Path) -> None:
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
    src = project_path / "src"
    pkg = src / package_name
    _ensure_directory(pkg)
    init_py = pkg / "__init__.py"
    if not init_py.exists():
        _write_file(init_py, f'"""{package_name} package"""\n')
    return pkg


def _update_pyproject_tools(project_path: Path) -> None:
    """Append ruff / pytest / mypy / bandit / vulture tool config if absent."""
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
    """Initialize git repository."""
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
    except Exception as e:
        _print_warn(f"Could not initialize git: {e}")


def _copy_docs(project_path: Path, spec_path: Path, doc_files: list[str]) -> None:
    """Copy documentation files referenced in the spec."""
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


# ---------------------------------------------------------------------------
# LLM runners
# ---------------------------------------------------------------------------


def _estimate_num_ctx(prompt: str, system_prompt: str = "") -> int:
    """Return the next power-of-2 context window that fits prompt + response budget."""
    # Rough estimate: 4 chars ≈ 1 token; reserve 4096 tokens for the response.
    tokens = (len(prompt) + len(system_prompt)) // 4 + 4096
    ctx = 4096
    while ctx < tokens:
        ctx *= 2
    return min(ctx, 131072)  # 128k upper bound


def _run_llm(
    prompt: str,
    model_provider: str,
    model: str,
    system_prompt: str = "",
    show_output: bool = False,
) -> str:
    """Dispatch to Claude or Ollama and return generated text.

    If *system_prompt* is empty the ``system.txt`` template is loaded
    automatically so both providers always receive identical instructions.
    """
    if not system_prompt:
        system_prompt = _load_prompt_template("system")
    if model_provider == "claude":
        return _run_claude(prompt, model, system_prompt, show_output)
    if model_provider == "ollama":
        return _run_ollama(prompt, model, system_prompt, show_output)
    raise ValueError(f"Unsupported model provider: {model_provider}")


def _run_claude(prompt: str, model: str, system_prompt: str, show_output: bool) -> str:
    """Call the Claude CLI (non-interactive --print mode) and return stdout."""
    cmd = ["claude", "--model", model, "--print"]
    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])
    proc = subprocess.run(
        cmd,
        input=prompt,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        _print_err(f"Claude CLI exited with code {proc.returncode}")
        if proc.stderr:
            _print_err(proc.stderr[:500])
    if show_output:
        print(proc.stdout)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
    return proc.stdout or ""


def _run_ollama(prompt: str, model: str, system_prompt: str, show_output: bool) -> str:
    """Call OllamaClient and return the response text.

    The context window is capped to the model's actual limit so we never
    request more tokens than the model supports.
    """
    client = OllamaClient(model=model)

    # Estimate required tokens, capped to what the model actually supports.
    estimated = _estimate_num_ctx(prompt, system_prompt)
    model_limit = client.model_context_length()
    num_ctx = min(estimated, model_limit)

    try:
        result = client.chat(user=prompt, system=system_prompt, num_ctx=num_ctx)
    except Exception as e:
        _print_err(f"Ollama request failed: {e}")
        return ""

    if show_output:
        print(result)
    return result


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _get_test_failure_summary(output: str) -> str:
    """Extract the most relevant lines from pytest output."""
    lines = output.split("\n")
    relevant = [
        line
        for line in lines
        if any(
            x in line
            for x in [
                "FAILED",
                "ERROR",
                "error:",
                "AssertionError",
                "Exception",
                "Traceback",
                "passed",
                "failed",
            ]
        )
    ]
    return "\n".join(relevant[:80]) if relevant else "\n".join(lines[:60])


def _get_repo_tree(project_path: Path, max_depth: int = 5) -> str:
    """Generate an ASCII directory tree."""
    exclude_dirs = {
        ".venv",
        ".git",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
    }

    def _tree_lines(path: Path, prefix: str = "", depth: int = 0) -> list[str]:
        if depth > max_depth:
            return []
        try:
            items = sorted(path.iterdir())
        except (PermissionError, OSError):
            return []

        items = [
            item
            for item in items
            if item.name not in exclude_dirs and not item.name.endswith(".egg-info")
        ]
        dirs = [item for item in items if item.is_dir()]
        files = [item for item in items if item.is_file()]
        ordered = dirs + files

        lines: list[str] = []
        for idx, item in enumerate(ordered):
            is_last = idx == len(ordered) - 1
            connector = "└── " if is_last else "├── "
            child_prefix = "    " if is_last else "│   "
            if item.is_dir():
                lines.append(f"{prefix}{connector}{item.name}/")
                lines.extend(_tree_lines(item, prefix + child_prefix, depth + 1))
            else:
                lines.append(f"{prefix}{connector}{item.name}")
        return lines

    return "\n".join([f"{project_path.name}/"] + _tree_lines(project_path))


def _generate_readme(
    project_path: Path, spec: dict[str, Any], package_name: str
) -> None:
    """Write a comprehensive README.md."""
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


def _format_code(project_path: Path) -> bool:
    """Run ruff check --fix then ruff format."""
    try:
        _run_cmd(
            ["uv", "run", "ruff", "check", ".", "--fix"],
            cwd=project_path,
            check=False,
        )
        _run_cmd(["uv", "run", "ruff", "format", "."], cwd=project_path, check=False)
        return True
    except Exception as e:
        _print_warn(f"Could not run ruff: {e}")
        return False


def _run_tests(project_path: Path) -> tuple[bool, str]:
    """Run pytest and return (passed, output)."""
    try:
        result = _run_cmd(
            ["uv", "run", "pytest", "-x", "--tb=short"],
            cwd=project_path,
            capture_output=True,
            check=False,
        )
        return result.returncode == 0, result.stdout
    except Exception as e:
        return False, str(e)


def _load_prompt_template(name: str) -> str:
    """Load a prompt template from the vibegen.prompts package."""
    try:
        from importlib import resources

        with resources.path("vibegen", "prompts") as p:
            prompt_file = p / f"{name}.txt"
            if prompt_file.exists():
                return prompt_file.read_text(encoding="utf-8")
    except Exception:
        pass

    script_dir = Path(__file__).parent
    prompt_file = script_dir / "prompts" / f"{name}.txt"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")

    return ""


# ---------------------------------------------------------------------------
# LLM output parsing
# ---------------------------------------------------------------------------


def _parse_generated_files(output: str) -> dict[str, str]:
    """Parse ``--- file: path ---`` blocks from LLM output."""
    files: dict[str, str] = {}
    lines = output.split("\n")
    current_file: str | None = None
    current_content: list[str] = []

    for line in lines:
        if line.strip().startswith("---") and line.strip().endswith("---"):
            trimmed = line.strip()
            if current_file and current_content:
                content = _clean_file_content(current_content)
                if content.strip():
                    files[current_file] = content

            if "file:" in trimmed:
                path_part = trimmed.replace("--- file:", "").replace("---", "").strip()
            else:
                path_part = trimmed.replace("---", "").strip()

            if path_part and not path_part.lower().startswith("end"):
                current_file = path_part
                current_content = []
        elif current_file:
            current_content.append(line)

    if current_file and current_content:
        content = _clean_file_content(current_content)
        if content.strip():
            files[current_file] = content

    return files


def _clean_file_content(lines: list[str]) -> str:
    """Strip markdown code fences and any narrative text after the closing fence."""
    result: list[str] = []
    in_code_block = False
    last_fence_was_closing = False

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code_block:
                in_code_block = False
                last_fence_was_closing = True
            else:
                if last_fence_was_closing:
                    result = []
                in_code_block = True
                last_fence_was_closing = False
            continue

        if (
            last_fence_was_closing
            and not in_code_block
            and stripped
            and not stripped.startswith(("```", "---"))
        ):
            break

        if in_code_block:
            result.append(line)
            last_fence_was_closing = False

    return "\n".join(result).rstrip("\n")


def _write_generated_files(project_path: Path, files: dict[str, str]) -> int:
    """Write generated files to the project with LF line endings."""
    count = 0
    for rel_path, content in files.items():
        dest = project_path / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        _write_file(dest, content)
        _print_ok(f"Generated: {rel_path}")
        count += 1
    return count


# ---------------------------------------------------------------------------
# Code generation pipeline
# ---------------------------------------------------------------------------


def _generate_code(
    project_path: Path,
    spec: dict[str, Any],
    package_name: str,
    model_provider: str,
    model: str,
    show_output: bool = False,
) -> bool:
    """Generate source code with LLM, then auto-fix and LLM-fix remaining errors."""
    _print_step("Planning implementation (module design phase)...")

    plan_template = _load_prompt_template("plan")
    code_template = _load_prompt_template("generate_code")

    if not plan_template or not code_template:
        _print_warn("Prompt templates not found. Skipping code generation.")
        return False

    repo_tree = _get_repo_tree(project_path)
    installed_deps = _get_pyproject_deps(project_path)
    constraints = (
        "- Use type hints on every function signature.\n"
        "- Use Google-style docstrings on public functions and classes.\n"
        "- Use Pydantic models for any structured data.\n"
        "- Use loguru for logging (never print()).\n"
        "- Handle all edge cases mentioned in the spec.\n"
        "- Keep functions focused and under 30 lines.\n"
        f"- Use absolute imports: from {package_name}.module import ...\n"
        "- Only use packages already listed in pyproject.toml dependencies.\n"
        "- Do NOT modify pyproject.toml."
    )

    plan_prompt = _render_template(
        plan_template,
        {
            "spec": spec["raw"],
            "repo_tree": repo_tree,
            "constraints": constraints,
            "package": package_name,
        },
    )

    _print_step("Planning with LLM...")
    plan_output = _run_llm(plan_prompt, model_provider, model, show_output=show_output)
    _print_ok("Planning complete")
    _write_file(project_path / "MODEL_OUTPUT_plan.txt", plan_output)

    code_prompt = _render_template(
        code_template,
        {
            "spec": spec["raw"],
            "repo_tree": repo_tree,
            "constraints": constraints,
            "package": package_name,
            "plan": plan_output,
        },
    )

    _print_step("Generating source code with LLM...")
    code_output = _run_llm(code_prompt, model_provider, model, show_output=show_output)
    _write_file(project_path / "MODEL_OUTPUT_code.txt", code_output)

    generated = _parse_generated_files(code_output)
    if not generated:
        _print_warn("No files were generated by LLM.")
        _print_warn(
            f"Raw output saved to MODEL_OUTPUT_code.txt ({len(code_output)} chars)"
        )
        return False

    count = _write_generated_files(project_path, generated)
    _print_ok(f"Generated {count} files")

    src_dir = project_path / "src" / package_name

    # Pass 1: auto-fix with ruff
    _print_step("Formatting generated code...")
    _format_code(project_path)

    # Pass 2: LLM-fix non-auto-fixable ruff errors in src/
    _fix_code_errors_with_llm(
        project_path, ["src/"], installed_deps, model_provider, model, show_output
    )

    # Pass 3: install missing packages (ruff can't detect these)
    installed_deps = _install_missing_deps(
        project_path,
        src_dir,
        package_name,
        installed_deps,
    )

    # Pass 4: re-format after all edits
    _format_code(project_path)

    try:
        _run_cmd(["git", "add", "-A"], cwd=project_path, check=False)
        _run_cmd(
            ["git", "commit", "-q", "-m", "feat: generate source code from spec"],
            cwd=project_path,
            check=False,
        )
    except Exception:
        pass

    return True


# ---------------------------------------------------------------------------
# Test generation pipeline
# ---------------------------------------------------------------------------


def _relocate_test_files(project_path: Path) -> None:
    """Move test files accidentally placed at the repo root into tests/."""
    tests_dir = project_path / "tests"

    for name in ("conftest.py",):
        root_file = project_path / name
        if root_file.exists():
            tests_dir.mkdir(exist_ok=True)
            target = tests_dir / name
            if not target.exists():
                _write_file(target, root_file.read_text(encoding="utf-8"))
                _print_ok(f"Relocated {name} → tests/{name}")
            root_file.unlink()

    for py_file in project_path.glob("test_*.py"):
        tests_dir.mkdir(exist_ok=True)
        target = tests_dir / py_file.name
        if not target.exists():
            _write_file(target, py_file.read_text(encoding="utf-8"))
            _print_ok(f"Relocated {py_file.name} → tests/{py_file.name}")
        py_file.unlink()


def _plan_tests(
    project_path: Path,
    spec: dict[str, Any],
    package_name: str,
    source_files: str,
    dependency_graph: str,
    installed_deps: str,
    model_provider: str,
    model: str,
    show_output: bool = False,
) -> str:
    """Phase 2: plan tests from the *actual* generated source code."""
    plan_tests_template = _load_prompt_template("plan_tests")
    if not plan_tests_template:
        return ""

    constraints = (
        "- Write tests using pytest only.\n"
        "- Cover normal cases, edge cases, and error paths.\n"
        f"- Use absolute imports: from {package_name}.module import ...\n"
        "- Never import from src/.\n"
        "- Only use packages listed in INSTALLED DEPENDENCIES."
    )

    prompt = _render_template(
        plan_tests_template,
        {
            "spec": spec["raw"],
            "source_files": source_files,
            "dependency_graph": dependency_graph,
            "installed_deps": installed_deps,
            "constraints": constraints,
            "package": package_name,
        },
    )

    _print_step("Planning tests (phase 2 — based on actual source code)...")
    test_plan = _run_llm(prompt, model_provider, model, show_output=show_output)
    _print_ok("Test plan complete")
    _write_file(project_path / "MODEL_OUTPUT_test_plan.txt", test_plan)
    return test_plan


def _generate_and_fix_tests(
    project_path: Path,
    spec: dict[str, Any],
    package_name: str,
    model_provider: str,
    model: str,
    max_fix_attempts: int = 3,
    show_output: bool = False,
) -> bool:
    """Plan tests from actual source, generate them, fix errors, then run pytest."""
    test_template = _load_prompt_template("write_tests")
    if not test_template:
        _print_warn("Test template not found. Skipping test generation.")
        return True

    src_dir = project_path / "src" / package_name
    if not src_dir.exists():
        _print_warn("No source directory found.")
        return True

    modules = [f for f in src_dir.rglob("*.py") if f.name != "__init__.py"]
    if not modules:
        _print_warn("No source modules found to test.")
        return True

    # Build shared context from the actual generated source
    source_files = _read_source_files(src_dir, project_path)
    dependency_graph = _build_dependency_graph(src_dir, package_name)
    installed_deps = _get_pyproject_deps(project_path)

    # Phase 2: derive a test plan from the real source code
    test_plan = _plan_tests(
        project_path,
        spec,
        package_name,
        source_files,
        dependency_graph,
        installed_deps,
        model_provider,
        model,
        show_output=show_output,
    )

    _print_step("Generating tests with LLM...")
    constraints = (
        f"Use pytest. Cover edge cases.\n"
        f"Only import from the installed package: "
        f"from {package_name}.module import ...\n"
        f"Never import from src/.\n"
        f"Only use packages listed in INSTALLED DEPENDENCIES."
    )

    for module in modules:
        rel_path = str(module.relative_to(project_path))
        test_prompt = _render_template(
            test_template,
            {
                "module_path": rel_path,
                "spec": spec["raw"],
                "constraints": constraints,
                "test_plan": test_plan,
                "source_files": source_files,
                "dependency_graph": dependency_graph,
                "installed_deps": installed_deps,
                "package": package_name,
            },
        )
        test_output = _run_llm(
            test_prompt, model_provider, model, show_output=show_output
        )
        generated = _parse_generated_files(test_output)
        _write_generated_files(project_path, generated)

    _print_ok("Tests generated")

    # Move any test files the LLM placed at the repo root into tests/
    _relocate_test_files(project_path)

    tests_dir = project_path / "tests"

    # Pass 1: auto-fix
    _format_code(project_path)

    # Pass 2: LLM-fix non-auto-fixable ruff errors in tests/
    _fix_code_errors_with_llm(
        project_path, ["tests/"], installed_deps, model_provider, model, show_output
    )

    # Pass 3: install missing packages in tests/
    if tests_dir.exists():
        installed_deps = _install_missing_deps(
            project_path,
            tests_dir,
            package_name,
            installed_deps,
        )

    # Pass 4: re-format after all edits
    _format_code(project_path)

    for attempt in range(1, max_fix_attempts + 1):
        _print_step(f"Running tests (attempt {attempt}/{max_fix_attempts})...")
        passed, output = _run_tests(project_path)
        if passed:
            _print_ok("All tests passing!")
            break
        if attempt >= max_fix_attempts:
            _print_warn("Max attempts reached. Some tests may still be failing.")
            print(output[-500:] if len(output) > 500 else output)
            break
        _print_warn("Tests failing. Attempting to fix...")
        if tests_dir.exists():
            installed_deps = _install_missing_deps(
                project_path,
                tests_dir,
                package_name,
                installed_deps,
            )
        _fix_code_errors_with_llm(
            project_path, ["tests/"], installed_deps, model_provider, model, show_output
        )
        _format_code(project_path)

    try:
        _run_cmd(["git", "add", "-A"], cwd=project_path, check=False)
        _run_cmd(
            ["git", "commit", "-q", "-m", "test: generate and fix tests"],
            cwd=project_path,
            check=False,
        )
    except Exception:
        pass

    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="vibegen - generate Python projects from a spec"
    )
    parser.add_argument("spec_file", nargs="?", help="Path to spec markdown file")
    parser.add_argument("--output-dir", default="", help="Output directory")
    parser.add_argument(
        "--repair", action="store_true", help="Repair an existing project"
    )
    parser.add_argument("--repo-path", default="", help="Path to repo to repair")
    parser.add_argument(
        "--max-fix-attempts", type=int, default=3, help="Max test fix iterations"
    )
    parser.add_argument(
        "--max-turns", type=int, default=30, help="Max LLM turns per step"
    )
    parser.add_argument(
        "--model-provider",
        choices=["claude", "ollama"],
        default="claude",
        help="Which LLM provider to use",
    )
    parser.add_argument(
        "--model", default="claude-sonnet-4-6", help="Model name to use"
    )
    parser.add_argument(
        "--skip-permissions", action="store_true", help="Skip permission checks"
    )
    parser.add_argument(
        "--show-output", action="store_true", help="Show full LLM output"
    )

    args = parser.parse_args(argv)

    if not args.spec_file and not args.repair:
        parser.print_help()
        return 0

    if args.repair:
        _print_step("Repair mode is planned for a future release.")
        _print_warn("For now, generate new projects with 'vibegen create <spec>'")
        return 1

    spec_path = Path(args.spec_file)
    if not spec_path.exists():
        _print_err(f"Spec file not found: {spec_path}")
        return 1

    spec = _parse_spec(spec_path)
    project_name = spec["project_name"]
    if not project_name:
        _print_err("Spec must include a '## Name' section.")
        return 1

    package_name = project_name.lower().replace("-", "_").replace(" ", "_")
    output_dir = (
        Path(args.output_dir) if args.output_dir else spec_path.parent / project_name
    )

    _print_step("Scaffolding project with uv...")
    if output_dir.exists() and any(output_dir.iterdir()):
        _print_warn(
            "Output directory already exists and is not empty. Proceeding anyway."
        )
    else:
        output_dir.mkdir(parents=True, exist_ok=True)

    try:
        _run_cmd(
            ["uv", "init", str(output_dir), "--lib", "--python", spec["python_version"]]
        )
    except subprocess.CalledProcessError as e:
        _print_err(f"Failed to scaffold project: {e}")
        return 1

    _ensure_package_dir(output_dir, package_name)
    _write_claude_md(output_dir, spec)
    _create_vscode_settings(output_dir)
    _write_gitignore(output_dir)
    _write_gitattributes(output_dir)
    _write_pre_commit_config(output_dir)
    _update_pyproject_tools(output_dir)
    _copy_docs(output_dir, spec_path, spec["doc_files"])
    _init_git(output_dir)
    _generate_readme(output_dir, spec, package_name)

    try:
        _run_cmd(["git", "add", "-A"], cwd=output_dir, check=False)
        _run_cmd(
            ["git", "commit", "-q", "-m", "chore: initial scaffold from vibegen"],
            cwd=output_dir,
            check=False,
        )
    except Exception:
        pass

    _print_ok("Project scaffold created")

    try:
        code_generated = _generate_code(
            output_dir,
            spec,
            package_name,
            args.model_provider,
            args.model,
            show_output=args.show_output,
        )

        if code_generated:
            _generate_and_fix_tests(
                output_dir,
                spec,
                package_name,
                args.model_provider,
                args.model,
                max_fix_attempts=args.max_fix_attempts,
                show_output=args.show_output,
            )
            _generate_readme(output_dir, spec, package_name)
            try:
                _run_cmd(["git", "add", "-A"], cwd=output_dir, check=False)
                _run_cmd(
                    [
                        "git",
                        "commit",
                        "-q",
                        "-m",
                        "docs: update README with final structure",
                    ],
                    cwd=output_dir,
                    check=False,
                )
            except Exception:
                pass

            _print_ok("Project generation complete!")
            _print_ok(f"Location: {output_dir}")
        else:
            _print_warn("Code generation skipped. Create source files manually.")

    except Exception as e:
        _print_warn(f"Code generation failed: {e}")
        _print_warn("Manual code generation may be required.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
