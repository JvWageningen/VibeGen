Refactor: $ARGUMENTS

1. Read the file; identify: functions >30 lines (extract helpers), deep nesting (use early returns), code duplication, missing type hints or docstrings
2. Apply improvements
3. Run: uv run ruff check . --fix && uv run ruff format .
4. Run: uv run pytest -x --tb=short && uv run mypy src/