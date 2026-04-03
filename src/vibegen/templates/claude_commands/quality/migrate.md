think hard

## Scope
Migrate code pattern: $ARGUMENTS (format: "OldPattern -> NewPattern")
Do NOT change logic or behaviour — mechanical pattern replacement only.

## Anchor
Run `cymbal search <OldPattern> --text` to find all occurrences. Read each file before modifying.

## Outcome
| File | Line | Before | After | Status |
|------|------|--------|-------|--------|
| src/pkg/module.py | 42 | `old_pattern()` | `new_pattern()` | migrated |

All occurrences migrated. `uv run pytest -x` passes with no regressions.
