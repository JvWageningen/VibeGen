Generate edge-case tests for: $ARGUMENTS

1. Read the source file and existing tests; identify boundary conditions: empty, None, zero, negative, max values, type errors
2. Add parametrized tests for each boundary; use specific exception types in pytest.raises()
3. Run: uv run pytest tests/test_$ARGUMENTS.py -x --tb=short
4. Fix failures; run: uv run ruff check tests/ --fix && uv run ruff format tests/