## Scope
Find all TODO, FIXME, HACK, and XXX markers in the codebase.
Report only — do NOT fix anything.

## Anchor
Search: `cymbal search "TODO|FIXME|HACK|XXX" --text` across `src/` and `tests/`.

## Outcome
| File | Line | Type | Description |
|------|------|------|-------------|

Sort by type: FIXME first, then HACK, TODO, XXX.
Report total count per type at the end.
