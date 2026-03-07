Migrate code pattern: $ARGUMENTS

1. Find all occurrences; for each: understand context, apply migration, verify behavior preserved
2. Run: uv run ruff check . --fix && uv run ruff format .
3. Run: uv run pytest -x --tb=short