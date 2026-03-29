Reduce complexity across the repository.

1. Read all source files; find: unnecessary abstractions, over-engineered patterns, deep nesting, premature optimizations
2. Simplify: collapse unnecessary hierarchies, flatten nesting with early returns, remove over-engineering
3. Run: uv run ruff check . --fix && uv run ruff format .
4. Run: uv run pytest -x --tb=short