think hard

## Scope
Implement new functionality: $ARGUMENTS
Do NOT modify unrelated files. Do NOT add speculative utilities beyond what is described.

## Anchor
Run `cymbal structure` and `cymbal search $ARGUMENTS` to understand where this fits. Read the most relevant existing modules and their tests before writing any code.

## Outcome
Your implementation is complete when ALL of the following hold:
1. The new functionality is implemented with type hints and Google-style docstrings.
2. It is exported from `__init__.py` if it is a public API.
3. Tests are written covering happy path, edge cases, and failure modes.
4. `uv run pytest -x` passes.
5. `uv run ruff check . --fix` and `uv run mypy src/` pass.
