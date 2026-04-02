"""Command-line interface for vibegen."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Force UTF-8 for console I/O on Windows to prevent charmap encoding errors
# when LLM output contains Unicode characters (emojis, arrows, etc.).
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from ._io import _print_err, _print_ok, _print_step, _print_warn, _run_cmd
from ._pipeline import _generate_and_fix_tests, _generate_code
from ._plan import build_default_plan
from ._scaffold import (
    _copy_claude_commands,
    _copy_docs,
    _create_vscode_settings,
    _ensure_package_dir,
    _generate_readme,
    _init_git,
    _repair_project,
    _run_cymbal_index,
    _update_pyproject_tools,
    _write_ci_workflow,
    _write_claude_md,
    _write_claude_settings,
    _write_conftest,
    _write_docs_reference,
    _write_gitattributes,
    _write_gitignore,
    _write_pre_commit_config,
)
from ._session import Session, hash_spec, save_session, spec_changed
from .sandbox import SandboxConfig, ensure_image_ready


def _run_improve_command(argv: list[str]) -> int:
    """Parse and run the ``vibegen improve`` subcommand.

    Args:
        argv: Arguments after ``improve``.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    parser = argparse.ArgumentParser(
        prog="vibegen improve",
        description="Iteratively improve a project with Claude",
    )
    parser.add_argument(
        "project_path",
        nargs="?",
        default=".",
        help="Path to the project to improve (default: .)",
    )
    parser.add_argument(
        "--task",
        required=True,
        help="Improvement task description",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=0,
        help="Max iterations (0 = unlimited, stops on stall)",
    )
    parser.add_argument(
        "--branch-name",
        default="",
        help="Branch name (default: vibegen/improve-<project>)",
    )
    parser.add_argument("--port", type=int, default=8089, help="Web UI port")
    parser.add_argument("--model", default="claude-sonnet-4-6", help="Claude model")
    parser.add_argument(
        "--model-provider",
        default="claude",
        choices=["claude", "ollama"],
        help="LLM provider",
    )
    parser.add_argument(
        "--auto-merge",
        action="store_true",
        help="Merge to base branch when done",
    )
    parser.add_argument(
        "--show-output",
        action="store_true",
        help="Show full Claude output",
    )
    parser.add_argument(
        "--mode",
        default="direct",
        choices=["direct", "polling"],
        help="Execution mode",
    )
    parser.add_argument(
        "--poll-flag",
        default=None,
        help="Flag file path for polling mode",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=60,
        help="Seconds between polls (polling mode)",
    )
    args = parser.parse_args(argv)

    project_path = Path(args.project_path).resolve()
    branch = args.branch_name or (f"vibegen/improve-{project_path.name}")

    from ._improve_loop import _run_improve_loop

    return _run_improve_loop(
        project_path=project_path,
        task=args.task,
        max_iterations=args.max_iterations,
        model=args.model,
        model_provider=args.model_provider,
        branch_name=branch,
        port=args.port,
        auto_merge=args.auto_merge,
        show_output=args.show_output,
        mode=args.mode,
        poll_flag=args.poll_flag,
        poll_interval=args.poll_interval,
    )


