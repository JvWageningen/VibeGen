## Scope
Manage git tags: $ARGUMENTS
Subcommands: create <version>, list, push, delete <version>.

## Anchor
Run `git tag --sort=-v:refname | head -10` to show recent tags.
Run `git log --oneline -1` to confirm HEAD.

## Outcome
- create: `git tag -a v<version> -m "Release v<version>"` (annotated tag)
- list: table with Tag | Date | Message via `git tag -l --format='%(tag) %(creatordate:short) %(subject)'`
- push: `git push origin --tags`
- delete: `git tag -d <tag>` and offer `git push origin :refs/tags/<tag>`
Confirm with `git tag --sort=-v:refname | head -5`.
