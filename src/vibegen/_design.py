"""Interactive spec generation via Claude Q&A."""

from __future__ import annotations

import re
from pathlib import Path

from ._io import _print_err, _print_ok, _print_step, _print_warn, _write_file
from ._llm import _load_prompt_template, _render_template, _run_claude_session

_MAX_QA_ROUNDS = 10
_MAX_PARSE_FAILURES = 3


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------


def _parse_qa_response(text: str) -> tuple[str, list[str]]:
    """Parse Claude's Q&A response into a status and question list.

    Args:
        text: Raw Claude response text.

    Returns:
        Tuple of (status, questions) where status is ``"READY"`` or
        ``"NEED_MORE"`` and questions is a list of question strings.
    """
    lower = text.lower()

    # Detect READY — explicit marker or common phrasing.
    if "STATUS: READY" in text:
        return "READY", []
    ready_phrases = [
        "i have enough information",
        "i have sufficient information",
        "i'm ready to generate",
        "ready to create the spec",
        "ready to write the spec",
        "let me generate the spec",
        "proceed with generating",
    ]
    if any(phrase in lower for phrase in ready_phrases):
        return "READY", []

    # Extract questions — try multiple common formats.
    body = text.split("STATUS:")[0] if "STATUS:" in text else text
    questions: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        # Numbered: "1. ...", "1) ...", "**1.** ...", "**1)** ..."
        if re.match(r"^(\*{0,2}\d+[\.\)]\*{0,2}\s+)", stripped):
            q = re.sub(r"^(\*{0,2}\d+[\.\)]\*{0,2}\s+)", "", stripped)
            if q and "?" in q:
                questions.append(q)
        # Dash/bullet: "- ...", "* ..."
        elif re.match(r"^[-*]\s+\S", stripped):
            q = re.sub(r"^[-*]\s+", "", stripped)
            if q and "?" in q:
                questions.append(q)
        # Bare question line (contains a ?)
        elif stripped.endswith("?") and len(stripped) > 15:
            questions.append(stripped)

    if "STATUS: NEED_MORE" in text or questions:
        return "NEED_MORE", questions

    # No marker and no questions found — likely ready or confused.
    return "NEED_MORE", []


def _extract_spec_text(response: str) -> str:
    """Extract spec markdown from between delimiters in Claude's response.

    Looks for content between ``--- spec.md ---`` and ``--- end ---``.
    Falls back to the full response if delimiters are absent.

    Args:
        response: Raw Claude response text.

    Returns:
        Extracted spec markdown.
    """
    match = re.search(
        r"---\s*spec\.md\s*---\s*\n(.*?)\n\s*---\s*end\s*---",
        response,
        re.DOTALL,
    )
    if match:
        return match.group(1).strip()
    return response.strip()


def _read_multiline_input(prompt: str = "") -> str:
    """Read multi-line input from stdin until a blank line.

    Args:
        prompt: Optional prompt to display before reading.

    Returns:
        Collected input text (may be empty if user just presses Enter).
    """
    if prompt:
        print(prompt, flush=True)
    lines: list[str] = []
    try:
        while True:
            line = input()
            if not line and lines:
                break
            if not line and not lines:
                # First line is blank — user pressed Enter immediately.
                return ""
            lines.append(line)
    except EOFError:
        pass
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Session functions
# ---------------------------------------------------------------------------


def _run_qa_round(
    description: str,
    model: str,
    cwd: Path,
    session_id: str = "",
    user_answers: str = "",
    show_output: bool = False,
) -> tuple[str, str, list[str], str]:
    """Run one Q&A round with Claude.

    On the first round (no session_id), sends the interview prompt with
    the user's description. On subsequent rounds, sends user answers.

    Args:
        description: User's project description (used on first round).
        model: Claude model identifier.
        cwd: Working directory.
        session_id: Session ID to resume (empty for first round).
        user_answers: User's answers from previous round.
        show_output: Show full Claude output.

    Returns:
        Tuple of (status, session_id, questions, raw_response).
    """
    if not session_id:
        template = _load_prompt_template("design_interview")
        prompt = _render_template(template, {"description": description})
    else:
        prompt = f"Here are my answers:\n\n{user_answers}"

    result, new_session_id = _run_claude_session(
        prompt=prompt,
        model=model,
        cwd=cwd,
        permission_mode="plan",
        resume_session=session_id or None,
        show_output=show_output,
    )
    status, questions = _parse_qa_response(result)
    return status, new_session_id, questions, result


