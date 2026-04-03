think

## Scope
Improve test coverage for: $ARGUMENTS
Do NOT remove existing tests.

## Anchor
Run `uv run pytest --cov=src --cov-report=term-missing -x`. Read coverage report and source to identify uncovered paths.

## Outcome
| File | Current % | Uncovered Lines | Tests Added |
|------|-----------|-----------------|-------------|
| src/pkg/module.py | 62% | 45-52, 78 | test_edge_case_empty, test_raises_on_none |

Re-run coverage to confirm improvement. `uv run pytest -x` passes.
