Find and merge duplicate logic across the repository.

1. Read all source files; identify functions/patterns appearing in multiple places
2. For each duplication: create a canonical version in a shared module, update all call sites, remove duplicates
3. Run: uv run ruff check . --fix && uv run ruff format .
4. Run: uv run pytest -x --tb=short