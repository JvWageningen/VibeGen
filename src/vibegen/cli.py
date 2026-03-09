"""Command-line interface for vibegen."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from .ollama_client import main as ollama_main


def _print_step(message: str) -> None:
    print(f"[STEP]  {message}")


def _print_ok(message: str) -> None:
    print(f"[OK]    {message}")


def _print_warn(message: str) -> None:
    print(f"[WARN]  {message}")


def _print_err(message: str) -> None:
    print(f"[ERR]   {message}", file=sys.stderr)


def _run_cmd(
    args: list[str],
    cwd: Optional[Path] = None,
    capture_output: bool = False,
    check: bool = True,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=capture_output,
        text=True,
        env=env,
        check=check,
    )


def _render_template(text: str, values: Dict[str, str]) -> str:
    # Simple non-recursive replacement of {{key}} placeholders.
    out = text
    for k, v in values.items():
        out = out.replace(f"{{{{{k}}}}}", v)
    return out


def _parse_spec(path: Path) -> Dict[str, Any]:
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

    # Extract usage/examples section
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


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_claude_md(project_path: Path, spec: Dict[str, Any]) -> None:
    description = spec.get("description", "")
    if not description:
        # Fallback: use description from raw spec if available
        for line in spec["raw"].splitlines():
            if line.startswith("## Description"):
                continue
            if line.startswith("## "):
                break
            if line.strip():
                description = line.strip()
                break

    content = f"""# {spec['project_name']}

## Project
{description}

## Tech Stack
- Python {spec['python_version']}, managed by `uv`
- Ruff for linting and formatting
- pytest for testing
- mypy for type checking

## Directory Map
- `src/{spec['project_name'].lower().replace('-', '_')}/` - main package
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
- Use absolute imports: `from {spec['project_name'].lower().replace('-', '_')}.module import ...`
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
    (project_path / "CLAUDE.md").write_text(content, encoding="utf-8")


def _create_vscode_settings(project_path: Path) -> None:
    vscode_dir = project_path / ".vscode"
    _ensure_directory(vscode_dir)
    settings = {
        "python.defaultInterpreterPath": "./.venv/Scripts/python.exe" if os.name == "nt" else "./.venv/bin/python",
        "python.analysis.typeCheckingMode": "strict",
        "[python]": {
            "editor.defaultFormatter": "charliermarsh.ruff",
            "editor.formatOnSave": True,
            "editor.codeActionsOnSave": {
                "source.fixAll.ruff": "explicit",
                "source.organizeImports.ruff": "explicit"
            }
        },
        "ruff.lint.args": ["--config=pyproject.toml"],
        "files.trimTrailingWhitespace": True,
        "files.insertFinalNewline": True,
        "files.eol": "\n"
    }

    (vscode_dir / "settings.json").write_text(json.dumps(settings, indent=2), encoding="utf-8")


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
    (project_path / ".gitignore").write_text(content, encoding="utf-8")


def _write_gitattributes(project_path: Path) -> None:
    (project_path / ".gitattributes").write_text("* text=auto eol=lf\n", encoding="utf-8")


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
    (project_path / ".pre-commit-config.yaml").write_text(content, encoding="utf-8")


def _ensure_package_dir(project_path: Path, package_name: str) -> Path:
    src = project_path / "src"
    pkg = src / package_name
    _ensure_directory(pkg)
    init_py = pkg / "__init__.py"
    if not init_py.exists():
        init_py.write_text(f'"""{package_name} package"""\n', encoding="utf-8")
    return pkg


def _update_pyproject_tools(project_path: Path) -> None:
    """Add tool configurations for ruff, pytest, mypy, bandit, and vulture."""
    pyproject_path = project_path / "pyproject.toml"
    if not pyproject_path.exists():
        return

    text = pyproject_path.read_text(encoding="utf-8")

    # Check if tools are already configured
    if "[tool.ruff]" in text:
        return  # Already configured

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

    text += tool_config
    pyproject_path.write_text(text, encoding="utf-8")


