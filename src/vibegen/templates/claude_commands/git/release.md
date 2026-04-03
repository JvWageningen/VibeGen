think

## Scope
Prepare a release commit: $ARGUMENTS (major, minor, or patch)

## Anchor
Read `VERSION` for current version. Run `git log --oneline $(git describe --tags --abbrev=0)..HEAD` to review changes since last tag.

## Outcome
Compose a commit message with the `[$ARGUMENTS]` flag (e.g. `feat: release X.Y.Z [minor]`).
Stage and commit. Remind: CI auto-bumps version and creates a GitHub release on push to main.
