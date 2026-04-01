"""Core iteration engine for the ``vibegen improve`` command."""

from __future__ import annotations

import contextlib
import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path

from ._improve_metrics import _run_verification
from ._improve_state import (
    ImproveState,
    IterationRecord,
    _append_changelog,
    _ensure_improve_dirs,
    _load_improve_state,
    _record_failed_change,
    _save_improve_state,
    _save_iteration_log,
    _save_verdict,
)
from ._io import _print_err, _print_ok, _print_step, _print_warn, _run_cmd
from ._llm import _load_prompt_template, _render_template, _run_claude_session
from ._pipeline import _format_code
from ._scaffold import _repair_project

_MAX_FIX_SUBLOOP = 3
_STALL_LIMIT = 5
_REGRESSION_REVERT_THRESHOLD = 3


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git_current_branch(project_path: Path) -> str:
    """Return the name of the currently checked-out branch.

    Args:
        project_path: Project root directory.

    Returns:
        Branch name string.
    """
    result = _run_cmd(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=project_path,
        capture_output=True,
    )
    return (result.stdout or "").strip()


def _git_is_clean(project_path: Path) -> bool:
    """Return True if the git working tree has no uncommitted changes.

    Args:
        project_path: Project root directory.

    Returns:
        True when the working tree is clean.
    """
    result = _run_cmd(
        ["git", "status", "--porcelain"],
        cwd=project_path,
        capture_output=True,
    )
    return not (result.stdout or "").strip()


def _git_create_branch(project_path: Path, branch_name: str) -> None:
    """Create and checkout a new branch.

    Args:
        project_path: Project root directory.
        branch_name: Name for the new branch.
    """
    _run_cmd(
        ["git", "checkout", "-b", branch_name],
        cwd=project_path,
        capture_output=True,
    )


def _git_commit_and_push(project_path: Path, iteration: int, summary: str) -> str:
    """Stage all changes, commit, and push to the current branch.

    Args:
        project_path: Project root directory.
        iteration: Iteration number for the commit message.
        summary: One-line change summary.

    Returns:
        Commit SHA, or empty string on failure.
    """
    _run_cmd(
        ["git", "add", "-A"],
        cwd=project_path,
        capture_output=True,
    )

    # Check if there's anything to commit.
    result = _run_cmd(
        ["git", "status", "--porcelain"],
        cwd=project_path,
        capture_output=True,
    )
    if not (result.stdout or "").strip():
        _print_warn("No changes to commit")
        return ""

    _run_cmd(
        [
            "git",
            "commit",
            "-m",
            f"vibegen improve: iter {iteration} — {summary}",
        ],
        cwd=project_path,
        capture_output=True,
    )

    # Push to remote (best-effort, don't fail the loop on push errors).
    try:
        _run_cmd(
            ["git", "push", "-u", "origin", "HEAD"],
            cwd=project_path,
            capture_output=True,
        )
    except Exception:  # noqa: BLE001
        _print_warn("Push failed — changes committed locally only")

    sha_result = _run_cmd(
        ["git", "rev-parse", "HEAD"],
        cwd=project_path,
        capture_output=True,
    )
    return (sha_result.stdout or "").strip()


def _git_diff_staged(project_path: Path) -> str:
    """Return the diff of all uncommitted changes.

    Args:
        project_path: Project root directory.

    Returns:
        Diff text.
    """
    result = _run_cmd(
        ["git", "diff", "HEAD"],
        cwd=project_path,
        capture_output=True,
        check=False,
    )
    return (result.stdout or "")[:8000]  # Truncate for prompt size


