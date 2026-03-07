Safely rename across the codebase: $ARGUMENTS (format: OldName -> NewName)

1. Search all source files, tests, and docs for every occurrence of the old name
2. Rename: definition, all call sites, imports, __init__.py exports, docstrings, comments
3. Run: uv run ruff check . --fix && uv run ruff format .
4. Run: uv run pytest -x --tb=short && uv run mypy src/