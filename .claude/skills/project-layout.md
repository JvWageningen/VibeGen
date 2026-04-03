# Project Layout

## Directory Map

- `src/vibegen/` — main package
- `tests/` — test suite (mirrors src structure)
- `docs/reference/` — repo information reference docs (ARCHITECTURE.md, CHANGELOG.md)

## Documentation First Rule

For complex features or refactors:

1. First update or create reference docs in `docs/reference/`
2. Then implement code changes

## Efficiency

- Read specific line ranges (offset/limit), not whole files. Use Grep before Read.
- Batch independent tool calls into single messages.
- Use /compact at logical breakpoints. Never let context exceed ~200K.
