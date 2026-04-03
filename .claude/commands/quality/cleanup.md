## Scope
Remove dead code, unused imports, and duplicate utilities.
Do NOT remove code that is reachable via dynamic dispatch or reflection.

## Anchor
Run `uv run vulture src/ --min-confidence 80`. Review findings carefully before removing anything.
Find duplicate utilities across modules.

## Outcome
| Item | Type | File | Action |
|------|------|------|--------|
| `_old_helper` | function | src/pkg/utils.py | removed |
| `import os` | unused import | src/pkg/cli.py | removed |

Consolidate duplicate utilities into one canonical location and update all call sites.
