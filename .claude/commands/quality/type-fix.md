## Scope
Fix all mypy type errors.
Do NOT change logic — type annotation fixes only. Use `type: ignore` only as last resort with an explaining comment.

## Anchor
Run `uv run mypy src/ --show-error-codes`. Read each failing file.

## Outcome
Run `uv run mypy src/` — no errors reported. Re-run after each batch of fixes to confirm progress.
