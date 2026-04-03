## Scope
Prepare code for commit — verify everything passes.
Do NOT commit — prepare only.

## Anchor
Run all checks: `uv run ruff check . --output-format=concise; uv run pytest --tb=line -q; uv run mypy src/ --no-error-summary`

## Outcome
All of the following pass: `uv run ruff check .`, `uv run pytest -x`, `uv run mypy src/`
Apply ruff auto-fix. Fix any test/type failures.
Run `git diff --stat` to review staged changes. Suggest a concise conventional commit message.
