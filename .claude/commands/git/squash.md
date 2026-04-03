## Scope
Squash recent commits: $ARGUMENTS (number of commits, e.g. 3)

## Anchor
Run `git log --oneline -$ARGUMENTS` to show commits being squashed.

## Outcome
Run `git reset --soft HEAD~$ARGUMENTS`, then compose one conventional commit message summarizing all.
Preserve the highest version flag from the originals (major > minor > patch).
Confirm with `git log --oneline -3`.
