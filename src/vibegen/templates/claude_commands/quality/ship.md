Prepare code for commit.

1. Run all checks at once: `uv run ruff check . --output-format=concise; uv run pytest --tb=line -q; uv run mypy src/ --no-error-summary`
2. Apply ruff auto-fix: `uv run ruff check . --fix && uv run ruff format .`
3. Fix any test failures or type errors; verify with `uv run pytest -x --tb=short`
4. Run: `git diff --stat && git diff` to review what changed; suggest a concise commit message

Do NOT create the commit.