think

## Scope
Refactor: $ARGUMENTS
Do NOT change observable behaviour — refactor only.

## Anchor
Read the file first. Run `cymbal investigate $ARGUMENTS` to understand callers and impact before changing signatures.

## Outcome
Issues addressed:

| File | Line | Issue | Fix Applied |
|------|------|-------|-------------|
| src/pkg/module.py | 42 | function >30 lines | extracted `_helper()` |

`uv run pytest -x` passes. `uv run ruff check .` and `uv run mypy src/` pass.
