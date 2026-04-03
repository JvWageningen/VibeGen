think

## Scope
Find and merge duplicate logic across the repository.
Do NOT change behaviour — refactor only.

## Anchor
Run `cymbal search <pattern> --text` to find similar implementations. Identify functions/patterns appearing in multiple places.

## Outcome
| Duplicate | Locations (file:line) | Canonical Location | Action |
|-----------|-----------------------|--------------------|--------|
| `_retry_with_backoff` | src/a.py:12, src/b.py:45 | src/utils.py | consolidated |

For each: create canonical version, update all call sites, remove duplicates. `uv run pytest -x` passes.
