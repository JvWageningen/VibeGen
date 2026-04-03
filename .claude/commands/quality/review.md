think hard

## Scope
Review recent changes for correctness and quality.
Do NOT apply fixes — report issues only.

## Anchor
Run `git diff HEAD~1 --name-only` to get changed files. Read only those files.
Run diagnostics: `uv run ruff check . --output-format=concise; uv run pytest --tb=line -q; uv run mypy src/ --no-error-summary`

## Outcome
| File | Line | Category | Description | Suggested Fix |
|------|------|----------|-------------|---------------|
| src/pkg/module.py | 42 | logic | off-by-one in slice | change `[1:]` to `[1:-1]` |

Category: type / logic / style / edge-case / security / test-coverage
