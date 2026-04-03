## Scope
Safely undo: $ARGUMENTS (e.g. "last commit", "staged changes", "unstaged changes")
Never use `--hard` without explicit user confirmation.

## Anchor
Show `git status` and `git log -3 --oneline` before acting.

## Outcome
- Last commit: `git reset --soft HEAD~1` (keeps changes staged)
- Staged changes: `git restore --staged .`
- Unstaged changes: `git stash`

Show `git status` and `git log -3 --oneline` after to confirm.
