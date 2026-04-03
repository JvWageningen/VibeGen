## Scope
Merge branch into current: $ARGUMENTS (branch name)

## Anchor
Run `git log --oneline HEAD..$ARGUMENTS` to preview incoming commits. Check for version flags (`[major]`, `[minor]`, `[patch]`).

## Outcome
Run `git merge $ARGUMENTS`. If conflicts arise: list them with `git diff --name-only --diff-filter=U`, show each conflict, and resolve.
After merge, verify with `git status` and `uv run pytest -x`.
