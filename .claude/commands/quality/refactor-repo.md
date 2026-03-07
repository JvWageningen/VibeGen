Refactor the entire repository for consistency and maintainability.

1. Run diagnostic tools to build a prioritized work list:
   `uv run ruff check . --output-format=concise; uv run radon cc src/ -mi C; uv run vulture src/ --min-confidence 80; uv run mypy src/ --no-error-summary`
2. Apply ruff auto-fix: `uv run ruff check . --fix && uv run ruff format .`
3. Work through findings in priority order:
   - High-complexity functions from radon (CC >= 11): extract helpers, apply early returns
   - Unused code from vulture: remove confirmed dead code
   - Type errors from mypy: add missing type hints
   - Inconsistent naming, duplicated logic, missing abstractions: read only affected files
4. Update tests for any changed interfaces
5. Verify: `uv run pytest -x --tb=short && uv run mypy src/`
