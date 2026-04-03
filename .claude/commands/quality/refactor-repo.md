think hard

## Scope
Refactor the entire repository for consistency and maintainability.
Do NOT change public APIs or observable behaviour.

## Anchor
Run diagnostics:
```
uv run ruff check . --output-format=concise
uv run radon cc src/ -mi C
uv run vulture src/ --min-confidence 80
uv run mypy src/ --no-error-summary
```

## Outcome
Work through findings by priority:
1. High-complexity functions (CC ≥ 6): extract helpers, early returns
2. Dead code: remove confirmed unused items
3. Type errors: fix
4. Inconsistent naming/duplication: consolidate

**Diagnostics Summary**: counts of issues found per category
**Changes Applied**: table of File | Change | Rationale
**Verification Results**: all checks passing after changes
