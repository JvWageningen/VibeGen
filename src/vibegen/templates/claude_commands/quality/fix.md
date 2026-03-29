Fix everything that fails in the verification suite.

1. Run all diagnostics at once to get the full picture:
   `uv run ruff check . --output-format=concise; uv run pytest --tb=line -q; uv run mypy src/ --no-error-summary`
2. Apply ruff auto-fix: `uv run ruff check . --fix && uv run ruff format .`
3. Fix test failures: read only the failing test files and their source; fix root causes
4. Fix mypy type errors
5. Verify: `uv run pytest -x --tb=short && uv run mypy src/`
6. Repeat from step 1 if anything still fails

Do NOT weaken assertions. Fix actual bugs.