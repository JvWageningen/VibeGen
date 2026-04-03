## Scope
Create a commit for: $ARGUMENTS

## Anchor
Run `git diff --cached --stat` to see staged changes. If nothing staged, run `git status --short` and suggest files to stage.

## Outcome
Write a conventional commit message (feat/fix/chore/docs/test/refactor).
If changes touch source code, include version flag: `[patch]` bugfix, `[minor]` new feature, `[major]` breaking change.
Commit and confirm with `git log -1 --oneline`.