def _init_git(project_path: Path) -> None:
    """Initialize git repository."""
    try:
        _run_cmd(["git", "init"], cwd=project_path, check=False)
        _run_cmd(["git", "config", "user.email", "vibegen@example.com"], cwd=project_path, check=False)
        _run_cmd(["git", "config", "user.name", "VibeGen"], cwd=project_path, check=False)
        _run_cmd(["git", "add", "-A"], cwd=project_path, check=False)
        _run_cmd(["git", "commit", "-q", "-m", "chore: initial scaffold from vibegen"], cwd=project_path, check=False)
        _print_ok("Git initialized")
    except Exception as e:
        _print_warn(f"Could not initialize git: {e}")


def _copy_docs(project_path: Path, spec_path: Path, doc_files: list[str]) -> None:
    """Copy documentation files from spec directory."""
    if not doc_files:
        return

    spec_dir = spec_path.parent
    docs_dir = project_path / "docs"
    _ensure_directory(docs_dir)

    for doc_file in doc_files:
        full_path = spec_dir / doc_file
        if full_path.exists():
            dest = docs_dir / Path(doc_file).name
            dest.write_text(full_path.read_text(encoding="utf-8"), encoding="utf-8")
            _print_ok(f"Loaded: {doc_file}")
        else:
            _print_warn(f"Documentation file not found: {full_path}")


def _run_llm(
    prompt: str,
    model_provider: str,
    model: str,
    system_prompt: str = "",
    show_output: bool = False,
) -> str:
    """Run Claude or Ollama to generate content."""
    if model_provider == "claude":
        # Use claude CLI
        cmd = ["claude", "--model", model, "--stream"]
        proc = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            capture_output=True,
            check=False,
        )
        if show_output:
            print(proc.stdout)
            if proc.stderr:
                print(proc.stderr, file=sys.stderr)
        return proc.stdout or ""
    elif model_provider == "ollama":
        # Use ollama_client directly (not via subprocess to avoid module import issues)
        try:
            import io
            from contextlib import redirect_stdout, redirect_stderr

            # Capture output from ollama_client
            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()

            # Prepare args
            ollama_args = ["--model", model]
            if system_prompt:
                ollama_args.extend(["--system", system_prompt])
            ollama_args.extend(["--user", prompt])

            # Call ollama_main directly
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                exit_code = ollama_main(ollama_args)

            stdout_content = stdout_capture.getvalue()
            stderr_content = stderr_capture.getvalue()

            if show_output or exit_code != 0:
                if stdout_content:
                    print(stdout_content)
                if stderr_content:
                    print(stderr_content, file=sys.stderr)

            if exit_code != 0:
                _print_err(f"Ollama client exit code: {exit_code}")
                return ""

            return stdout_content or ""

        except Exception as e:
            _print_err(f"Failed to call Ollama: {e}")
            return ""
    else:
        raise ValueError(f"Unsupported model provider: {model_provider}")


def _get_test_failure_summary(output: str) -> str:
    """Extract relevant test failure lines from pytest output."""
    lines = output.split("\n")
    relevant = [
        line for line in lines
        if any(x in line for x in ["FAILED", "ERROR", "error:", "AssertionError", "Exception", "Traceback", "passed", "failed"])
    ]
    if not relevant:
        return "\n".join(lines[:60])
    return "\n".join(relevant[:80])