def _run_qa_loop(
    description: str,
    model: str,
    cwd: Path,
    show_output: bool = False,
) -> tuple[str, str]:
    """Drive the full interactive Q&A loop.

    Args:
        description: User's project description.
        model: Claude model identifier.
        cwd: Working directory.
        show_output: Show full Claude output.

    Returns:
        Tuple of (session_id, final_status).
    """
    session_id = ""
    parse_failures = 0

    for round_num in range(1, _MAX_QA_ROUNDS + 1):
        if round_num == 1:
            _print_step("Analyzing your description and preparing questions...")
            status, session_id, questions, raw = _run_qa_round(
                description,
                model,
                cwd,
                show_output=show_output,
            )
        else:
            answers = _read_multiline_input(
                "\nYour answers (type 'done' or press Enter"
                " to skip to spec generation):"
            )
            if not answers.strip() or answers.strip().lower() == "done":
                _print_ok("Moving on to spec generation")
                return session_id, "READY"
            _print_step(f"Processing your answers (round {round_num})...")
            status, session_id, questions, raw = _run_qa_round(
                description,
                model,
                cwd,
                session_id,
                answers,
                show_output,
            )

        if status == "READY":
            _print_ok("Claude has enough information to generate the spec")
            return session_id, status

        if questions:
            parse_failures = 0
            print("\nClaude has some questions:\n")
            for i, question in enumerate(questions, 1):
                print(f"  {i}. {question}")
        else:
            # Could not extract structured questions — show raw response.
            parse_failures += 1
            print(f"\nClaude says:\n\n{raw.strip()}\n")
            if parse_failures >= _MAX_PARSE_FAILURES:
                _print_ok("No further questions detected — moving to spec generation")
                return session_id, "READY"

    _print_warn(f"Reached max Q&A rounds ({_MAX_QA_ROUNDS}) — proceeding")
    return session_id, "READY"


def _generate_spec(
    session_id: str,
    model: str,
    cwd: Path,
    output_path: Path,
    show_output: bool = False,
) -> tuple[Path, str]:
    """Ask Claude to generate spec.md from the Q&A context.

    Claude writes the file directly via ``acceptEdits`` mode for
    reliability.  If the file is not created, falls back to extracting
    the spec from Claude's text response.

    Args:
        session_id: Claude session ID from Q&A loop.
        model: Claude model identifier.
        cwd: Working directory.
        output_path: Directory to write spec.md into.
        show_output: Show full Claude output.

    Returns:
        Tuple of (spec_path, session_id).
    """
    _print_step("Generating spec.md...")
    spec_path = output_path / "spec.md"

    prompt = (
        "Based on our entire conversation, generate a complete project "
        "specification and write it to the file: "
        f"{spec_path}\n\n"
        "The spec MUST include ALL of these sections with exactly "
        "these ## headers:\n"
        "## Name\n## Description\n## Python Version\n"
        "## Input\n## Output\n## Requirements\n"
        "## Dependencies\n## Example Usage\n"
        "## Edge Cases\n## Documentation\n\n"
        "Include ALL information from our conversation. "
        "Every section must have substantive content.\n"
        "Requirements should be numbered (REQ-01, REQ-02, etc.).\n"
        "Dependencies should be comma-separated package names.\n"
        "Example Usage should have concrete bash code blocks."
    )

    result, session_id = _run_claude_session(
        prompt=prompt,
        model=model,
        cwd=cwd,
        permission_mode="acceptEdits",
        resume_session=session_id,
        show_output=show_output,
    )

    # Check if Claude wrote the file directly.
    if spec_path.exists() and spec_path.stat().st_size > 50:
        _print_ok(f"Spec written to {spec_path}")
        return spec_path, session_id

    # Fallback: extract spec from Claude's text response.
    _print_warn("Claude did not write the file — extracting from response")
    spec_text = _extract_spec_text(result)
    if not spec_text or len(spec_text) < 50:
        _print_err("Could not generate spec — Claude returned empty response")
        _write_file(spec_path, "# Project Spec\n\n(generation failed)\n")
        return spec_path, session_id

    if not spec_text.startswith("# "):
        spec_text = "# Project Spec\n\n" + spec_text

    _write_file(spec_path, spec_text)
    _print_ok(f"Spec written to {spec_path}")
    return spec_path, session_id


