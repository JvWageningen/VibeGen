think

## Scope
Identify performance bottlenecks in: $ARGUMENTS
Do NOT apply optimizations — report only.

## Anchor
Run `uv run radon cc $ARGUMENTS -mi B` for cyclomatic complexity. Read the module.
Look for: nested loops on large data, repeated computations, unnecessary copies, blocking I/O in async, missing caching.

## Outcome
| Hotspot | File:Line | Issue Type | Estimated Impact | Suggested Fix |
|---------|-----------|------------|-----------------|---------------|
| `process_batch` | src/pkg/processor.py:42 | nested loops | High | use vectorized operation |
