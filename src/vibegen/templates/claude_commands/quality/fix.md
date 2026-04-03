## Scope
Fix everything that fails in the verification suite.
Do NOT weaken assertions — fix actual bugs.

## Anchor
Run all diagnostics: `uv run ruff check . --output-format=concise; uv run pytest --tb=line -q; uv run mypy src/ --no-error-summary`
Read only failing test files and their source.

## Outcome
All of the following pass: `uv run ruff check .`, `uv run pytest -x`, `uv run mypy src/`
Apply ruff auto-fix first. Fix test failures and mypy errors. Repeat until clean.
