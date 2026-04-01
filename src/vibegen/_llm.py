"""LLM dispatch layer: Claude CLI, Ollama, and prompt template utilities."""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path

from ._io import _print_err
from .ollama_client import OllamaClient


def _render_template(text: str, values: dict[str, str]) -> str:
    """Replace ``{{key}}`` placeholders in *text* with values from *values*.

    Args:
        text: Template string containing ``{{key}}`` placeholders.
        values: Mapping of placeholder names to replacement strings.

    Returns:
        Template with all placeholders replaced.
    """
    out = text
    for k, v in values.items():
        out = out.replace(f"{{{{{k}}}}}", v)
    return out


def _load_prompt_template(name: str) -> str:
    """Load a prompt template from the ``vibegen/prompts/`` package directory.

    Args:
        name: Template file stem (e.g. ``"fix_errors"`` → ``fix_errors.txt``).

    Returns:
        Template text, or empty string if not found.
    """
    try:
        from importlib import resources

        with resources.path("vibegen", "prompts") as p:
            prompt_file = p / f"{name}.txt"
            if prompt_file.exists():
                return prompt_file.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    script_dir = Path(__file__).parent
    prompt_file = script_dir / "prompts" / f"{name}.txt"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")

    return ""


def _estimate_num_ctx(prompt: str, system_prompt: str = "") -> int:
    """Return the next power-of-2 context window that fits prompt + response budget.

    Args:
        prompt: User prompt string.
        system_prompt: Optional system prompt string.

    Returns:
        Context window size (tokens), capped at 128 k.
    """
    # Rough estimate: 4 chars ≈ 1 token; reserve 4096 tokens for the response.
    tokens = (len(prompt) + len(system_prompt)) // 4 + 4096
    ctx = 4096
    while ctx < tokens:
        ctx *= 2
    return min(ctx, 131072)  # 128k upper bound


def _run_llm_role(
    role: str,
    prompt: str,
    model_provider: str,
    model: str,
    show_output: bool = False,
) -> str:
    """Call the LLM with a role-specific system prompt loaded from a template file.

    Loads ``prompts/role_<role>.txt`` as the system prompt, then delegates to
    :func:`_run_llm`.  Falls back to the default ``system.txt`` when the role
    template is missing.

    Args:
        role: Role name (e.g. ``"architect"``, ``"reviewer"``).
        prompt: User prompt.
        model_provider: ``"claude"`` or ``"ollama"``.
        model: Model identifier string.
        show_output: Print LLM output to stdout when True.

    Returns:
        Generated text from the LLM.
    """
    system_prompt = _load_prompt_template(f"role_{role}") or _load_prompt_template(
        "system"
    )
    return _run_llm(
        prompt,
        model_provider,
        model,
        system_prompt=system_prompt,
        show_output=show_output,
    )


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

    Args:
        prompt: User prompt.
        model_provider: ``"claude"`` or ``"ollama"``.
        model: Model identifier string.
        system_prompt: Override system prompt; auto-loaded when empty.
        show_output: Print LLM output to stdout when True.

    Returns:
        Generated text from the LLM.

    Raises:
        ValueError: If *model_provider* is not recognised.
    """
    if not system_prompt:
        system_prompt = _load_prompt_template("system")
    if model_provider == "claude":
        return _run_claude(prompt, model, system_prompt, show_output)
    if model_provider == "ollama":
        return _run_ollama(prompt, model, system_prompt, show_output)
    raise ValueError(f"Unsupported model provider: {model_provider}")


def _run_claude(prompt: str, model: str, system_prompt: str, show_output: bool) -> str:
    """Call the Claude CLI in ``--print`` mode and return stdout.

    Args:
        prompt: User prompt (passed via stdin).
        model: Claude model identifier.
        system_prompt: System prompt string.
        show_output: Print output to stdout when True.

    Returns:
        Claude's response text.
    """
    cmd = ["claude", "--model", model, "--print"]
    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])
    proc = subprocess.run(
        cmd,
        input=prompt,
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
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


def _run_claude_session(
    prompt: str,
    model: str,
    cwd: Path,
    permission_mode: str = "plan",
    effort: str = "high",
    resume_session: str | None = None,
    system_prompt: str = "",
    max_turns: int = 50,
    show_output: bool = False,
) -> tuple[str, str]:
    """Run Claude CLI in session mode with plan/execute phases.

    Uses ``--output-format json`` to capture both the response text
    and the session ID for multi-turn continuations.

    Args:
        prompt: User prompt.
        model: Claude model identifier.
        cwd: Working directory for Claude (the project root).
        permission_mode: One of ``"plan"``, ``"acceptEdits"``, ``"auto"``.
        effort: Effort level (``"low"``, ``"medium"``, ``"high"``).
        resume_session: Session ID to resume, or None to start fresh.
        system_prompt: System prompt string.
        max_turns: Maximum agentic turns before exiting.
        show_output: Print LLM output to stdout when True.

    Returns:
        Tuple of (result_text, session_id).
    """
    cmd = [
        "claude",
        "-p",
        "--model",
        model,
        "--effort",
        effort,
        "--permission-mode",
        permission_mode,
        "--output-format",
        "json",
        "--max-turns",
        str(max_turns),
    ]
    if resume_session:
        cmd.extend(["--resume", resume_session])
    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])

    # Run Claude as a subprocess.  Print periodic progress messages so
    # the user knows it has not hung — the CLI in ``-p --output-format
    # json`` mode produces no output until it finishes.
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=None,  # Inherits parent stderr
        text=True,
        encoding="utf-8",
        cwd=cwd,
    )

    stop_event = threading.Event()

    def _progress_ticker() -> None:
        """Print elapsed time every 10 s so the user sees activity."""
        start = time.monotonic()
        while not stop_event.wait(10):
            elapsed = int(time.monotonic() - start)
            mins, secs = divmod(elapsed, 60)
            sys.stderr.write(f"\r  Claude working… {mins}m {secs:02d}s   ")
            sys.stderr.flush()
        sys.stderr.write("\r" + " " * 40 + "\r")
        sys.stderr.flush()

    ticker = threading.Thread(target=_progress_ticker, daemon=True)
    ticker.start()

    try:
        stdout, stderr = proc.communicate(input=prompt)
    finally:
        stop_event.set()
        ticker.join(timeout=2)

    result_text = ""
    session_id = ""

    if stdout:
        try:
            data = json.loads(stdout)
            result_text = data.get("result", "")
            session_id = data.get("session_id", "")
        except json.JSONDecodeError:
            result_text = stdout
            _print_err("Failed to parse Claude JSON output")

    if proc.returncode != 0:
        _print_err(f"Claude CLI exited with code {proc.returncode}")
        if stderr:
            _print_err(stderr[:500])

    if show_output and result_text:
        print(result_text)

    return result_text, session_id


def _run_ollama(prompt: str, model: str, system_prompt: str, show_output: bool) -> str:
    """Call OllamaClient and return the response text.

    The context window is capped to the model's actual limit so we never
    request more tokens than the model supports.

    Args:
        prompt: User prompt.
        model: Ollama model name.
        system_prompt: System prompt string.
        show_output: Print output to stdout when True.

    Returns:
        Ollama response text.
    """
    client = OllamaClient(model=model)

    estimated = _estimate_num_ctx(prompt, system_prompt)
    model_limit = client.model_context_length()
    num_ctx = min(estimated, model_limit)

    try:
        result = client.chat(user=prompt, system=system_prompt, num_ctx=num_ctx)
    except Exception as e:  # noqa: BLE001
        _print_err(f"Ollama request failed: {e}")
        return ""

    if show_output:
        print(result)
    return result
