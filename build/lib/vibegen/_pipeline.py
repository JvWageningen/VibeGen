"""Code and test generation pipeline."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from ._analysis import (
    _build_dependency_graph,
    _get_installed_package_names,
    _get_pyproject_deps,
    _get_repo_tree,
    _read_source_files,
)
from ._io import _print_ok, _print_step, _print_warn, _run_cmd, _write_file
from ._llm import _load_prompt_template, _render_template, _run_llm
from ._output_parser import _parse_generated_files, _write_generated_files
from .sandbox import SandboxConfig
from .web_search import web_search

# ---------------------------------------------------------------------------
# Code quality helpers
# ---------------------------------------------------------------------------


def _format_code(project_path: Path, sandbox: SandboxConfig | None = None) -> bool:
    """Run ``ruff check --fix`` then ``ruff format``.

    Args:
        project_path: Project root directory.
        sandbox: Optional Docker sandbox config.

    Returns:
        True on success, False if ruff raised an unexpected exception.
    """
    try:
        _run_cmd(
            ["uv", "run", "ruff", "check", ".", "--fix"],
            cwd=project_path,
            capture_output=True,
            check=False,
            sandbox=sandbox,
        )
        _run_cmd(
            ["uv", "run", "ruff", "format", "."],
            cwd=project_path,
            capture_output=True,
            check=False,
            sandbox=sandbox,
        )
        return True
    except Exception as e:  # noqa: BLE001
        _print_warn(f"Could not run ruff: {e}")
        return False


def _run_tests(
    project_path: Path, sandbox: SandboxConfig | None = None
) -> tuple[bool, str]:
    """Run pytest and return ``(passed, output)``.

    Args:
        project_path: Project root directory.
        sandbox: Optional Docker sandbox config.

    Returns:
        Tuple of (all tests passed, combined stdout).
    """
    try:
        result = _run_cmd(
            ["uv", "run", "pytest", "-x", "--tb=short"],
            cwd=project_path,
            capture_output=True,
            check=False,
            sandbox=sandbox,
        )
        return result.returncode == 0, result.stdout
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _get_ruff_errors_by_file(
    project_path: Path,
    check_paths: list[str],
    sandbox: SandboxConfig | None = None,
) -> dict[str, list[str]]:
    """Run ruff and return non-auto-fixable errors grouped by relative file path.

    E501 (line-too-long) errors are filtered out because ``ruff format``
    handles them silently.

    Args:
        project_path: Project root directory.
        check_paths: Paths to pass to ruff (e.g. ``["src/"]``).
        sandbox: Optional Docker sandbox config.

    Returns:
        Dict mapping relative file path to list of error strings.
    """
    try:
        result = _run_cmd(
            ["uv", "run", "ruff", "check", "--output-format=concise"] + check_paths,
            cwd=project_path,
            capture_output=True,
            check=False,
            sandbox=sandbox,
        )
    except Exception:  # noqa: BLE001
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
            abs_path = f"{parts[0]}:{parts[1]}"
            try:
                rel_path = str(Path(abs_path).relative_to(project_path))
            except ValueError:
                rel_path = abs_path
        else:
            rel_path = parts[0]

        errors.setdefault(rel_path, []).append(line.strip())

    return errors


def _install_missing_deps(
    project_path: Path,
    search_dir: Path,
    package_name: str,
    installed_deps: str,
    sandbox: SandboxConfig | None = None,
) -> str:
    """Use pipreqs to detect and install packages missing from pyproject.toml.

    pipreqs resolves the import-name → PyPI-package-name mapping correctly
    (e.g. ``PIL`` → ``Pillow``) and ignores internal project modules.

    Args:
        project_path: Project root directory.
        search_dir: Directory to scan for imports (src or tests).
        package_name: The project's own package name (excluded from installs).
        installed_deps: Current installed-deps string from
            :func:`_get_pyproject_deps`.
        sandbox: Optional Docker sandbox config.

    Returns:
        Updated installed-deps string after any ``uv add`` calls.
    """
    installed = _get_installed_package_names(installed_deps)

    try:
        result = _run_cmd(
            ["uvx", "pipreqs", "--print", str(search_dir)],
            cwd=project_path,
            capture_output=True,
            check=False,
            sandbox=sandbox,
        )
    except Exception:  # noqa: BLE001
        return installed_deps

    missing: list[str] = []
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", "INFO", "WARNING", "ERROR")):
            continue
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
            _run_cmd(["uv", "add", pkg], cwd=project_path, sandbox=sandbox)
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
    web_context: str = "",
    sandbox: SandboxConfig | None = None,
) -> None:
    """Use the LLM to fix non-auto-fixable ruff errors in the given paths.

    Args:
        project_path: Project root directory.
        check_paths: Paths to check with ruff.
        installed_deps: Installed-deps string for context.
        model_provider: ``"claude"`` or ``"ollama"``.
        model: Model identifier.
        show_output: Print LLM output when True.
        web_context: Optional web-search results to prepend to the prompt.
        sandbox: Optional Docker sandbox config.
    """
    fix_template = _load_prompt_template("fix_errors")
    if not fix_template:
        _print_warn("fix_errors template not found — skipping LLM error fixing.")
        return

    errors_by_file = _get_ruff_errors_by_file(
        project_path, check_paths, sandbox=sandbox
    )
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
                "web_context": web_context,
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

        fixed_lines = fixed.splitlines()
        if fixed_lines and fixed_lines[0].startswith("```"):
            fixed_lines = fixed_lines[1:]
        if fixed_lines and fixed_lines[-1].strip() == "```":
            fixed_lines = fixed_lines[:-1]

        _write_file(full_path, "\n".join(fixed_lines))
        _print_ok(f"Fixed: {rel_path}")


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
    sandbox: SandboxConfig | None = None,
) -> bool:
    """Generate source code with LLM, then auto-fix and LLM-fix remaining errors.

    Args:
        project_path: Project root directory.
        spec: Parsed spec dict.
        package_name: Python package name (snake_case).
        model_provider: ``"claude"`` or ``"ollama"``.
        model: Model identifier.
        show_output: Print LLM output when True.
        sandbox: Optional Docker sandbox config.

    Returns:
        True if source files were generated, False otherwise.
    """
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
    _format_code(project_path, sandbox=sandbox)

    # Pass 2: LLM-fix non-auto-fixable ruff errors in src/
    _fix_code_errors_with_llm(
        project_path,
        ["src/"],
        installed_deps,
        model_provider,
        model,
        show_output,
        sandbox=sandbox,
    )

    # Pass 3: install missing packages (ruff can't detect these)
    installed_deps = _install_missing_deps(
        project_path,
        src_dir,
        package_name,
        installed_deps,
        sandbox=sandbox,
    )

    # Pass 4: re-format after all edits
    _format_code(project_path, sandbox=sandbox)

    try:
        _run_cmd(["git", "add", "-A"], cwd=project_path, check=False)
        _run_cmd(
            ["git", "commit", "-q", "-m", "feat: generate source code from spec"],
            cwd=project_path,
            check=False,
        )
    except Exception:  # noqa: BLE001
        pass

    return True


# ---------------------------------------------------------------------------
# Test generation pipeline
# ---------------------------------------------------------------------------


def _relocate_test_files(project_path: Path) -> None:
    """Move test files accidentally placed at the repo root into ``tests/``.

    Args:
        project_path: Project root directory.
    """
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
    """Derive a test plan from the actual generated source code.

    Args:
        project_path: Project root directory.
        spec: Parsed spec dict.
        package_name: Python package name.
        source_files: Combined source file content string.
        dependency_graph: Dependency graph string.
        installed_deps: Installed-deps string.
        model_provider: ``"claude"`` or ``"ollama"``.
        model: Model identifier.
        show_output: Print LLM output when True.

    Returns:
        Test plan text from the LLM.
    """
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


def _parse_pytest_failures(output: str) -> dict[str, str]:
    """Extract per-test-file failure blocks from pytest ``--tb=short`` output.

    First pass: find all ``FAILED``/``ERROR`` summary lines to identify which
    files have failures.  Second pass: split the output on ``_ test_name ___``
    dividers and map each block to the file it references.

    Args:
        output: Full pytest stdout.

    Returns:
        Dict mapping relative test-file path (forward-slash) to the combined
        error text for that file.
    """
    lines = output.splitlines()

    # Pass 1: collect failing file paths from the summary section.
    failing_files: dict[str, list[str]] = {}
    for line in lines:
        for prefix in ("FAILED ", "ERROR "):
            if line.startswith(prefix):
                node = line[len(prefix) :].split(" - ")[0].strip()
                file_path = node.split("::")[0].replace("\\", "/")
                failing_files.setdefault(file_path, []).append(line)

    if not failing_files:
        return {}

    # Pass 2: split output into traceback blocks and map to files.
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line.startswith("_ ") and line.rstrip().endswith("_") and len(line) > 6:
            if current:
                blocks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(current)

    file_blocks: dict[str, list[str]] = {f: [] for f in failing_files}
    for block in blocks:
        block_text = "\n".join(block)
        for file_path in failing_files:
            alt_path = file_path.replace("/", "\\")
            if file_path in block_text or alt_path in block_text:
                file_blocks[file_path].extend(block)

    result: dict[str, str] = {}
    for file_path, summary_lines in failing_files.items():
        parts = file_blocks.get(file_path, []) + summary_lines
        if parts:
            result[file_path] = "\n".join(parts)
    return result


def _fix_pytest_failures_with_llm(
    project_path: Path,
    failures: dict[str, str],
    src_dir: Path,
    package_name: str,
    installed_deps: str,
    model_provider: str,
    model: str,
    show_output: bool = False,
    web_context: str = "",
    sandbox: SandboxConfig | None = None,
) -> None:
    """Fix each failing test file individually using the LLM.

    For every file in *failures*, this function:
    1. Builds a focused prompt with that file's error block and source context.
    2. Calls the LLM to fix the test file.
    3. Writes the fixed content back.
    4. Runs ruff auto-fix on the project immediately after each edit.

    Args:
        project_path: Project root directory.
        failures: Mapping from relative test-file path to error text
            (from :func:`_parse_pytest_failures`).
        src_dir: Source package directory (used to build source context).
        package_name: Python package name.
        installed_deps: Installed-deps string for context.
        model_provider: ``"claude"`` or ``"ollama"``.
        model: Model identifier.
        show_output: Print LLM output when True.
        web_context: Optional web-search results to prepend to the error log.
        sandbox: Optional Docker sandbox config.
    """
    fix_tests_template = _load_prompt_template("fix_tests")
    if not fix_tests_template:
        _print_warn("fix_tests template not found — skipping pytest failure fixes.")
        return

    repo_tree = _get_repo_tree(project_path)
    dep_graph = _build_dependency_graph(src_dir, package_name)
    source_context = _read_source_files(src_dir, project_path)

    for rel_path, error_block in failures.items():
        full_path = project_path / rel_path
        if not full_path.exists():
            _print_warn(f"Test file not found: {rel_path}")
            continue

        test_content = full_path.read_text(encoding="utf-8")
        source = (
            f"{source_context}\n\n"
            f"=== {rel_path} (TEST FILE TO FIX) ===\n{test_content}"
        )
        error_log = f"{web_context}\n\n{error_block}" if web_context else error_block

        prompt = _render_template(
            fix_tests_template,
            {
                "error_log": error_log,
                "repo_tree": repo_tree,
                "dep_graph": dep_graph,
                "source": source,
            },
        )

        _print_step(f"Fixing failing tests in {rel_path}...")
        fixed_output = _run_llm(
            prompt, model_provider, model, show_output=show_output
        )

        if not fixed_output.strip():
            _print_warn(f"LLM returned empty output for {rel_path}. Skipping.")
            continue

        fixed_files = _parse_generated_files(fixed_output)
        if fixed_files:
            _write_generated_files(project_path, fixed_files)
        else:
            # LLM returned raw code — apply to the target file directly.
            fixed_lines = fixed_output.splitlines()
            if fixed_lines and fixed_lines[0].startswith("```"):
                fixed_lines = fixed_lines[1:]
            if fixed_lines and fixed_lines[-1].strip() == "```":
                fixed_lines = fixed_lines[:-1]
            _write_file(full_path, "\n".join(fixed_lines))
            _print_ok(f"Fixed: {rel_path}")

        # Immediately ruff-format so the next iteration sees clean code.
        _format_code(project_path, sandbox=sandbox)


def _generate_and_fix_tests(
    project_path: Path,
    spec: dict[str, Any],
    package_name: str,
    model_provider: str,
    model: str,
    max_fix_attempts: int = 3,
    show_output: bool = False,
    sandbox: SandboxConfig | None = None,
) -> bool:
    """Plan tests from actual source, generate them, fix errors, then run pytest.

    Args:
        project_path: Project root directory.
        spec: Parsed spec dict.
        package_name: Python package name.
        model_provider: ``"claude"`` or ``"ollama"``.
        model: Model identifier.
        max_fix_attempts: Number of test-fix retry cycles.
        show_output: Print LLM output when True.
        sandbox: Optional Docker sandbox config.

    Returns:
        True (always; failures are reported via warnings).
    """
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

    source_files = _read_source_files(src_dir, project_path)
    dependency_graph = _build_dependency_graph(src_dir, package_name)
    installed_deps = _get_pyproject_deps(project_path)

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
    _relocate_test_files(project_path)

    tests_dir = project_path / "tests"

    # Pass 1: auto-fix
    _format_code(project_path, sandbox=sandbox)

    # Pass 2: LLM-fix non-auto-fixable ruff errors in tests/
    _fix_code_errors_with_llm(
        project_path,
        ["tests/"],
        installed_deps,
        model_provider,
        model,
        show_output,
        sandbox=sandbox,
    )

    # Pass 3: install missing packages in tests/
    if tests_dir.exists():
        installed_deps = _install_missing_deps(
            project_path,
            tests_dir,
            package_name,
            installed_deps,
            sandbox=sandbox,
        )

    # Pass 4: re-format after all edits
    _format_code(project_path, sandbox=sandbox)

    for attempt in range(1, max_fix_attempts + 1):
        _print_step(f"Running tests (attempt {attempt}/{max_fix_attempts})...")
        passed, output = _run_tests(project_path, sandbox=sandbox)
        if passed:
            _print_ok("All tests passing!")
            break
        if attempt >= max_fix_attempts:
            _print_warn("Max attempts reached. Some tests may still be failing.")
            print(output[-500:] if len(output) > 500 else output)
            break
        _print_warn("Tests failing. Attempting to fix...")

        # From the 2nd failed attempt onwards, enrich context with a web search.
        web_ctx = ""
        if attempt >= 2:
            first_error = next(
                (
                    line.strip()
                    for line in output.splitlines()
                    if any(
                        tag in line
                        for tag in ("ERROR", "error:", "Exception", "AssertionError")
                    )
                ),
                "",
            )
            if first_error:
                _print_step(f"Searching web for: {first_error[:80]}...")
                web_ctx = web_search(f"python pytest {first_error[:120]}")

        # Step 1: install any newly required packages.
        if tests_dir.exists():
            installed_deps = _install_missing_deps(
                project_path,
                tests_dir,
                package_name,
                installed_deps,
                sandbox=sandbox,
            )

        # Step 2: ruff fixes first — handles imports, style, auto-fixable errors.
        _fix_code_errors_with_llm(
            project_path,
            ["tests/"],
            installed_deps,
            model_provider,
            model,
            show_output,
            sandbox=sandbox,
        )
        _format_code(project_path, sandbox=sandbox)

        # Step 3: fix each failing test file individually with the LLM.
        failures = _parse_pytest_failures(output)
        if failures:
            _fix_pytest_failures_with_llm(
                project_path,
                failures,
                src_dir,
                package_name,
                installed_deps,
                model_provider,
                model,
                show_output,
                web_context=web_ctx,
                sandbox=sandbox,
            )
            # Final ruff cleanup after all LLM edits.
            _fix_code_errors_with_llm(
                project_path,
                ["tests/"],
                installed_deps,
                model_provider,
                model,
                show_output,
                sandbox=sandbox,
            )
            _format_code(project_path, sandbox=sandbox)

    try:
        _run_cmd(["git", "add", "-A"], cwd=project_path, check=False)
        _run_cmd(
            ["git", "commit", "-q", "-m", "test: generate and fix tests"],
            cwd=project_path,
            check=False,
        )
    except Exception:  # noqa: BLE001
        pass

    return True
