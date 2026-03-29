Standardize naming and structure across the repository.

1. Read all source files; fix: snake_case (files, functions, variables), PascalCase (classes), UPPER_SNAKE_CASE (constants), absolute imports, Google-style docstrings on public APIs, loguru instead of print()
2. Run: uv run ruff check . --fix && uv run ruff format .
3. Run: uv run pytest -x --tb=short