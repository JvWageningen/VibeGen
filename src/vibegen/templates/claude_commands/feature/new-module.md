think

## Scope
Create a new module: $ARGUMENTS
Do NOT modify unrelated modules.

## Anchor
Run `cymbal structure` to understand existing module layout and naming conventions. Read the nearest sibling module to match patterns.

## Outcome
Your module is complete when ALL of the following hold:
1. `src/{{PACKAGE_NAME}}/$ARGUMENTS.py` exists with module docstring, absolute imports, type-hinted stubs, Google-style docstrings on all public members.
2. `tests/test_$ARGUMENTS.py` exists with at least one test per public function.
3. `uv run pytest -x` passes.
4. `uv run ruff check . --fix` and `uv run mypy src/` pass.
