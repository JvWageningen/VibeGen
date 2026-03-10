"""Command-line interface for vibegen."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from ._analysis import _parse_spec
from ._io import _print_err, _print_ok, _print_step, _print_warn, _run_cmd
from ._pipeline import _generate_and_fix_tests, _generate_code
from ._scaffold import (
    _copy_docs,
    _create_vscode_settings,
    _ensure_package_dir,
    _generate_readme,
    _init_git,
    _update_pyproject_tools,
    _write_claude_md,
    _write_gitattributes,
    _write_gitignore,
    _write_pre_commit_config,
)
from .sandbox import SandboxConfig, ensure_image_ready


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and drive the full project-generation pipeline.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]``).

    Returns:
        Exit code (0 = success, 1 = error).
    """
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
    parser.add_argument(
        "--sandbox",
        action="store_true",
        help="Run project commands inside a Docker container (filesystem isolation)",
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

    sandbox: SandboxConfig | None = None
    if args.sandbox:
        sandbox = SandboxConfig(project_path=output_dir)
        ensure_image_ready(sandbox.image)
        _print_step(f"Sandbox enabled (image: {sandbox.image})")

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
    except Exception:  # noqa: BLE001
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
            sandbox=sandbox,
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
                sandbox=sandbox,
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
            except Exception:  # noqa: BLE001
                pass

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
    _ensure_directory,
)