def _git_merge_to_base(project_path: Path, base_branch: str) -> bool:
    """Merge the current branch into *base_branch*.

    Args:
        project_path: Project root directory.
        base_branch: Target branch to merge into.

    Returns:
        True on success.
    """
    current = _git_current_branch(project_path)
    try:
        _run_cmd(
            ["git", "checkout", base_branch],
            cwd=project_path,
            capture_output=True,
        )
        _run_cmd(
            [
                "git",
                "merge",
                current,
                "--no-ff",
                "-m",
                f"Merge {current} into {base_branch}",
            ],
            cwd=project_path,
            capture_output=True,
        )
        _run_cmd(
            ["git", "push", "origin", base_branch],
            cwd=project_path,
            capture_output=True,
        )
        _print_ok(f"Merged {current} into {base_branch}")
        return True
    except Exception:  # noqa: BLE001
        _print_err(f"Merge to {base_branch} failed — resolve manually")
        return False


def _revert_iterations(project_path: Path, count: int) -> bool:
    """Revert the last *count* commits as a single revert commit.

    Args:
        project_path: Project root directory.
        count: Number of commits to revert.

    Returns:
        True on success.
    """
    try:
        for i in range(count):
            _run_cmd(
                ["git", "revert", "--no-commit", f"HEAD~{i}"],
                cwd=project_path,
                capture_output=True,
            )
        _run_cmd(
            [
                "git",
                "commit",
                "-m",
                f"vibegen improve: revert last {count} iterations (regression)",
            ],
            cwd=project_path,
            capture_output=True,
        )
        _print_warn(f"Reverted last {count} iterations due to regression")
        return True
    except Exception:  # noqa: BLE001
        # If revert fails (e.g. conflicts), reset to clean state.
        _run_cmd(
            ["git", "revert", "--abort"],
            cwd=project_path,
            capture_output=True,
            check=False,
        )
        _print_err("Revert failed — manual intervention needed")
        return False


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def _format_history(history: list[IterationRecord], limit: int = 5) -> str:
    """Format recent history entries for inclusion in prompts.

    Args:
        history: Full history list.
        limit: Maximum entries to include.

    Returns:
        Formatted multi-line string.
    """
    if not history:
        return "(no previous iterations)"
    recent = history[-limit:]
    lines: list[str] = []
    for rec in recent:
        rev = " [REVERTED]" if rec.reverted else ""
        lines.append(
            f"Iter {rec.iteration}: [{rec.verdict}]{rev} — {rec.changes_summary}"
        )
    return "\n".join(lines)


def _build_improve_prompt(
    state: ImproveState,
    project_path: Path,
) -> str:
    """Build the iteration prompt from the template.

    Args:
        state: Current improvement state.
        project_path: Project root directory.

    Returns:
        Rendered prompt string.
    """
    template = _load_prompt_template("improve_tick")

    # Read changelog if it exists.
    changelog_path = project_path / ".vibegen/improve/CHANGELOG.md"
    changelog = ""
    if changelog_path.exists():
        changelog = changelog_path.read_text(encoding="utf-8")[-2000:]

    failed = (
        "\n".join(
            f"- Iter {fc.get('iteration', '?')}: {fc.get('change', '?')} "
            f"(reason: {fc.get('reason', '?')})"
            for fc in state.failed_changes
        )
        or "(none)"
    )

    notes = "\n".join(state.notes_for_claude) or "(none)"

    return _render_template(
        template,
        {
            "task": state.task,
            "iteration": str(state.iteration),
            "history": _format_history(state.history),
            "failed_changes": failed,
            "notes": notes,
            "changelog": changelog or "(no entries yet)",
        },
    )


def _build_evaluate_prompt(
    state: ImproveState,
    changes_summary: str,
    diff: str,
    verification: dict[str, str],
) -> str:
    """Build the evaluation prompt for Claude to judge an iteration.

    Args:
        state: Current improvement state.
        changes_summary: What Claude changed this iteration.
        diff: Git diff of changes.
        verification: Raw verification output dict.

    Returns:
        Rendered evaluation prompt.
    """
    template = _load_prompt_template("improve_evaluate")
    return _render_template(
        template,
        {
            "iteration": str(state.iteration),
            "task": state.task,
            "changes_summary": changes_summary,
            "diff": diff[:6000],
            "pytest_output": verification.get("pytest", "")[:3000],
            "ruff_output": verification.get("ruff", "")[:2000],
            "mypy_output": verification.get("mypy", "")[:2000],
            "history": _format_history(state.history),
        },
    )


