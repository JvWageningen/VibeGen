think

## Scope
Reduce complexity across the repository.
Do NOT change observable behaviour — simplification only.

## Anchor
Run `uv run radon cc src/ -mi C` for high-complexity functions. Run `cymbal search <pattern>` to identify over-engineered abstractions.

## Outcome
| File | Line | Complexity Issue | Simplification Applied |
|------|------|-----------------|----------------------|
| src/pkg/module.py | 42 | 4-level nesting | flattened with early returns |
| src/pkg/utils.py | 15 | premature abstraction | inlined into call site |
