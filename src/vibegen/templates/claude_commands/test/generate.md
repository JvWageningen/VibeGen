think

## Scope
Generate tests for: $ARGUMENTS
Do NOT modify source code — tests only.

## Anchor
Read the source file. Identify all public functions and classes. Read existing tests to match patterns.

## Outcome
| Function | Scenarios Covered | Test Names |
|----------|-------------------|-----------|
| `process_item` | happy path, empty input, raises on invalid | test_process_item_happy, test_process_item_empty, test_process_item_raises |

Create or update matching test file in `tests/`. Test every public function: happy path, edge cases, error handling.
Mock external deps (network, file I/O, APIs). Name tests `test_<function>_<scenario>`.
`uv run pytest -x` passes.
