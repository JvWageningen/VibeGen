"""Parse and write LLM-generated file blocks."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from ._io import _print_ok, _print_warn, _write_file

# Matches: --- file: path --- or --- file: path --- function: name ---
_DELIMITER_RE = re.compile(
    r"^---\s*file:\s*(\S+?)(?:\s*---\s*function:\s*(\S+?))?\s*---\s*$"
)
# Legacy form: --- path --- (no "file:" keyword)
_DELIMITER_LEGACY_RE = re.compile(r"^---\s*(\S+?)\s*---\s*$")
# Separator used in dict keys for function-level blocks.
_FUNC_SEP = "\x00"


def _parse_delimiter(line: str) -> tuple[str, str] | None:
    """Return ``(file_path, function_name)`` from a delimiter line, or None.

    ``function_name`` is empty string for file-level blocks.

    Args:
        line: A single line of LLM output.

    Returns:
        Tuple of path and function name, or None if not a delimiter.
    """
    stripped = line.strip()
    if not (stripped.startswith("---") and stripped.endswith("---")):
        return None
    m = _DELIMITER_RE.match(stripped)
    if m:
        return (m.group(1), m.group(2) or "")
    m = _DELIMITER_LEGACY_RE.match(stripped)
    return (m.group(1), "") if m else None


def _parse_generated_files(output: str) -> dict[str, str]:
    """Parse file and function-level delimiter blocks from LLM output.

    Supports two delimiter forms:
    - ``--- file: path ---`` → file-level block, key is the plain path.
    - ``--- file: path --- function: name ---`` → function-level block,
      key is ``path\\x00func_name`` (use :data:`_FUNC_SEP`).

    Args:
        output: Raw LLM response text.

    Returns:
        Mapping of key → cleaned content.
    """
    files: dict[str, str] = {}
    lines = output.split("\n")
    current_key: str | None = None
    current_content: list[str] = []

    for line in lines:
        parsed = _parse_delimiter(line)
        if parsed is not None:
            if current_key and current_content:
                content = _clean_file_content(current_content)
                if content.strip():
                    files[current_key] = content

            file_path, func_name = parsed
            if file_path and not file_path.lower().startswith("end"):
                current_key = (
                    f"{file_path}{_FUNC_SEP}{func_name}" if func_name else file_path
                )
                current_content = []
        elif current_key:
            current_content.append(line)

    if current_key and current_content:
        content = _clean_file_content(current_content)
        if content.strip():
            files[current_key] = content

    return files


def _clean_file_content(lines: list[str]) -> str:
    """Strip markdown code fences if present; keep raw code otherwise.

    Handles two LLM output styles:
    1. Code wrapped in markdown fences (```python ... ```) — fences are stripped.
    2. Raw code without fences — returned as-is.

    Args:
        lines: Lines of raw LLM content for one file block.

    Returns:
        Cleaned source code string.
    """
    has_fences = any(line.strip().startswith("```") for line in lines)

    if not has_fences:
        return "\n".join(lines).strip("\n")

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


def _merge_function_into_file(dest: Path, func_name: str, new_body: str) -> bool:
    """Replace a single function in *dest* with *new_body* using AST.

    Locates *func_name* in the existing source, replaces only that function's
    lines, and writes the result back.  Falls back to a full-file overwrite
    when the file does not exist or AST parsing fails.

    Args:
        dest: Absolute path of the source file to update.
        func_name: Name of the function to replace.
        new_body: Complete new function source (including ``def`` line).

    Returns:
        True if the merge succeeded, False if a full overwrite is needed.
    """
    if not dest.exists():
        return False
    source = dest.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    lines = source.splitlines(keepends=True)
    node = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == func_name
        ),
        None,
    )
    if node is None:
        return False

    start = node.lineno - 1  # 0-indexed
    end = node.end_lineno  # exclusive (already 1-past-end)
    replacement = new_body.rstrip("\n") + "\n"
    updated = lines[:start] + [replacement] + lines[end:]
    dest.write_text("".join(updated), encoding="utf-8")
    return True


def _write_generated_files(project_path: Path, files: dict[str, str]) -> int:
    """Write generated files; perform targeted function merges where requested.

    Keys from :func:`_parse_generated_files` are either plain relative paths
    (file-level, full overwrite) or ``path\\x00func_name`` (function-level,
    targeted merge via :func:`_merge_function_into_file`).

    Args:
        project_path: Project root directory.
        files: Mapping from :func:`_parse_generated_files`.

    Returns:
        Number of files written or patched.
    """
    count = 0
    for key, content in files.items():
        if _FUNC_SEP in key:
            rel_path, func_name = key.split(_FUNC_SEP, 1)
            dest = project_path / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            if _merge_function_into_file(dest, func_name, content):
                _print_ok(f"Patched: {rel_path}::{func_name}")
            else:
                _print_warn(
                    f"Function '{func_name}' not found in {rel_path}"
                    " — writing full file."
                )
                _write_file(dest, content)
        else:
            dest = project_path / key
            dest.parent.mkdir(parents=True, exist_ok=True)
            _write_file(dest, content)
            _print_ok(f"Generated: {key}")
        count += 1
    return count