def _get_repo_tree(project_path: Path, max_depth: int = 5) -> str:
    """Generate ASCII directory tree."""
    exclude_dirs = {".venv", ".git", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build"}

    def _tree_lines(path: Path, prefix: str = "", depth: int = 0) -> list[str]:
        if depth > max_depth:
            return []

        try:
            items = sorted(path.iterdir())
        except (PermissionError, OSError):
            return []

        items = [
            item for item in items
            if item.name not in exclude_dirs and not item.name.endswith(".egg-info")
        ]

        dirs = [item for item in items if item.is_dir()]
        files = [item for item in items if item.is_file()]
        ordered = dirs + files

        lines = []
        for i, item in enumerate(ordered):
            is_last = i == len(ordered) - 1
            connector = "└── " if is_last else "├── "
            child_prefix = "    " if is_last else "│   "

            if item.is_dir():
                lines.append(f"{prefix}{connector}{item.name}/")
                lines.extend(_tree_lines(item, prefix + child_prefix, depth + 1))
            else:
                lines.append(f"{prefix}{connector}{item.name}")

        return lines

    root_name = project_path.name
    lines = [f"{root_name}/"] + _tree_lines(project_path)
    return "\n".join(lines)


def _generate_readme(project_path: Path, spec: Dict[str, Any], package_name: str) -> None:
    """Generate a comprehensive README."""
    description = spec.get("description", "")
    usage = spec.get("usage", "See the documentation for usage details.")
    repo_slug = spec["project_name"].lower().replace(" ", "-").replace("_", "-")

    # Get list of source files
    src_dir = project_path / "src" / package_name
    py_files = []
    if src_dir.exists():
        for py_file in sorted(src_dir.rglob("*.py")):
            if py_file.name != "__init__.py":
                rel_path = py_file.relative_to(project_path / "src")
                py_files.append(f"  - `{rel_path}`")

    py_files_section = "\n".join(py_files) if py_files else "  - (generated source files)"

    content = f"""# {spec['project_name']}

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
    (project_path / "README.md").write_text(content, encoding="utf-8")


def _format_code(project_path: Path) -> bool:
    """Run ruff check and format."""
    try:
        _run_cmd(["uv", "run", "ruff", "check", ".", "--fix"], cwd=project_path, check=False)
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
            check=False
        )
        passed = result.returncode == 0
        return passed, result.stdout
    except Exception as e:
        return False, str(e)


def _load_prompt_template(name: str) -> str:
    """Load a prompt template from package resources."""
    try:
        from importlib import resources
        with resources.path("vibegen", "prompts") as p:
            prompt_file = p / f"{name}.txt"
            if prompt_file.exists():
                return prompt_file.read_text(encoding="utf-8")
    except Exception:
        pass

    # Fallback: try relative to script
    script_dir = Path(__file__).parent
    prompt_file = script_dir / "prompts" / f"{name}.txt"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")

    return ""


def _parse_generated_files(output: str) -> Dict[str, str]:
    """Parse --- file: path --- blocks from LLM output, cleaning up narrative text."""
    files: Dict[str, str] = {}
    lines = output.split("\n")
    current_file: Optional[str] = None
    current_content: list[str] = []

    for i, line in enumerate(lines):
        # Match "--- file: path ---" format
        if line.strip().startswith("---") and line.strip().endswith("---"):
            trimmed = line.strip()
            # Save previous file
            if current_file and current_content:
                content = _clean_file_content(current_content)
                if content.strip():
                    files[current_file] = content

            # Extract path
            if "file:" in trimmed:
                path_part = trimmed.replace("--- file:", "").replace("---", "").strip()
            else:
                path_part = trimmed.replace("---", "").strip()

            if path_part and not path_part.lower().startswith("end"):
                current_file = path_part
                current_content = []
        elif current_file:
            current_content.append(line)

    # Save last file
    if current_file and current_content:
        content = _clean_file_content(current_content)
        if content.strip():
            files[current_file] = content

    return files


def _clean_file_content(lines: list[str]) -> str:
    """Clean file content by stripping markdown code fences and narrative text after closing fence."""
    result: list[str] = []
    in_code_block = False
    last_fence_was_closing = False

    for line in lines:
        stripped = line.strip()

        # Check for code fence
        if stripped.startswith("```"):
            if in_code_block:
                # Closing fence
                in_code_block = False
                last_fence_was_closing = True
            else:
                # Opening fence
                if last_fence_was_closing:
                    # This shouldn't happen normally
                    result = []
                in_code_block = True
                last_fence_was_closing = False
            continue  # Don't include fence lines

        # If we just closed a fence and encounter non-code content, stop capturing
        if last_fence_was_closing and not in_code_block and line.strip():
            # Text after the code block - likely narrative, so stop here
            if not line.strip().startswith(("```", "---")):
                break

        if in_code_block:
            result.append(line)
            last_fence_was_closing = False

    return "\n".join(result).rstrip("\n")


def _write_generated_files(project_path: Path, files: Dict[str, str]) -> int:
    """Write generated files to project."""
    count = 0
    for rel_path, content in files.items():
        dest = project_path / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        _print_ok(f"Generated: {rel_path}")
        count += 1
    return count


def _generate_code(
    project_path: Path,
    spec: Dict[str, Any],
    package_name: str,
    model_provider: str,
    model: str,
    show_output: bool = False,
) -> bool:
    """Generate source code and tests using LLM."""
    _print_step("Planning implementation (module design phase)...")

    # Load prompts
    plan_template = _load_prompt_template("plan")
    code_template = _load_prompt_template("generate_code")
    test_template = _load_prompt_template("write_tests")

    if not plan_template or not code_template:
        _print_warn("Prompt templates not found. Skipping code generation.")
        return False

    # Generate plan
    repo_tree = _get_repo_tree(project_path)
    constraints = (
        "- Use type hints on every function signature.\n"
        "- Use Google-style docstrings on public functions and classes.\n"
        "- Use Pydantic models for any structured data.\n"
        "- Use loguru for logging (never print()).\n"
        "- Handle all edge cases mentioned in the spec.\n"
        "- Keep functions focused and under 30 lines.\n"
        f"- Use absolute imports: from {package_name}.module import ...\n"
        "- Do NOT modify pyproject.toml dependencies."
    )

    plan_prompt = _render_template(plan_template, {
        "spec": spec["raw"],
        "repo_tree": repo_tree,
        "constraints": constraints,
        "package": package_name,
    })

    _print_step("Planning with LLM...")
    plan_output = _run_llm(plan_prompt, model_provider, model, show_output=show_output)
    _print_ok("Planning complete")

    # Save plan for debugging
    (project_path / "MODEL_OUTPUT_plan.txt").write_text(plan_output, encoding="utf-8")

    # Generate code
    code_prompt = _render_template(code_template, {
        "spec": spec["raw"],
        "repo_tree": repo_tree,
        "constraints": constraints,
        "package": package_name,
        "plan": plan_output,
    })

    _print_step("Generating source code with LLM...")
    code_output = _run_llm(code_prompt, model_provider, model, show_output=show_output)

    # Save raw output for debugging
    (project_path / "MODEL_OUTPUT_code.txt").write_text(code_output, encoding="utf-8")

    # Parse and write generated files
    generated = _parse_generated_files(code_output)
    if not generated:
        _print_warn("No files were generated by LLM.")
        _print_warn(f"Raw output saved to MODEL_OUTPUT_code.txt ({len(code_output)} chars)")
        return False

    count = _write_generated_files(project_path, generated)
    _print_ok(f"Generated {count} files")

    # Format code
    _print_step("Formatting generated code...")
    _format_code(project_path)

    # Commit
    try:
        _run_cmd(["git", "add", "-A"], cwd=project_path, check=False)
        _run_cmd(["git", "commit", "-q", "-m", "feat: generate source code from spec"], cwd=project_path, check=False)
    except Exception:
        pass

    return True


def _generate_and_fix_tests(
    project_path: Path,
    spec: Dict[str, Any],
    package_name: str,
    model_provider: str,
    model: str,
    max_fix_attempts: int = 3,
    show_output: bool = False,
) -> bool:
    """Generate tests and fix failing ones."""
    test_template = _load_prompt_template("write_tests")
    if not test_template:
        _print_warn("Test template not found. Skipping test generation.")
        return True  # Not critical

    _print_step("Generating tests with LLM...")

    # Find source modules
    src_dir = project_path / "src" / package_name
    if not src_dir.exists():
        _print_warn("No source files found.")
        return True

    modules = [f for f in src_dir.rglob("*.py") if f.name != "__init__.py"]
    if not modules:
        _print_warn("No source modules found to test.")
        return True

    for module in modules:
        rel_path = str(module.relative_to(project_path))
        test_prompt = _render_template(test_template, {
            "module_path": rel_path,
            "spec": spec["raw"],
            "constraints": "Use pytest. Cover edge cases. Import from installed package only.",
        })

        test_output = _run_llm(test_prompt, model_provider, model, show_output=show_output)
        generated = _parse_generated_files(test_output)
        _write_generated_files(project_path, generated)

    _print_ok("Tests generated")

    # Format and run tests
    _format_code(project_path)

    for attempt in range(1, max_fix_attempts + 1):
        _print_step(f"Running tests (attempt {attempt}/{max_fix_attempts})...")

        passed, output = _run_tests(project_path)
        if passed:
            _print_ok("All tests passing!")
            break

        if attempt >= max_fix_attempts:
            _print_warn(f"Max attempts reached. Some tests may still be failing.")
            print(output[-500:] if len(output) > 500 else output)
            break

        _print_warn("Tests failing. Attempting to fix...")
        # For now, just re-run ruff - more sophisticated fixing would require LLM
        _format_code(project_path)

    # Commit
    try:
        _run_cmd(["git", "add", "-A"], cwd=project_path, check=False)
        _run_cmd(["git", "commit", "-q", "-m", "test: generate and fix tests"], cwd=project_path, check=False)
    except Exception:
        pass

    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="vibegen - generate Python projects from a spec")
    parser.add_argument("spec_file", nargs="?", help="Path to spec markdown file")
    parser.add_argument("--output-dir", default="", help="Output directory")
    parser.add_argument("--repair", action="store_true", help="Repair an existing project")
    parser.add_argument("--repo-path", default="", help="Path to repo to repair")
    parser.add_argument("--max-fix-attempts", type=int, default=3, help="Max test fix iterations")
    parser.add_argument("--max-turns", type=int, default=30, help="Max LLM turns per step")
    parser.add_argument(
        "--model-provider",
        choices=["claude", "ollama"],
        default="claude",
        help="Which LLM provider to use",
    )
    parser.add_argument("--model", default="claude-sonnet-4-6", help="Model name to use")
    parser.add_argument("--skip-permissions", action="store_true", help="Skip permission checks")
    parser.add_argument("--show-output", action="store_true", help="Show full LLM output")

    args = parser.parse_args(argv)

    if not args.spec_file and not args.repair:
        parser.print_help()
        return 0

    if args.repair:
        _print_step("Repair mode is not yet fully implemented in the Python version.")
        _print_warn("Use vibegen.ps1 for repair mode with full features.")
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

    # Convert project name to valid Python package name
    package_name = project_name.lower().replace("-", "_").replace(" ", "_")

    output_dir = Path(args.output_dir) if args.output_dir else spec_path.parent / project_name

    _print_step("Scaffolding project with uv...")
    if output_dir.exists() and any(output_dir.iterdir()):
        _print_warn("Output directory already exists and is not empty. Proceeding anyway.")
    else:
        output_dir.mkdir(parents=True, exist_ok=True)

    try:
        _run_cmd(["uv", "init", str(output_dir), "--lib", "--python", spec["python_version"]])
    except subprocess.CalledProcessError as e:
        _print_err(f"Failed to scaffold project: {e}")
        return 1

    # Create package directory and files
    _ensure_package_dir(output_dir, package_name)
    _write_claude_md(output_dir, spec)
    _create_vscode_settings(output_dir)
    _write_gitignore(output_dir)
    _write_gitattributes(output_dir)
    _write_pre_commit_config(output_dir)
    _update_pyproject_tools(output_dir)

    # Copy documentation files
    _copy_docs(output_dir, spec_path, spec["doc_files"])

    # Initialize git
    _init_git(output_dir)

    # Generate README (initial version)
    _generate_readme(output_dir, spec, package_name)

    # Commit initial files
    try:
        _run_cmd(["git", "add", "-A"], cwd=output_dir, check=False)
        _run_cmd(["git", "commit", "-q", "-m", "chore: initial scaffold from vibegen"], cwd=output_dir, check=False)
    except Exception:
        pass

    _print_ok("Project scaffold created")

    # Generate code and tests (requires LLM)
    try:
        code_generated = _generate_code(
            output_dir, spec, package_name,
            args.model_provider, args.model,
            show_output=args.show_output
        )

        if code_generated:
            _generate_and_fix_tests(
                output_dir, spec, package_name,
                args.model_provider, args.model,
                max_fix_attempts=args.max_fix_attempts,
                show_output=args.show_output
            )

            # Final README update with generated structure
            _generate_readme(output_dir, spec, package_name)
            try:
                _run_cmd(["git", "add", "-A"], cwd=output_dir, check=False)
                _run_cmd(["git", "commit", "-q", "-m", "docs: update README with final structure"], cwd=output_dir, check=False)
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

