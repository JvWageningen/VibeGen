Implement new functionality: $ARGUMENTS

1. Read relevant source files to understand context
2. Implement with type hints and Google-style docstrings; export from __init__.py if public API
3. Write tests using specific exception types in pytest.raises()
4. Run: uv run ruff check . --fix && uv run ruff format .
5. Run: uv run pytest -x --tb=short
6. Run: uv run mypy src/