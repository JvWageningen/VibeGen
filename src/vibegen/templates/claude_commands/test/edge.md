think

## Scope
Generate edge-case tests for: $ARGUMENTS
Do NOT modify source code — tests only.

## Anchor
Read the source and existing tests. Identify boundary conditions: empty, None, zero, negative, max values, type errors.

## Outcome
| Function | Edge Case | Input | Expected Output | Test Name |
|----------|-----------|-------|-----------------|-----------|
| `process` | empty list | `[]` | raises ValueError | test_process_raises_on_empty |

Use parametrized tests for each boundary. Use specific exception types in `pytest.raises()`.
