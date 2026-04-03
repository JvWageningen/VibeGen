think hard

## Scope
Add functionality to: $ARGUMENTS
Do NOT modify unrelated files. Do NOT change existing behaviour — extend only.

## Anchor
Read the module and its tests first. Run `cymbal investigate $ARGUMENTS` to understand the existing structure before writing any code.

## Outcome
Your change is complete when ALL of the following hold:
1. New functionality follows existing patterns (type hints, docstrings, naming).
2. It is exported from `__init__.py` if it is a public API.
3. New tests are added or existing tests are updated.
4. `uv run pytest -x` passes.
5. `uv run ruff check . --fix` and `uv run mypy src/` pass.
