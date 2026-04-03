## Scope
Standardize naming and structure across the repository.
Do NOT change behaviour — naming and structure only.
Follow code style rules from `.claude/skills/code-style.md`.

## Anchor
Run `cymbal search <pattern>` for naming violations. Read source files to identify: non-snake_case functions, non-PascalCase classes, print() instead of loguru, relative imports.

## Outcome
| File | Line | Issue | Standard Applied |
|------|------|-------|-----------------|
| src/pkg/module.py | 42 | camelCase function | renamed to snake_case |
| src/pkg/cli.py | 12 | `print()` call | replaced with loguru |

`uv run ruff check .` and `uv run mypy src/` pass.