def _review_spec_loop(
    spec_path: Path,
    session_id: str,
    model: str,
    cwd: Path,
    show_output: bool = False,
) -> str:
    """Let the user review and revise the generated spec.

    The user can type changes for Claude to apply, manually edit the file,
    or press Enter to accept.

    Args:
        spec_path: Path to the generated spec.md.
        session_id: Claude session ID.
        model: Claude model identifier.
        cwd: Working directory.
        show_output: Show full Claude output.

    Returns:
        Final session_id after any revisions.
    """
    while True:
        print(f"\nSpec file: {spec_path}")
        print("Review the spec, then:")
        print("  - Type your changes and press Enter on a blank line")
        print("  - Or just press Enter to accept and continue")

        changes = _read_multiline_input()
        if not changes.strip():
            _print_ok("Spec accepted")
            break

        _print_step("Updating spec with your changes...")
        prompt = (
            f"Update the spec file at {spec_path} with these changes:\n\n"
            f"{changes}\n\n"
            "Edit the file directly. Keep all existing sections and content "
            "that are not affected by the requested changes."
        )

        _result, session_id = _run_claude_session(
            prompt=prompt,
            model=model,
            cwd=cwd,
            permission_mode="acceptEdits",
            resume_session=session_id,
            show_output=show_output,
        )

        if spec_path.exists() and spec_path.stat().st_size > 50:
            _print_ok(f"Spec updated: {spec_path}")
        else:
            _print_warn("Spec file may not have been updated")

    return session_id


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_design_flow(
    description: str,
    model: str,
    model_provider: str,
    output_dir: Path,
    show_output: bool = False,
    spec_only: bool = False,
    max_fix_attempts: int = 3,
    max_turns: int = 30,
    sandbox: bool = False,
) -> int:
    """Orchestrate the full design-to-generation flow.

    Args:
        description: User's project description.
        model: Claude model identifier.
        model_provider: LLM provider (must be ``"claude"``).
        output_dir: Directory for spec.md and generated project.
        show_output: Show full Claude output.
        spec_only: Only generate spec, do not create project.
        max_fix_attempts: Max test-fix iterations for generation.
        max_turns: Max LLM turns per step.
        sandbox: Use Docker sandbox.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    if model_provider != "claude":
        _print_err("vibegen design requires --model-provider claude")
        return 1

    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Interactive Q&A.
    _print_step("Starting interactive spec design...")
    try:
        session_id, _status = _run_qa_loop(
            description,
            model,
            output_dir,
            show_output,
        )
    except KeyboardInterrupt:
        _print_warn("\nInterrupted")
        return 1

    # Step 2: Generate spec.
    spec_path, session_id = _generate_spec(
        session_id,
        model,
        output_dir,
        output_dir,
        show_output,
    )

    # Step 3: Review loop.
    try:
        session_id = _review_spec_loop(
            spec_path,
            session_id,
            model,
            output_dir,
            show_output,
        )
    except KeyboardInterrupt:
        _print_warn("\nInterrupted — spec.md saved")
        return 0

    if spec_only:
        _print_ok(f"Spec-only mode — spec saved at {spec_path}")
        return 0

    # Step 4: Hand off to existing pipeline.
    _print_step("Proceeding to project generation...")
    return _run_generation_pipeline(
        spec_path=spec_path,
        output_dir=output_dir,
        session_id=session_id,
        model=model,
        model_provider=model_provider,
        show_output=show_output,
        max_fix_attempts=max_fix_attempts,
        max_turns=max_turns,
        sandbox=sandbox,
    )


def _run_generation_pipeline(
    spec_path: Path,
    output_dir: Path,
    session_id: str,
    model: str,
    model_provider: str,
    show_output: bool,
    max_fix_attempts: int,
    max_turns: int,
    sandbox: bool,
) -> int:
    """Run the standard VibeGen generation pipeline from a spec file.

    Reuses the session_id from the design phase so Claude has full context.

    Args:
        spec_path: Path to the spec.md file.
        output_dir: Directory for the generated project.
        session_id: Claude session ID from design phase.
        model: Claude model identifier.
        model_provider: LLM provider.
        show_output: Show full Claude output.
        max_fix_attempts: Max test-fix iterations.
        max_turns: Max LLM turns per step.
        sandbox: Use Docker sandbox.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    import subprocess

    from ._analysis import _parse_spec
    from ._pipeline import _generate_and_fix_tests, _generate_code
    from ._scaffold import (
        _copy_claude_commands,
        _copy_docs,
        _create_vscode_settings,
        _ensure_package_dir,
        _generate_readme,
        _init_git,
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

    spec = _parse_spec(spec_path)
    project_name = spec.get("project_name", "")
    if not project_name:
        _print_err("Generated spec is missing project name")
        return 1

    package_name = project_name.lower().replace("-", "_").replace(" ", "_")
    project_path = output_dir / project_name

    # --- Scaffold ---
    _print_step(f"Scaffolding project '{project_name}'...")
    project_path.mkdir(parents=True, exist_ok=True)
    try:
        from ._io import _run_cmd

        _run_cmd(
            [
                "uv",
                "init",
                str(project_path),
                "--lib",
                "--python",
                spec["python_version"],
            ]
        )
    except subprocess.CalledProcessError as e:
        _print_err(f"Failed to scaffold project: {e}")
        return 1

    _ensure_package_dir(project_path, package_name)
    _write_claude_md(project_path, spec)
    _write_claude_settings(project_path)
    _copy_claude_commands(project_path)
    _create_vscode_settings(project_path)
    _write_gitignore(project_path)
    _write_gitattributes(project_path)
    _write_pre_commit_config(project_path)
    _update_pyproject_tools(project_path)
    _write_conftest(project_path, package_name)
    _write_ci_workflow(project_path, spec["python_version"])
    _write_docs_reference(project_path, spec)
    _copy_docs(project_path, spec_path, spec.get("doc_files", []))
    _init_git(project_path)
    _generate_readme(project_path, spec, package_name)
    _print_ok("Scaffold complete")

    # --- Install dependencies ---
    deps = spec.get("dependencies", [])
    if deps:
        _print_step(f"Installing dependencies: {', '.join(deps)}")
        try:
            _run_cmd(
                ["uv", "add"] + deps,
                cwd=project_path,
            )
            _print_ok("Dependencies installed")
        except Exception:  # noqa: BLE001
            _print_warn("Some dependencies failed to install")

    # --- Code generation ---
    _print_step("Generating code...")
    code_result = _generate_code(
        project_path,
        spec,
        package_name,
        model_provider,
        model,
        show_output=show_output,
        resume_session=session_id,
    )
    if not code_result:
        _print_err("Code generation failed")
        return 1

    claude_session = code_result if isinstance(code_result, str) else ""

    # --- Test generation + fix loop ---
    _print_step("Generating tests...")
    _generate_and_fix_tests(
        project_path,
        spec,
        package_name,
        model_provider,
        model,
        max_fix_attempts=max_fix_attempts,
        show_output=show_output,
        session_id=claude_session,
    )

    _print_ok(f"Project generated at {project_path}")
    return 0
