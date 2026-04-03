think

## Scope
Restructure the module: $ARGUMENTS
Do NOT change the public API — internal restructuring only.

## Anchor
Read all files in the module. Identify: files >200 lines, poor separation of concerns, circular imports.

## Outcome
| Before | After | Rationale |
|--------|-------|-----------|
| src/pkg/big.py (350 lines) | src/pkg/reader.py + src/pkg/writer.py | single responsibility |

Split large files into focused submodules. Update all imports. Keep public API unchanged (update __init__.py).
`uv run pytest -x` passes.
