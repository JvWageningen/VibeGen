Restructure the module: $ARGUMENTS

1. Read all files; identify: files >200 lines, poor separation of concerns, circular imports
2. Split large files into focused submodules; update all imports; keep public API unchanged (update __init__.py)
3. Run: uv run ruff check . --fix && uv run ruff format .
4. Run: uv run pytest -x --tb=short && uv run mypy src/