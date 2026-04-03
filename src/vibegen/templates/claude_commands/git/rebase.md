## Scope
Rebase current branch onto: $ARGUMENTS (default: main).
Do NOT force-push — rebase locally only.

## Anchor
Run `git branch --show-current` to confirm current branch.
Run `git fetch origin` to update remote refs.
Run `git log --oneline HEAD..origin/$ARGUMENTS` to preview incoming commits.

## Outcome
Run `git rebase origin/$ARGUMENTS`.
If conflicts: list with `git diff --name-only --diff-filter=U`, show context per file, resolve each, `git add <file>`, then `git rebase --continue`.
If unresolvable, offer `git rebase --abort`.
Confirm with `git log --oneline -5` and `git status`.