def _run_init_command(argv: list[str]) -> int:
    """Parse and run the ``vibegen init`` subcommand.

    Initialises VibeGen dev tooling on an existing project without requiring
    a spec file.  Sets up ruff, pytest, mypy configuration, CLAUDE.md,
    .claude/ commands, VS Code settings, pre-commit hooks, CI workflow, etc.

    Args:
        argv: Arguments after ``init``.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    parser = argparse.ArgumentParser(
        prog="vibegen init",
        description="Initialize VibeGen dev tooling on an existing project",
    )
    parser.add_argument(
        "project_path",
        nargs="?",
        default=".",
        help="Path to the project (default: current directory)",
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="Claude model for README generation",
    )
    parser.add_argument(
        "--show-output",
        action="store_true",
        help="Show full Claude output",
    )
    args = parser.parse_args(argv)
    project_path = Path(args.project_path).resolve()

    _print_step(f"Initializing VibeGen tooling in {project_path}")
    exit_code, _spec, _pkg = _repair_project(
        project_path,
        model=args.model,
        show_output=args.show_output,
    )
    if exit_code == 0:
        _print_ok("VibeGen tooling initialized successfully")
    return exit_code


def _run_design_command(argv: list[str]) -> int:
    """Parse and run the ``vibegen design`` subcommand.

    Interactively designs a spec.md via Claude Q&A, then optionally
    generates the full project from the resulting spec.

    Args:
        argv: Arguments after ``design``.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    parser = argparse.ArgumentParser(
        prog="vibegen design",
        description="Interactively design a project spec with Claude",
    )
    parser.add_argument(
        "--description",
        default="",
        help="Brief project description (prompted if omitted)",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory for spec.md and generated project",
    )
    parser.add_argument(
        "--model",
        default="claude-sonnet-4-6",
        help="Claude model",
    )
    parser.add_argument(
        "--show-output",
        action="store_true",
        help="Show full Claude output",
    )
    parser.add_argument(
        "--spec-only",
        action="store_true",
        help="Generate spec.md only, do not create project",
    )
    parser.add_argument(
        "--max-fix-attempts",
        type=int,
        default=3,
        help="Max test fix iterations (for generation)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=30,
        help="Max LLM turns per step (for generation)",
    )
    parser.add_argument(
        "--sandbox",
        action="store_true",
        help="Use Docker sandbox",
    )
    args = parser.parse_args(argv)

    description = args.description
    if not description:
        _print_step("No description provided — enter your project idea:")
        description = input("> ").strip()
        if not description:
            _print_err("Description cannot be empty")
            return 1

    from ._design import run_design_flow

    return run_design_flow(
        description=description,
        model=args.model,
        model_provider="claude",
        output_dir=Path(args.output_dir),
        show_output=args.show_output,
        spec_only=args.spec_only,
        max_fix_attempts=args.max_fix_attempts,
        max_turns=args.max_turns,
        sandbox=args.sandbox,
    )


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and drive the full project-generation pipeline.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]``).

    Returns:
        Exit code (0 = success, 1 = error).
    """
    # Route to subcommands before the main argparse.
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "improve":
        return _run_improve_command(argv[1:])
    if argv and argv[0] == "init":
        return _run_init_command(argv[1:])
    if argv and argv[0] == "design":
        return _run_design_command(argv[1:])

    parser = argparse.ArgumentParser(
        description="vibegen - generate Python projects from a spec"
    )
    parser.add_argument("spec_file", nargs="?", help="Path to spec markdown file")
    parser.add_argument("--output-dir", default="", help="Output directory")
    parser.add_argument(
        "--repair", action="store_true", help="Repair an existing project"
    )
    parser.add_argument(
        "--repo-path",
        default="",
        help="Path to repo to repair (defaults to current directory)",
    )
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
    parser.add_argument(
        "--sandbox",
        action="store_true",
        help="Run project commands inside a Docker container (filesystem isolation)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume a previous run: skip scaffold/generate if spec is unchanged",
    )

    args = parser.parse_args(argv)

    if not args.spec_file and not args.repair:
        parser.print_help()
        return 0

    if args.repair:
        repo_path = Path(args.repo_path) if args.repo_path else Path.cwd()
        exit_code, spec, package_name = _repair_project(
            repo_path,
            model=args.model,
            show_output=args.show_output,
        )
        if exit_code != 0:
            return exit_code

        # If a spec file is also provided, run code generation
        if args.spec_file:
            from ._analysis import _parse_spec

            spec_path = Path(args.spec_file)
            if spec_path.exists():
                spec = _parse_spec(spec_path)
                package_name = (
                    spec["project_name"].lower().replace("-", "_").replace(" ", "_")
                )
            task_plan = build_default_plan()
            for step_id in (
                "scaffold",
                "install_deps",
            ):
                task_plan.skip(step_id, "repair mode")

            try:
                code_result = _generate_code(
                    repo_path,
                    spec,
                    package_name,
                    args.model_provider,
                    args.model,
                    show_output=args.show_output,
                    plan=task_plan,
                )
                if code_result:
                    claude_session = code_result if isinstance(code_result, str) else ""
                    _generate_and_fix_tests(
                        repo_path,
                        spec,
                        package_name,
                        args.model_provider,
                        args.model,
                        max_fix_attempts=args.max_fix_attempts,
                        show_output=args.show_output,
                        plan=task_plan,
                        session_id=claude_session,
                    )
                    _print_ok("Generation complete!")
            except Exception as e:  # noqa: BLE001
                _print_warn(f"Code generation failed: {e}")

        return 0

    from ._analysis import _parse_spec

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

    task_plan = build_default_plan()

    sandbox: SandboxConfig | None = None
    if args.sandbox:
        sandbox = SandboxConfig(project_path=output_dir)
        ensure_image_ready(sandbox.image)
        _print_step(f"Sandbox enabled (image: {sandbox.image})")

    task_plan.start("parse_spec")
    task_plan.complete("parse_spec", project_name)

    # ------------------------------------------------------------------
    # Resume logic: skip scaffold + generate when spec is unchanged
    # ------------------------------------------------------------------
    resuming = args.resume and not spec_changed(output_dir, spec_path)
    if args.resume and not resuming:
        _print_warn("Spec has changed since the last run — starting fresh.")

    session = Session(
        spec_hash=hash_spec(spec_path),
        project_name=project_name,
        package_name=package_name,
        model_provider=args.model_provider,
        model=args.model,
    )

    if resuming:
        task_plan.skip("scaffold", "resuming previous run")
        task_plan.skip("install_deps", "resuming previous run")
        _print_step("Resuming previous run — skipping scaffold.")
    else:
        task_plan.start("scaffold")
        _print_step("Scaffolding project with uv...")
        if output_dir.exists() and any(output_dir.iterdir()):
            _print_warn(
                "Output directory already exists and is not empty. Proceeding anyway."
            )
        else:
            output_dir.mkdir(parents=True, exist_ok=True)

        try:
            _run_cmd(
                [
                    "uv",
                    "init",
                    str(output_dir),
                    "--lib",
                    "--python",
                    spec["python_version"],
                ]
            )
        except subprocess.CalledProcessError as e:
            _print_err(f"Failed to scaffold project: {e}")
            task_plan.fail("scaffold", str(e))
            return 1

        _ensure_package_dir(output_dir, package_name)
        _write_claude_md(output_dir, spec)
        _write_claude_settings(output_dir)
        _copy_claude_commands(output_dir)
        _create_vscode_settings(output_dir)
        _write_gitignore(output_dir)
        _write_gitattributes(output_dir)
        _write_pre_commit_config(output_dir)
        _update_pyproject_tools(output_dir)
        _write_conftest(output_dir, package_name)
        _write_ci_workflow(output_dir, spec["python_version"])
        _write_docs_reference(output_dir, spec)
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
        except Exception:  # noqa: BLE001
            pass

        task_plan.complete("scaffold")
        _print_ok("Project scaffold created")
        _run_cymbal_index(output_dir)
        save_session(output_dir, session)

    try:
        task_plan.start("install_deps")
        task_plan.complete("install_deps")

        if resuming:
            for step_id in (
                "plan_code",
                "generate_code",
                "fix_code_ruff",
                "fix_code_llm",
            ):
                task_plan.skip(step_id, "resuming previous run")

        code_result = resuming or _generate_code(
            output_dir,
            spec,
            package_name,
            args.model_provider,
            args.model,
            show_output=args.show_output,
            sandbox=sandbox,
            plan=task_plan,
        )

        if code_result:
            # For Claude, code_result is the session ID (str);
            # for Ollama it's True (bool).
            claude_session = code_result if isinstance(code_result, str) else ""
            _generate_and_fix_tests(
                output_dir,
                spec,
                package_name,
                args.model_provider,
                args.model,
                max_fix_attempts=args.max_fix_attempts,
                show_output=args.show_output,
                sandbox=sandbox,
                plan=task_plan,
                session_id=claude_session,
            )

            task_plan.start("finalize")
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
            except Exception:  # noqa: BLE001
                pass
            task_plan.complete("finalize")
            session.last_status = "complete"
            save_session(output_dir, session)

            print("\n" + task_plan.render())
            _print_ok("Project generation complete!")
            _print_ok(f"Location: {output_dir}")
        else:
            _print_warn("Code generation skipped. Create source files manually.")

    except Exception as e:  # noqa: BLE001
        _print_warn(f"Code generation failed: {e}")
        _print_warn("Manual code generation may be required.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# Re-exports for backward compatibility
# ---------------------------------------------------------------------------
# Any code that previously did `from vibegen.cli import _run_cmd` etc. will
# still work via these re-exports.

from ._analysis import (  # noqa: E402, F401
    _build_dependency_graph,
    _get_installed_package_names,
    _get_pyproject_deps,
    _get_repo_tree,
    _get_test_failure_summary,
    _read_source_files,
)
from ._io import (  # noqa: E402, F401
    _write_file,
)
from ._llm import (  # noqa: E402, F401
    _estimate_num_ctx,
    _load_prompt_template,
    _render_template,
    _run_llm,
)
from ._output_parser import (  # noqa: E402, F401
    _clean_file_content,
    _parse_generated_files,
    _write_generated_files,
)
from ._pipeline import (  # noqa: E402, F401
    _fix_code_errors_with_llm,
    _format_code,
    _get_ruff_errors_by_file,
    _install_missing_deps,
    _plan_tests,
    _relocate_test_files,
    _run_tests,
)
from ._scaffold import (  # noqa: E402, F401
    _detect_package_name,
    _ensure_directory,
    _read_pyproject_info,
)
