## Scope
Safely rename across the codebase: $ARGUMENTS (format: OldName -> NewName)
Do NOT change behaviour — rename only.

## Anchor
Run `cymbal search <OldName> --text` to find every occurrence: definitions, call sites, imports, docstrings, comments.

## Outcome
| Location | Type | Old | New |
|----------|------|-----|-----|
| src/pkg/module.py:42 | definition | old_fn | new_fn |
| tests/test_module.py:15 | call site | old_fn | new_fn |

All occurrences renamed including `__init__.py` exports. `uv run pytest -x` passes.
