Fix all mypy type errors.

1. Run: uv run mypy src/ --show-error-codes
2. Read each failing file; fix type errors: add missing annotations, correct wrong types; use type: ignore only as last resort with a comment explaining why
3. Re-run mypy to confirm all errors resolved
4. Run: uv run ruff check . --fix && uv run ruff format .