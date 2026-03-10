"""Tests for vibegen._analysis module."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from vibegen._analysis import (
    _build_dependency_graph,
    _get_installed_package_names,
    _get_pyproject_deps,
    _get_repo_tree,
    _get_test_failure_summary,
    _parse_spec,
    _read_source_files,
)

# ---------------------------------------------------------------------------
# _parse_spec
# ---------------------------------------------------------------------------


@pytest.fixture()
def basic_spec(tmp_path: Path) -> Path:
    content = textwrap.dedent("""\
        ## Name
        MyProject

        ## Python Version
        3.11

        ## Dependencies
        requests, loguru

        ## Description
        A simple web scraper.

        ## Usage
        Run `python -m myproject`
    """)
    spec = tmp_path / "spec.md"
    spec.write_text(content, encoding="utf-8")
    return spec


def test_parse_spec_project_name(basic_spec: Path) -> None:
    result = _parse_spec(basic_spec)
    assert result["project_name"] == "MyProject"


def test_parse_spec_python_version(basic_spec: Path) -> None:
    result = _parse_spec(basic_spec)
    assert result["python_version"] == "3.11"


def test_parse_spec_dependencies(basic_spec: Path) -> None:
    result = _parse_spec(basic_spec)
    assert result["dependencies"] == ["requests", "loguru"]


def test_parse_spec_description(basic_spec: Path) -> None:
    result = _parse_spec(basic_spec)
    assert "web scraper" in result["description"]


def test_parse_spec_usage(basic_spec: Path) -> None:
    result = _parse_spec(basic_spec)
    assert "myproject" in result["usage"]


def test_parse_spec_raw(basic_spec: Path) -> None:
    result = _parse_spec(basic_spec)
    assert "## Name" in result["raw"]


def test_parse_spec_doc_files(tmp_path: Path) -> None:
    content = "## Name\nFoo\n<!-- docs/api.md -->\n"
    spec = tmp_path / "spec.md"
    spec.write_text(content, encoding="utf-8")
    result = _parse_spec(spec)
    assert "docs/api.md" in result["doc_files"]


def test_parse_spec_doc_files_no_match(tmp_path: Path) -> None:
    content = "## Name\nFoo\n<!-- images/logo.png -->\n"
    spec = tmp_path / "spec.md"
    spec.write_text(content, encoding="utf-8")
    result = _parse_spec(spec)
    assert result["doc_files"] == []


def test_parse_spec_default_python_version(tmp_path: Path) -> None:
    content = "## Name\nFoo\n## Description\nbar\n"
    spec = tmp_path / "spec.md"
    spec.write_text(content, encoding="utf-8")
    result = _parse_spec(spec)
    assert result["python_version"] == "3.12"


def test_parse_spec_usage_fallback_examples(tmp_path: Path) -> None:
    content = "## Name\nFoo\n## Examples\nexample usage here\n"
    spec = tmp_path / "spec.md"
    spec.write_text(content, encoding="utf-8")
    result = _parse_spec(spec)
    assert "example usage here" in result["usage"]


def test_parse_spec_usage_fallback_cli(tmp_path: Path) -> None:
    content = "## Name\nFoo\n## CLI\ncli usage here\n"
    spec = tmp_path / "spec.md"
    spec.write_text(content, encoding="utf-8")
    result = _parse_spec(spec)
    assert "cli usage here" in result["usage"]


def test_parse_spec_empty_dependencies(tmp_path: Path) -> None:
    content = "## Name\nFoo\n## Dependencies\n\n"
    spec = tmp_path / "spec.md"
    spec.write_text(content, encoding="utf-8")
    result = _parse_spec(spec)
    assert result["dependencies"] == []


@pytest.mark.parametrize(
    "section,expected_key",
    [
        ("## Interface\ninterface info\n", "interface info"),
        ("## API\napi info\n", "api info"),
    ],
)
def test_parse_spec_usage_fallback_interface_api(
    tmp_path: Path, section: str, expected_key: str
) -> None:
    content = f"## Name\nFoo\n{section}"
    spec = tmp_path / "spec.md"
    spec.write_text(content, encoding="utf-8")
    result = _parse_spec(spec)
    assert expected_key in result["usage"]


# ---------------------------------------------------------------------------
# _build_dependency_graph
# ---------------------------------------------------------------------------


@pytest.fixture()
def simple_src(tmp_path: Path) -> Path:
    src = tmp_path / "src" / "mypkg"
    src.mkdir(parents=True)
    (src / "module_a.py").write_text(
        "import os\nimport requests\n\ndef public_func():\n    pass\n",
        encoding="utf-8",
    )
    (src / "module_b.py").write_text(
        "from mypkg import module_a\n\nclass PublicClass:\n    pass\n",
        encoding="utf-8",
    )
    return src


def test_build_dependency_graph_contains_header(simple_src: Path) -> None:
    result = _build_dependency_graph(simple_src, "mypkg")
    assert "=== Dependency Graph ===" in result


def test_build_dependency_graph_detects_external(simple_src: Path) -> None:
    result = _build_dependency_graph(simple_src, "mypkg")
    assert "requests" in result


def test_build_dependency_graph_detects_internal(simple_src: Path) -> None:
    result = _build_dependency_graph(simple_src, "mypkg")
    assert "mypkg" in result


def test_build_dependency_graph_detects_public_api(simple_src: Path) -> None:
    result = _build_dependency_graph(simple_src, "mypkg")
    assert "public_func" in result
    assert "PublicClass" in result


def test_build_dependency_graph_skips_stdlib(simple_src: Path) -> None:
    result = _build_dependency_graph(simple_src, "mypkg")
    # os is stdlib — should not appear in external packages
    assert (
        "external packages" not in result
        or "os" not in result.split("external packages")[-1].split("\n")[0]
    )


def test_build_dependency_graph_skips_syntax_error(tmp_path: Path) -> None:
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "bad.py").write_text("def broken(\n", encoding="utf-8")
    result = _build_dependency_graph(src, "pkg")
    # Should still return a graph string without crashing
    assert "=== Dependency Graph ===" in result


def test_build_dependency_graph_empty_dir(tmp_path: Path) -> None:
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    result = _build_dependency_graph(src, "pkg")
    assert "=== Dependency Graph ===" in result


def test_build_dependency_graph_private_not_in_api(tmp_path: Path) -> None:
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "mod.py").write_text("def _private(): pass\n", encoding="utf-8")
    result = _build_dependency_graph(src, "pkg")
    assert "_private" not in result


# ---------------------------------------------------------------------------
# _read_source_files
# ---------------------------------------------------------------------------


def test_read_source_files_returns_content(simple_src: Path, tmp_path: Path) -> None:
    result = _read_source_files(simple_src, tmp_path)
    assert "=== " in result
    assert "def public_func" in result


def test_read_source_files_relative_paths(simple_src: Path, tmp_path: Path) -> None:
    result = _read_source_files(simple_src, tmp_path)
    # Paths should be relative, not absolute
    assert str(tmp_path) not in result


def test_read_source_files_empty_dir(tmp_path: Path) -> None:
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    result = _read_source_files(src, tmp_path)
    assert result == ""


# ---------------------------------------------------------------------------
# _get_pyproject_deps
# ---------------------------------------------------------------------------


def test_get_pyproject_deps_no_file(tmp_path: Path) -> None:
    result = _get_pyproject_deps(tmp_path)
    assert result == "(no pyproject.toml found)"


def test_get_pyproject_deps_with_deps(tmp_path: Path) -> None:
    toml = tmp_path / "pyproject.toml"
    toml.write_text(
        '[project]\ndependencies = ["requests>=2.0", "loguru"]\n', encoding="utf-8"
    )
    result = _get_pyproject_deps(tmp_path)
    assert "requests" in result
    assert "loguru" in result


def test_get_pyproject_deps_optional(tmp_path: Path) -> None:
    toml = tmp_path / "pyproject.toml"
    toml.write_text(
        '[project.optional-dependencies]\ndev = ["pytest"]\n', encoding="utf-8"
    )
    result = _get_pyproject_deps(tmp_path)
    assert "pytest" in result


def test_get_pyproject_deps_dependency_groups(tmp_path: Path) -> None:
    toml = tmp_path / "pyproject.toml"
    toml.write_text('[dependency-groups]\ndev = ["black"]\n', encoding="utf-8")
    result = _get_pyproject_deps(tmp_path)
    assert "black" in result


def test_get_pyproject_deps_empty(tmp_path: Path) -> None:
    toml = tmp_path / "pyproject.toml"
    toml.write_text("[project]\n", encoding="utf-8")
    result = _get_pyproject_deps(tmp_path)
    assert "no dependencies" in result.lower()


# ---------------------------------------------------------------------------
# _get_installed_package_names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "dep_str,expected",
    [
        ("- requests>=2.0", {"requests"}),
        ("- loguru==0.7.0", {"loguru"}),
        ("- my-package!=1.0", {"my_package"}),
        ("- Pillow[all]", {"pillow"}),
        ("- requests>=2.0\n- loguru", {"requests", "loguru"}),
        ("", set()),
    ],
)
def test_get_installed_package_names(dep_str: str, expected: set[str]) -> None:
    result = _get_installed_package_names(dep_str)
    assert result == expected


def test_get_installed_package_names_normalizes_dashes(tmp_path: Path) -> None:
    result = _get_installed_package_names("- some-cool-pkg")
    assert "some_cool_pkg" in result


# ---------------------------------------------------------------------------
# _get_test_failure_summary
# ---------------------------------------------------------------------------


def test_get_test_failure_summary_extracts_failed(tmp_path: Path) -> None:
    output = "some output\nFAILED tests/test_foo.py::test_bar\nmore output"
    result = _get_test_failure_summary(output)
    assert "FAILED" in result


def test_get_test_failure_summary_extracts_error(tmp_path: Path) -> None:
    output = "AssertionError: assert 1 == 2"
    result = _get_test_failure_summary(output)
    assert "AssertionError" in result


def test_get_test_failure_summary_fallback_to_first_60(tmp_path: Path) -> None:
    lines = [f"line{i}" for i in range(100)]
    output = "\n".join(lines)
    result = _get_test_failure_summary(output)
    assert "line0" in result
    assert "line61" not in result


def test_get_test_failure_summary_caps_at_80_lines() -> None:
    # 100 matching lines → only first 80 returned
    lines = ["FAILED test_x" for _ in range(100)]
    output = "\n".join(lines)
    result = _get_test_failure_summary(output)
    assert result.count("FAILED") == 80


# ---------------------------------------------------------------------------
# _get_repo_tree
# ---------------------------------------------------------------------------


def test_get_repo_tree_contains_project_name(tmp_path: Path) -> None:
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    result = _get_repo_tree(tmp_path)
    assert tmp_path.name in result


def test_get_repo_tree_excludes_venv(tmp_path: Path) -> None:
    (tmp_path / ".venv").mkdir()
    result = _get_repo_tree(tmp_path)
    assert ".venv" not in result


def test_get_repo_tree_excludes_pycache(tmp_path: Path) -> None:
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    result = _get_repo_tree(tmp_path)
    assert "__pycache__" not in result


def test_get_repo_tree_excludes_egg_info(tmp_path: Path) -> None:
    (tmp_path / "foo.egg-info").mkdir()
    result = _get_repo_tree(tmp_path)
    assert "egg-info" not in result


def test_get_repo_tree_shows_files(tmp_path: Path) -> None:
    (tmp_path / "hello.py").write_text("", encoding="utf-8")
    result = _get_repo_tree(tmp_path)
    assert "hello.py" in result


def test_get_repo_tree_respects_max_depth(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b" / "c" / "d" / "e" / "f"
    deep.mkdir(parents=True)
    (deep / "deep.py").write_text("", encoding="utf-8")
    result = _get_repo_tree(tmp_path, max_depth=2)
    assert "deep.py" not in result
