## Scope
Amend the last commit: $ARGUMENTS
Warn if the commit is already pushed to remote.

## Anchor
Run `git log -1 --format='%s'` to show current message and `git diff --cached --stat` for newly staged changes.

## Outcome
Run `git commit --amend` with: the message from $ARGUMENTS if provided, otherwise the existing message.
Show updated `git log -1 --oneline` to confirm.
