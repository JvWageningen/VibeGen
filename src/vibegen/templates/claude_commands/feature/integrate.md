think

## Scope
Integrate external API or service: $ARGUMENTS
Follow code style rules from `.claude/skills/code-style.md`.

## Anchor
Read the existing codebase to understand the integration pattern. Run `cymbal structure` if needed.

## Outcome
Your integration is complete when ALL of the following hold:
1. A dedicated module exists with: typed client class, Pydantic models for request/response, error handling, loguru logging.
2. It is exported from `__init__.py`.
3. Tests mock the external service; `uv run pytest -x` passes.
4. `uv run ruff check . --fix` and `uv run mypy src/` pass.
