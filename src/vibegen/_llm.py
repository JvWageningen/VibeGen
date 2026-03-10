"""LLM dispatch layer: Anthropic SDK, Claude CLI fallback, Ollama, and prompt utilities."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from ._io import _print_err
from .ollama_client import OllamaClient

# ---------------------------------------------------------------------------
# Optional Anthropic SDK import (graceful fallback to Claude CLI if absent)
# ---------------------------------------------------------------------------

try:
    import anthropic as _anthropic_module

    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

_DOT_INTERVAL = 50  # print one stderr dot every N streamed chunks
_MAX_TOKENS = 16384  # max response tokens; claude-sonnet-4-6 supports up to 64 k


# ---------------------------------------------------------------------------
# Prompt template utilities
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Public LLM entry points
# ---------------------------------------------------------------------------


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
        prompt, model_provider, model, system_prompt=system_prompt,
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


# ---------------------------------------------------------------------------
# Claude: SDK (primary) + CLI (fallback)
# ---------------------------------------------------------------------------


def _run_claude(prompt: str, model: str, system_prompt: str, show_output: bool) -> str:
    """Dispatch to Anthropic SDK (primary) or Claude CLI (fallback).

    Uses the SDK when the ``anthropic`` package is installed and
    ``ANTHROPIC_API_KEY`` is set in the environment.  Falls back to the Claude
    CLI subprocess otherwise, preserving backward compatibility for users who
    authenticated via ``claude auth``.

    Args:
        prompt: User prompt.
        model: Claude model identifier.
        system_prompt: System prompt string.
        show_output: Print output to stdout when True.

    Returns:
        Claude's response text.
    """
    if _ANTHROPIC_AVAILABLE and os.environ.get("ANTHROPIC_API_KEY"):
        return _run_claude_sdk(prompt, model, system_prompt, show_output)
    if not _ANTHROPIC_AVAILABLE:
        _print_err(
            "anthropic package not installed — falling back to Claude CLI. "
            "Install with: uv add anthropic"
        )
    else:
        _print_err(
            "ANTHROPIC_API_KEY not set — falling back to Claude CLI. "
            "Set it with: $env:ANTHROPIC_API_KEY = 'sk-ant-...'"
        )
    return _run_claude_cli(prompt, model, system_prompt, show_output)


def _run_claude_sdk(
    prompt: str, model: str, system_prompt: str, show_output: bool
) -> str:
    """Call the Anthropic API with streaming and return the full response.

    When *show_output* is True, tokens are printed to stdout as they arrive.
    When *show_output* is False, a dot is written to stderr every
    ``_DOT_INTERVAL`` chunks to indicate that generation is in progress.

    Args:
        prompt: User prompt.
        model: Claude model identifier (e.g. ``"claude-sonnet-4-6"``).
        system_prompt: System prompt string.
        show_output: Print tokens to stdout in real-time when True.

    Returns:
        Complete response text, or ``""`` on API error.
    """
    client = _anthropic_module.Anthropic()  # reads ANTHROPIC_API_KEY automatically

    stream_kwargs: dict = {
        "model": model,
        "max_tokens": _MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_prompt:
        stream_kwargs["system"] = system_prompt

    parts: list[str] = []
    chunk_count = 0

    try:
        with client.messages.stream(**stream_kwargs) as stream:
            for text in stream.text_stream:
                parts.append(text)
                if show_output:
                    print(text, end="", flush=True)
                else:
                    chunk_count += 1
                    if chunk_count % _DOT_INTERVAL == 0:
                        print(".", end="", file=sys.stderr, flush=True)
    except _anthropic_module.APIStatusError as exc:
        _print_err(f"Anthropic API error {exc.status_code}: {exc.message}")
        return ""
    except _anthropic_module.APIConnectionError as exc:
        _print_err(f"Anthropic connection error: {exc}")
        return ""
    finally:
        if not show_output and chunk_count > 0:
            print("", file=sys.stderr)  # close the dots line
        elif show_output:
            print("", flush=True)  # ensure trailing newline after streamed output

    return "".join(parts)


def _run_claude_cli(
    prompt: str, model: str, system_prompt: str, show_output: bool
) -> str:
    """Call the Claude CLI in ``--print`` mode (fallback path).

    Used when ``ANTHROPIC_API_KEY`` is not set or the ``anthropic`` package is
    not installed.  The prompt is piped via stdin.

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
        encoding="utf-8",
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


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------


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