def _parse_changes_summary(claude_output: str) -> str:
    """Extract the ``CHANGES: ...`` line from Claude's output.

    Args:
        claude_output: Raw Claude response text.

    Returns:
        The change summary, or a fallback if not found.
    """
    for line in reversed(claude_output.splitlines()):
        if line.strip().upper().startswith("CHANGES:"):
            return line.strip()[len("CHANGES:") :].strip()
    return "(no summary provided)"


def _parse_verdict(claude_output: str) -> dict[str, str]:
    """Extract the structured verdict JSON from Claude's evaluation output.

    Args:
        claude_output: Raw Claude response text.

    Returns:
        Dict with ``verdict`` and ``reasoning`` keys, or defaults.
    """
    # Try to find JSON in the response.
    match = re.search(r'\{[^}]*"verdict"[^}]*\}', claude_output)
    if match:
        try:
            data = json.loads(match.group())
            if "verdict" in data:
                return {
                    "verdict": data["verdict"],
                    "reasoning": data.get("reasoning", ""),
                }
        except json.JSONDecodeError:
            pass
    return {"verdict": "neutral", "reasoning": "Could not parse verdict"}


# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------


def _ensure_vibegen_setup(project_path: Path) -> bool:
    """Ensure the project has VibeGen tooling set up.

    If ``.vibegen/`` does not exist, runs ``_repair_project()`` to scaffold
    the project with ruff, pytest, mypy configuration.

    Args:
        project_path: Project root directory.

    Returns:
        True if setup is ready, False on failure.
    """
    if (project_path / ".vibegen").exists():
        return True

    _print_step("Project not set up with VibeGen — running repair/scaffold...")
    exit_code, _spec, _pkg = _repair_project(project_path)
    if exit_code != 0:
        _print_err("Failed to set up VibeGen tooling")
        return False

    # Commit the scaffold so the improvement branch starts clean.
    _run_cmd(
        ["git", "add", "-A"],
        cwd=project_path,
        capture_output=True,
    )
    _run_cmd(
        ["git", "commit", "-m", "chore: initialize VibeGen tooling"],
        cwd=project_path,
        capture_output=True,
        check=False,
    )
    _print_ok("VibeGen tooling initialized")
    return True


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def _run_improve_loop(
    project_path: Path,
    task: str,
    max_iterations: int,
    model: str,
    model_provider: str,
    branch_name: str,
    port: int,
    auto_merge: bool,
    show_output: bool,
    mode: str = "direct",
    poll_flag: str | None = None,
    poll_interval: int = 60,
) -> int:
    """Run the iterative improvement loop.

    Args:
        project_path: Absolute path to the project.
        task: Improvement task description.
        max_iterations: Maximum iterations (0 = unlimited with stall detection).
        model: Claude model identifier.
        model_provider: LLM provider (``claude`` or ``ollama``).
        branch_name: Git branch name for improvements.
        port: Web UI port.
        auto_merge: Merge to base branch when done.
        show_output: Show full Claude output in console.
        mode: ``direct`` or ``polling``.
        poll_flag: Flag file path for polling mode.
        poll_interval: Seconds between polls.

    Returns:
        Exit code (0 = success, 1 = error).
    """
    project_path = project_path.resolve()

    # --- Pre-flight ---
    if not (project_path / ".git").is_dir():
        _print_err("Not a git repository")
        return 1

    if not _git_is_clean(project_path):
        _print_err("Working tree has uncommitted changes — commit or stash first")
        return 1

    if not _ensure_vibegen_setup(project_path):
        return 1

    base_branch = _git_current_branch(project_path)
    _git_create_branch(project_path, branch_name)
    _print_ok(f"Created branch: {branch_name}")

    # --- Initialize state ---
    _ensure_improve_dirs(project_path)
    state = ImproveState(
        iteration=0,
        max_iterations=max_iterations,
        status="running",
        mode=mode,
        task=task,
        branch_name=branch_name,
        base_branch=base_branch,
        started_at=datetime.now(tz=UTC).isoformat(),
        project_path=str(project_path),
        poll_flag_path=poll_flag or "",
        poll_interval=poll_interval,
    )
    _save_improve_state(project_path, state)

    # --- Start web UI ---
    server = None
    try:
        from ._improve_webui import _start_webui

        server = _start_webui(project_path, port)
        _print_ok(f"Web dashboard: http://localhost:{port}")
    except Exception:  # noqa: BLE001
        _print_warn("Web UI failed to start — continuing without dashboard")

    # --- Iteration loop ---
    try:
        while True:
            # Check termination conditions.
            if state.status in ("done", "error"):
                break
            if max_iterations > 0 and state.iteration >= max_iterations:
                _print_ok(f"Reached max iterations ({max_iterations})")
                state.status = "done"
                break
            if state.consecutive_stalls >= _STALL_LIMIT:
                _print_ok(f"No improvements for {_STALL_LIMIT} iterations — stopping")
                state.status = "done"
                break

            # Pause support.
            while state.status == "paused":
                time.sleep(5)
                state = _load_improve_state(project_path)

            if state.status in ("done", "error"):
                break

            state.iteration += 1
            _print_step(f"=== Iteration {state.iteration} ===")

            # --- Polling mode: wait for flag ---
            if mode == "polling" and poll_flag:
                _print_step(f"Waiting for flag: {poll_flag}")
                _wait_for_flag(Path(poll_flag), state, project_path, poll_interval)
                if state.status in ("done", "error", "paused"):
                    continue

            # --- Step A: Improve ---
            _print_step("Step A: Claude making improvements...")
            improve_prompt = _build_improve_prompt(state, project_path)
            claude_output, session_id = _run_claude_session(
                prompt=improve_prompt,
                model=model,
                cwd=project_path,
                permission_mode="acceptEdits",
                resume_session=state.claude_session_id or None,
                show_output=show_output,
            )
            state.claude_session_id = session_id
            changes_summary = _parse_changes_summary(claude_output)
            _save_iteration_log(project_path, state.iteration, claude_output)
            _print_ok(f"Changes: {changes_summary}")

            # --- Step B: Fix sub-loop ---
            _format_code(project_path)
            verification = _run_verification(project_path)

            for fix_attempt in range(_MAX_FIX_SUBLOOP):
                # Check if there are obvious issues to fix.
                has_issues = (
                    "FAILED" in verification.get("pytest", "")
                    or "error" in verification.get("ruff", "").lower()
                )
                if not has_issues:
                    break

                _print_step(
                    f"Step B: Fix attempt {fix_attempt + 1}/{_MAX_FIX_SUBLOOP}..."
                )
                fix_prompt = (
                    f"Fix the issues found in the verification output below. "
                    f"These are from iteration {state.iteration} of the "
                    f"improvement task: {task}\n\n"
                    f"pytest output:\n{verification['pytest'][:3000]}\n\n"
                    f"ruff output:\n{verification['ruff'][:2000]}\n\n"
                    f"mypy output:\n{verification['mypy'][:2000]}"
                )
                fix_output, session_id = _run_claude_session(
                    prompt=fix_prompt,
                    model=model,
                    cwd=project_path,
                    permission_mode="acceptEdits",
                    resume_session=session_id,
                    show_output=show_output,
                )
                state.claude_session_id = session_id
                _format_code(project_path)
                verification = _run_verification(project_path)

            # --- Step C: Evaluate ---
            _print_step("Step C: Evaluating iteration...")
            diff = _git_diff_staged(project_path)
            eval_prompt = _build_evaluate_prompt(
                state,
                changes_summary,
                diff,
                verification,
            )
            eval_output, session_id = _run_claude_session(
                prompt=eval_prompt,
                model=model,
                cwd=project_path,
                permission_mode="plan",  # Read-only for evaluation.
                resume_session=session_id,
                show_output=show_output,
            )
            state.claude_session_id = session_id
            verdict = _parse_verdict(eval_output)
            _save_verdict(project_path, state.iteration, verdict)
            _print_step(f"Verdict: {verdict['verdict']} — {verdict['reasoning']}")

            # --- Step D: Act on verdict ---
            record = IterationRecord(
                iteration=state.iteration,
                verdict=verdict["verdict"],
                verdict_reasoning=verdict["reasoning"],
                changes_summary=changes_summary,
                test_output=verification.get("pytest", "")[:1000],
                lint_output=verification.get("ruff", "")[:500],
                type_output=verification.get("mypy", "")[:500],
                timestamp=datetime.now(tz=UTC).isoformat(),
            )

            if verdict["verdict"] == "regression":
                state.consecutive_regressions += 1
                state.consecutive_stalls = 0
                _print_warn(
                    f"Regression ({state.consecutive_regressions}/"
                    f"{_REGRESSION_REVERT_THRESHOLD})"
                )

                if state.consecutive_regressions >= _REGRESSION_REVERT_THRESHOLD:
                    _handle_revert(project_path, state)
            else:
                state.consecutive_regressions = 0

                if verdict["verdict"] == "improvement":
                    state.consecutive_stalls = 0
                    state.best_iteration = state.iteration
                    _print_ok("Improvement detected!")
                else:
                    state.consecutive_stalls += 1

                sha = _git_commit_and_push(
                    project_path,
                    state.iteration,
                    changes_summary,
                )
                record.commit_sha = sha

            state.history.append(record)
            _append_changelog(project_path, state.iteration, changes_summary)
            _save_improve_state(project_path, state)

    except KeyboardInterrupt:
        _print_warn("Interrupted by user")
        state.status = "done"
        _save_improve_state(project_path, state)

    # --- Cleanup ---
    if server is not None:
        try:
            from ._improve_webui import _stop_webui

            _stop_webui(server)
        except Exception:  # noqa: BLE001
            pass

    # --- Optional merge ---
    if auto_merge and state.status == "done":
        _print_step(f"Merging {branch_name} into {base_branch}...")
        _git_merge_to_base(project_path, base_branch)

    # --- Final summary ---
    improvements = sum(1 for r in state.history if r.verdict == "improvement")
    _print_ok(
        f"Done after {state.iteration} iterations "
        f"({improvements} improvements, "
        f"best: iter {state.best_iteration})"
    )
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wait_for_flag(
    flag_path: Path,
    state: ImproveState,
    project_path: Path,
    interval: int,
) -> None:
    """Block until the flag file appears, checking for pause/stop.

    Args:
        flag_path: Path to the flag file to watch.
        state: Current state (reloaded each poll to check for pause/stop).
        project_path: Project root for state reloading.
        interval: Seconds between polls.
    """
    while not flag_path.exists():
        time.sleep(interval)
        state_check = _load_improve_state(project_path)
        if state_check.status in ("done", "error", "paused"):
            state.status = state_check.status
            return

    # Read and remove the flag.
    with contextlib.suppress(Exception):
        flag_path.read_text(encoding="utf-8")
    flag_path.unlink(missing_ok=True)


def _handle_revert(project_path: Path, state: ImproveState) -> None:
    """Revert the last N regression iterations and record failed changes.

    Args:
        project_path: Project root directory.
        state: Current state (modified in place).
    """
    count = _REGRESSION_REVERT_THRESHOLD
    _print_warn(f"Reverting last {count} iterations due to regressions")

    # Record failed changes from the reverted iterations.
    for rec in state.history[-count:]:
        _record_failed_change(
            project_path,
            rec.iteration,
            rec.changes_summary,
            rec.verdict_reasoning,
        )
        rec.reverted = True

    _revert_iterations(project_path, count)

    # Push the revert.
    with contextlib.suppress(Exception):
        _run_cmd(
            ["git", "push", "origin", "HEAD"],
            cwd=project_path,
            capture_output=True,
        )

    state.consecutive_regressions = 0
    state.notes_for_claude.append(
        f"Last {count} iterations were reverted due to regressions. "
        "Review failed_changes and try a different approach."
    )
