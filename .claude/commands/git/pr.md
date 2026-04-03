think

## Scope
Draft a pull request for: $ARGUMENTS

## Anchor
Run `git log --oneline main..HEAD` and `git diff main...HEAD --stat` to summarize the branch.

## Outcome
Generate a PR with:
- **Title**: conventional format, ≤70 chars
- **Summary**: 2-3 bullet points of key changes
- **Version impact**: patch/minor/major based on commit flags
- **Testing notes**: what was tested and how to verify

Use `gh pr create` with a HEREDOC body.
