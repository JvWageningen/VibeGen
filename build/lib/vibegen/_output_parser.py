"""Parse and write LLM-generated file blocks."""

from __future__ import annotations

from pathlib import Path

from ._io import _print_ok, _write_file


def _parse_generated_files(output: str) -> dict[str, str]:
    """Parse ``--- file: path ---`` blocks from LLM output.

    Args:
        output: Raw LLM response text.

    Returns:
        Mapping of relative file path → cleaned file content.
    """
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
    """Strip markdown code fences and any narrative text after the closing fence.

    Args:
        lines: Lines of raw LLM content for one file block.

    Returns:
        Cleaned source code string.
    """
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
    """Write generated files to the project with LF line endings.

    Args:
        project_path: Project root directory.
        files: Mapping of relative path → content from ``_parse_generated_files``.

    Returns:
        Number of files written.
    """
    count = 0
    for rel_path, content in files.items():
        dest = project_path / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        _write_file(dest, content)
        _print_ok(f"Generated: {rel_path}")
        count += 1
    return count
