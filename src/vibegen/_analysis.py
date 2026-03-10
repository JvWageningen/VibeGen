"""Code analysis, spec parsing, and dependency inspection utilities."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

# Standard-library module names (Python 3.10+); used to identify external deps.
_STDLIB: frozenset[str] = sys.stdlib_module_names


# ---------------------------------------------------------------------------
# Spec parsing
# ---------------------------------------------------------------------------


def _parse_spec(path: Path) -> dict[str, Any]:
    """Parse a vibegen spec Markdown file into a structured dict.

    Args:
        path: Path to the spec ``.md`` file.

    Returns:
        Dict with keys: project_name, python_version, dependencies,
        doc_files, usage, description, raw.
    """
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


# ---------------------------------------------------------------------------
# Source-code analysis
# ---------------------------------------------------------------------------


def _build_dependency_graph(src_dir: Path, package_name: str) -> str:
    """Build an AST-based dependency and public-API graph for all source files.

    Args:
        src_dir: Directory containing the package source.
        package_name: Top-level package name (used to distinguish internal imports).

    Returns:
        Formatted plain-text dependency graph.
    """
    graph: dict[str, dict[str, list[str]]] = {}

    for py_file in sorted(src_dir.rglob("*.py")):
        module = py_file.stem
        internal: list[str] = []
        external: list[str] = []
        public_api: list[str] = []

        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top == package_name:
                        internal.append(alias.name)
                    elif top not in _STDLIB:
                        external.append(top)
            elif isinstance(node, ast.ImportFrom):
                mod_name = node.module or ""
                top = mod_name.split(".")[0]
                if top == package_name or node.level > 0:
                    internal.append(mod_name or f"(relative level={node.level})")
                elif top and top not in _STDLIB:
                    external.append(top)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    public_api.append(f"def {node.name}()")
            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                public_api.append(f"class {node.name}")

        graph[module] = {
            "internal": sorted(set(internal)),
            "external": sorted(set(external)),
            "api": sorted(set(public_api)),
        }

    result_lines: list[str] = ["=== Dependency Graph ==="]
    for mod, info in sorted(graph.items()):
        result_lines.append(f"\n{mod}:")
        if info["internal"]:
            result_lines.append(f"  internal imports : {', '.join(info['internal'])}")
        if info["external"]:
            result_lines.append(f"  external packages: {', '.join(info['external'])}")
        if info["api"]:
            result_lines.append(f"  public API       : {', '.join(info['api'])}")

    return "\n".join(result_lines)


def _read_source_files(src_dir: Path, project_path: Path) -> str:
    """Return the content of every source Python file as a single formatted block.

    Args:
        src_dir: Source package directory.
        project_path: Project root (used to compute relative paths).

    Returns:
        Concatenated ``=== path ===\\n<content>`` blocks.
    """
    parts: list[str] = []
    for py_file in sorted(src_dir.rglob("*.py")):
        rel = py_file.relative_to(project_path)
        content = py_file.read_text(encoding="utf-8")
        parts.append(f"=== {rel} ===\n{content}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Dependency inspection
# ---------------------------------------------------------------------------


def _get_pyproject_deps(project_path: Path) -> str:
    """Return project dependencies from pyproject.toml as a bullet list.

    Reads all three dependency sections: ``[project.dependencies]``,
    ``[project.optional-dependencies]``, and ``[dependency-groups]``.

    Args:
        project_path: Project root directory.

    Returns:
        Newline-separated ``- <dep>`` lines, or a descriptive fallback string.
    """
    pyproject = project_path / "pyproject.toml"
    if not pyproject.exists():
        return "(no pyproject.toml found)"

    try:
        import tomllib

        with open(pyproject, "rb") as f:
            data = tomllib.load(f)

        all_deps: list[str] = list(data.get("project", {}).get("dependencies", []))

        for group_deps in (
            data.get("project", {}).get("optional-dependencies", {}).values()
        ):
            all_deps.extend(group_deps)

        for group_deps in data.get("dependency-groups", {}).values():
            for item in group_deps:
                if isinstance(item, str):
                    all_deps.append(item)

        return "\n".join(f"- {d}" for d in all_deps) or "(no dependencies listed)"
    except Exception:  # noqa: BLE001
        pass

    # Fallback: parse raw text
    text = pyproject.read_text(encoding="utf-8")
    in_deps = False
    result: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "dependencies = [":
            in_deps = True
            continue
        if in_deps:
            if stripped == "]":
                break
            dep = stripped.strip('",')
            if dep:
                result.append(f"- {dep}")
    return "\n".join(result) or "(could not parse dependencies)"


def _get_installed_package_names(installed_deps_str: str) -> set[str]:
    """Parse a dep-list string into a set of normalized package names.

    Args:
        installed_deps_str: Bullet-list string from :func:`_get_pyproject_deps`.

    Returns:
        Set of lowercased, underscore-normalised package names.
    """
    names: set[str] = set()
    for line in installed_deps_str.splitlines():
        dep = (
            line.lstrip("- ")
            .split(">=")[0]
            .split("==")[0]
            .split("!=")[0]
            .split("<")[0]
            .split("[")[0]
            .strip()
        )
        if dep:
            names.add(dep.lower().replace("-", "_"))
    return names


# ---------------------------------------------------------------------------
# Repo utilities
# ---------------------------------------------------------------------------


def _get_test_failure_summary(output: str) -> str:
    """Extract the most relevant lines from pytest output.

    Args:
        output: Full pytest stdout.

    Returns:
        Up to 80 relevant lines, or the first 60 lines if none matched.
    """
    lines = output.split("\n")
    relevant = [
        line
        for line in lines
        if any(
            x in line
            for x in [
                "FAILED",
                "ERROR",
                "error:",
                "AssertionError",
                "Exception",
                "Traceback",
                "passed",
                "failed",
            ]
        )
    ]
    return "\n".join(relevant[:80]) if relevant else "\n".join(lines[:60])


def _get_repo_tree(project_path: Path, max_depth: int = 5) -> str:
    """Generate an ASCII directory tree of the project.

    Args:
        project_path: Project root directory.
        max_depth: Maximum traversal depth.

    Returns:
        Multi-line string tree representation.
    """
    exclude_dirs = {
        ".venv",
        ".git",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
    }

    def _tree_lines(path: Path, prefix: str = "", depth: int = 0) -> list[str]:
        if depth > max_depth:
            return []
        try:
            items = sorted(path.iterdir())
        except (PermissionError, OSError):
            return []

        items = [
            item
            for item in items
            if item.name not in exclude_dirs and not item.name.endswith(".egg-info")
        ]
        dirs = [item for item in items if item.is_dir()]
        files = [item for item in items if item.is_file()]
        ordered = dirs + files

        sub_lines: list[str] = []
        for idx, item in enumerate(ordered):
            is_last = idx == len(ordered) - 1
            connector = "└── " if is_last else "├── "
            child_prefix = "    " if is_last else "│   "
            if item.is_dir():
                sub_lines.append(f"{prefix}{connector}{item.name}/")
                sub_lines.extend(_tree_lines(item, prefix + child_prefix, depth + 1))
            else:
                sub_lines.append(f"{prefix}{connector}{item.name}")
        return sub_lines

    return "\n".join([f"{project_path.name}/"] + _tree_lines(project_path))
