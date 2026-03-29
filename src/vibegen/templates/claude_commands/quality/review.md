Review recent changes.

1. Run: `git diff HEAD~1 --name-only` to get changed files; read only those files
2. Run diagnostics: `uv run ruff check . --output-format=concise; uv run pytest --tb=line -q; uv run mypy src/ --no-error-summary`
3. For each changed file: check type hints, Google-style docstrings, logic errors, unhandled edge cases
4. Suggest simplifications (early returns, extract helpers for functions >30 lines)
5. Apply: `uv run ruff check . --fix && uv run ruff format .`; fix any test or type failures
